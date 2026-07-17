import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { cp, mkdir, mkdtemp, readFile, readdir, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { execFileSync } from 'node:child_process';
import { _electron as electron } from 'playwright';
import { createServer as createViteServer } from 'vite';

const REPO_ROOT = process.cwd();
const BACKUP_ROOT = path.join(REPO_ROOT, 'benchmark_results', '_recovery_backups', '20260715_pre_resilience');
const BENCHMARK_FIXTURE = path.join(BACKUP_ROOT, 'w1_reviewer_ready_final_20260714');
const RECOVERY_FIXTURE = path.join(BACKUP_ROOT, 'import_test18');
const STAGE_TIMEOUT_MS = 60_000;
const TOTAL_TIMEOUT_MS = 300_000;
const startedAt = Date.now();
const resources = { vite: null, app: null, page: null, closing: false };
const tempDirectories = [];
const shutdownIssues = [];
const artifacts = { outputDirectory: null };

const log = (stage, message) => console.log(`[w1-actual-fixture +${Date.now() - startedAt}ms] ${stage}: ${message}`);
const sha256 = (value) => createHash('sha256').update(value).digest('hex');

async function stage(name, operation, timeoutMs = STAGE_TIMEOUT_MS) {
  log(name, `start (timeout ${timeoutMs}ms)`);
  let timer;
  try {
    const result = await Promise.race([
      Promise.resolve().then(operation),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${name} timed out after ${timeoutMs}ms`)), timeoutMs); }),
    ]);
    log(name, 'complete');
    return result;
  } finally {
    clearTimeout(timer);
  }
}

async function closeApp() {
  const app = resources.app;
  resources.app = null;
  if (!app) return;
  resources.closing = true;
  const child = app.process();
  const pid = child?.pid ?? null;
  const closeStartedAt = Date.now();
  try {
    await stage('electron.close', async () => {
      if (!child || child.exitCode !== null) return;
      const exited = once(child, 'exit');
      void app.evaluate(({ app: electronApp }) => { electronApp.quit(); }).catch((error) => {
        if (!/closed|destroyed|target/i.test(String(error))) log('electron.quit', `request failed: ${String(error)}`);
      });
      if (child.exitCode === null) await exited;
    }, 10_000);
    log('electron.close', `clean exit in ${Date.now() - closeStartedAt}ms (pid ${pid ?? 'unknown'})`);
  } catch (error) {
    let relatedProcesses = 'unavailable';
    try {
      const processLines = execFileSync('ps', ['-axo', 'pid=,ppid=,stat=,command='], { encoding: 'utf8' }).trim().split('\n');
      relatedProcesses = processLines.filter((line) => {
        const [processId, parentId] = line.trim().split(/\s+/, 3).map(Number);
        return processId === pid || parentId === pid;
      }).map((line) => line.trim()).join(' || ') || 'none';
    } catch { /* diagnostic only */ }
    const diagnostic = `pid=${pid ?? 'unknown'} pages=${app.windows().length} elapsedMs=${Date.now() - closeStartedAt} processes=${relatedProcesses} error=${String(error)}`;
    shutdownIssues.push(diagnostic);
    log('electron.close', `leak diagnostic: ${diagnostic}; forcing child exit`);
    try { app.process()?.kill('SIGKILL'); } catch { /* best effort */ }
  } finally {
    resources.page = null;
    resources.closing = false;
  }
}

async function cleanup() {
  await closeApp();
  if (resources.vite) {
    const vite = resources.vite;
    resources.vite = null;
    vite.httpServer?.closeAllConnections?.();
    await stage('vite.close', () => vite.close(), 20_000).catch((error) => log('vite.close', String(error)));
  }
  for (const directory of tempDirectories.reverse()) {
    await stage(`cleanup ${path.basename(directory)}`, () => rm(directory, { recursive: true, force: true }), 20_000)
      .catch((error) => log('cleanup', String(error)));
  }
}

async function copyFixture(name, source) {
  const root = await mkdtemp(path.join(os.tmpdir(), `narrative-ide-${name}-`));
  tempDirectories.push(root);
  const destination = path.join(root, 'project');
  await stage(`${name}.copy`, () => cp(source, destination, { recursive: true, force: false }));
  return destination;
}

function noCredentialEnv() {
  return Object.fromEntries(Object.entries(process.env).filter(([key]) => !/(api[_-]?key|openai|deepseek|anthropic|gemini)/i.test(key)));
}

async function launch(rendererUrl, userData, smokeProjectRoot) {
  resources.app = await stage('electron.launch', () => electron.launch({
    args: ['.'],
    cwd: REPO_ROOT,
    env: {
      ...noCredentialEnv(),
      NARRATIVE_IDE_RENDERER_URL: rendererUrl,
      NARRATIVE_IDE_USER_DATA: userData,
      NARRATIVE_IDE_RUNTIME_SMOKE: '1',
      NARRATIVE_IDE_SMOKE_PROJECT_ROOT: smokeProjectRoot,
    },
  }));
  const page = await stage('electron.firstWindow', () => resources.app.firstWindow());
  resources.page = page;
  page.on('dialog', (dialog) => {
    const action = resources.closing ? dialog.accept() : dialog.dismiss();
    action.catch(() => {});
  });
  await stage('renderer.ready', () => page.waitForSelector('[data-testid="activity-btn-workbench"]'));
  return page;
}

async function openProject(page, projectRoot) {
  await stage('project.dialog.open', () => page.getByTestId('toolbar-open-project').click());
  await stage('project.dialog.visible', () => page.getByTestId('project-dialog').waitFor({ state: 'visible' }));
  await stage('project.dialog.choose', () => page.getByTestId('project-folder-pick').click());
  await stage('project.dialog.selected', () => page.getByTestId('project-folder-input').waitFor({ state: 'visible' }));
  const selectedRoot = await page.getByTestId('project-folder-input').inputValue();
  assert.equal(selectedRoot, await realpath(projectRoot), 'smoke directory grant did not select the disposable project copy');
  await stage('project.dialog.submit', () => page.getByTestId('project-dialog-submit').click());
  await stage('project.dialog.closed', () => page.getByTestId('project-dialog').waitFor({ state: 'hidden' }));
}

async function storeSnapshot(page) {
  return page.evaluate(() => {
    const state = window.__narrativeStore.getState();
    return {
      proposals: state.proposals.map((proposal) => ({ id: proposal.id, status: proposal.status, lastBlockReason: proposal.lastBlockReason ?? null })),
      proposalHistory: state.proposalHistory.map((proposal) => ({ id: proposal.id, status: proposal.status })),
      counts: {
        characters: state.characters.length,
        characterTags: state.characterTags.length,
        relationships: state.relationships.length,
        chapters: state.chapters.length,
        scenes: state.scenes.length,
        manuscriptNodes: state.manuscriptNodes.length,
        timelineBranches: state.timelineBranches.length,
        timelineEvents: state.timelineEvents.length,
        worldContainers: state.worldContainers.length,
        worldItems: state.worldItems.length,
      },
      scenes: state.scenes.map((scene) => ({ id: scene.id, sourceSpan: scene.sourceSpan ?? null })),
    };
  });
}

async function waitFor(predicate, description) {
  const deadline = Date.now() + STAGE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${description}`);
}

const acceptedPendingCounts = (snapshot) => ({
  accepted: [...snapshot.proposals, ...snapshot.proposalHistory].filter((proposal) => proposal.status === 'accepted').length,
  pending: snapshot.proposals.filter((proposal) => proposal.status === 'pending' || !proposal.status).length,
});

async function inspectRepairReceipt(projectRoot, outputDirectory) {
  const runId = 'live_smoke_20260713_033431_6ee129ee';
  const transactionsRoot = path.join(projectRoot, 'system', 'transactions');
  const transactionNames = (await readdir(transactionsRoot)).filter((name) => name.startsWith(`repair-package-${runId}`));
  assert.equal(transactionNames.length, 1, 'repair must write exactly one idempotent migration transaction');
  const transactionRoot = path.join(transactionsRoot, transactionNames[0]);
  const committed = JSON.parse(await readFile(path.join(transactionRoot, 'committed.json'), 'utf8'));
  const manifest = JSON.parse(await readFile(path.join(transactionRoot, 'manifest.json'), 'utf8'));
  assert.equal(committed.state, 'committed', 'repair migration receipt must be committed');
  assert(manifest.targets.some((target) => target.relativePath === `system/imports/${runId}/staged_manuscript_projection.json`), 'repair transaction must target the staged manuscript projection');

  const artifactPath = path.join(projectRoot, 'system', 'imports', runId, 'staged_manuscript_projection.json');
  const artifact = JSON.parse(await readFile(artifactPath, 'utf8'));
  assert.equal(Object.prototype.hasOwnProperty.call(artifact, 'source_file_path'), false, 'migrated projection must remove the legacy source path');
  assert.deepEqual(artifact.source_ref, {
    relativePath: `system/imports/${runId}/raw_source.txt`,
    sha256: artifact.source_ref.sha256,
    contractVersion: 'w1-raw-source-v1',
    lineageId: runId,
    attemptId: 'legacy',
  });
  assert.match(artifact.source_ref.sha256, /^[a-f0-9]{64}$/);

  const receiptOutputPath = path.join(outputDirectory, 'migration-receipt.json');
  await writeFile(receiptOutputPath, `${JSON.stringify({ transaction: transactionNames[0], committed, manifest }, null, 2)}\n`);
  return { transactionNames, receiptOutputPath, artifactHash: sha256(await readFile(artifactPath)) };
}

async function benchmarkAcceptance(page, projectRoot, outputDirectory) {
  await openProject(page, projectRoot);
  const before = await storeSnapshot(page);
  const loadedProposalShape = await page.evaluate(() => {
    const proposal = window.__narrativeStore.getState().proposals[0];
    return {
      source: proposal?.source,
      sourceWorkflow: proposal?.source_workflow ?? proposal?.sourceWorkflow ?? null,
      operationsLength: Array.isArray(proposal?.operations) ? proposal.operations.length : null,
      proposedOperationsLength: Array.isArray(proposal?.proposedOperations) ? proposal.proposedOperations.length : null,
    };
  });
  log('benchmark.loaded-proposal', JSON.stringify(loadedProposalShape));
  assert.equal(before.proposals.length, 89, 'benchmark fixture must expose all 89 real proposals');
  assert(before.proposals.every((proposal) => proposal.status === 'pending'), 'benchmark fixture proposals must start pending');
  assert.equal(before.proposalHistory.length, 0, 'benchmark fixture must start without proposal history');

  await stage('workbench.open', () => page.getByTestId('activity-btn-workbench').click());
  await stage('workbench.inbox.select', async () => {
    await page.getByTestId('sidebar-section-workbench-inbox').click();
    await page.getByTestId('workbench-inbox-list').waitFor({ state: 'visible', timeout: STAGE_TIMEOUT_MS });
  });
  const repairButton = page.locator('[data-testid^="repair-blocked-package-"]');
  const acceptButton = page.locator('[data-testid^="accept-import-package-"]');
  await stage('package.action.visible', () => Promise.race([
    repairButton.waitFor({ state: 'visible', timeout: STAGE_TIMEOUT_MS }),
    acceptButton.waitFor({ state: 'visible', timeout: STAGE_TIMEOUT_MS }),
  ]));
  assert.equal((await repairButton.count()) + (await acceptButton.count()), 1, 'all 89 legacy W1 proposals must form one current package action');

  if (await repairButton.isVisible()) {
    log('package.action', await repairButton.getAttribute('data-testid'));
    await stage('package.repair', () => repairButton.click());
    await new Promise((resolve) => setTimeout(resolve, 750));
    const repaired = await storeSnapshot(page);
    assert.deepEqual(repaired.counts, before.counts, 'Repair must not mutate canonical collections');
    assert.deepEqual(acceptedPendingCounts(repaired), { accepted: 0, pending: 89 }, 'Repair must leave all proposals pending');
    if (!repaired.proposals.every((proposal) => proposal.lastBlockReason === null) || !(await acceptButton.isVisible())) {
      const reasons = [...new Set(repaired.proposals.map((proposal) => proposal.lastBlockReason).filter(Boolean))];
      const blockedScreenshotPath = path.join(outputDirectory, 'repair-blocked.png');
      const repairStatePath = path.join(outputDirectory, 'repair-state.json');
      await stage('package.repair.blocked-screenshot', () => page.screenshot({ path: blockedScreenshotPath, fullPage: true }));
      await writeFile(repairStatePath, `${JSON.stringify({ loadedProposalShape, reasons, before, repaired }, null, 2)}\n`);
      log('package.repair.blocked-screenshot', blockedScreenshotPath);
      log('package.repair.state', repairStatePath);
      throw new Error(`Repair did not make the package valid/unblocked: loadedShape=${JSON.stringify(loadedProposalShape)} blockedReasons=${JSON.stringify(reasons)}`);
    }
    assert.equal(repaired.proposalHistory.length, 0, 'Repair must not add proposal history');

    const firstReceipt = await inspectRepairReceipt(projectRoot, outputDirectory);
    if (await repairButton.isVisible()) {
      await stage('package.repair.repeat', () => repairButton.click());
      await stage('package.repair.repeat.settle', () => acceptButton.waitFor({ state: 'visible', timeout: STAGE_TIMEOUT_MS }));
      const repeated = await storeSnapshot(page);
      const repeatedReceipt = await inspectRepairReceipt(projectRoot, outputDirectory);
      assert.deepEqual(repeated, repaired, 'Repeated visible Repair must be state-idempotent');
      assert.deepEqual(repeatedReceipt, firstReceipt, 'Repeated visible Repair must not write another migration');
    } else {
      log('package.repair.repeat', 'repair control hidden after successful repair; explicit Accept is now the only package action');
    }
  }

  assert(await acceptButton.isVisible(), 'package must expose explicit Accept only after it is valid and unblocked');
  await stage('package.accept.explicit', () => acceptButton.click());
  await stage('package.accept.persist', () => waitFor(async () => {
    const current = await storeSnapshot(page);
    return current.proposals.length === 0 && acceptedPendingCounts(current).accepted === 89;
  }, '89 accepted proposals and zero pending proposals'));

  const accepted = await storeSnapshot(page);
  assert.deepEqual(acceptedPendingCounts(accepted), { accepted: 89, pending: 0 });
  assert.deepEqual(accepted.counts, {
    characters: 20,
    characterTags: 5,
    relationships: 2,
    chapters: 10,
    scenes: 10,
    manuscriptNodes: 20,
    timelineBranches: 1,
    timelineEvents: 9,
    worldContainers: 7,
    worldItems: 24,
  });
  assert.equal(accepted.proposals.length, 0);
  assert.equal(accepted.proposalHistory.length, 89);

  const screenshotPath = path.join(outputDirectory, 'accepted-package.png');
  await stage('benchmark.screenshot', () => page.screenshot({ path: screenshotPath, fullPage: true }));
  const receipt = await inspectRepairReceipt(projectRoot, outputDirectory);

  const sourcePath = path.join(projectRoot, 'system', 'imports', 'live_smoke_20260713_033431_6ee129ee', 'raw_source.txt');
  const sourceHash = sha256(await readFile(sourcePath));
  assert(accepted.scenes.every((scene) => scene.sourceSpan?.raw_source_hash === sourceHash), 'accepted scenes must preserve the canonical raw source hash');
  assert(accepted.scenes.every((scene) => typeof scene.sourceSpan?.substring_hash === 'string' && scene.sourceSpan.substring_hash.length === 64), 'accepted scenes must preserve source span hashes');

  return { screenshotPath, receiptOutputPath: receipt.receiptOutputPath };
}

async function recoveryCenter(page, projectRoot) {
  await openProject(page, projectRoot);
  let preflight = null;
  await stage('recovery.sidecar.ready', async () => {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      preflight = await page.evaluate(async (root) => window.narrativeIDE.runtimeRecoverable({ projectRoot: root }), projectRoot);
      if (preflight?.runs) return;
      if (attempt === 20) {
        const fallback = await page.evaluate(async (root) => window.narrativeIDE.sidecarSpawn({ projectRoot: root }), projectRoot);
        assert.equal(fallback.ok, true, `Recovery sidecar fallback failed: ${fallback.error || 'unknown error'}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(`Recovery sidecar stayed offline: ${JSON.stringify(preflight)}`);
  });
  log('recovery.bridge.preflight', JSON.stringify(preflight));
  assert.equal(preflight.runs?.length, 1, `Recovery bridge did not discover the legacy attempt: ${JSON.stringify(preflight)}`);
  await stage('import.modal.open', () => page.getByTestId('open-import-btn').click());
  const runCard = page.locator('[data-testid^="w1-recovery-run-"]');
  await stage('recovery.run.visible', () => runCard.waitFor({ state: 'visible', timeout: STAGE_TIMEOUT_MS }));
  assert.equal(await runCard.count(), 1, 'Recovery Center must discover exactly one legacy run');
  const details = await stage('recovery.bridge.inspect', () => page.evaluate(async (root) => window.narrativeIDE.runtimeRecoverable({ projectRoot: root }), projectRoot));
  assert.equal(details.runs.length, 1, 'runtime bridge must report one recoverable attempt');
  const [run] = details.runs;
  assert.equal(run.config.completed_chunks, 4);
  assert.equal(run.config.total_chunks, 10);
  assert.equal(run.source_compatible, true);
  assert.match(String(run.attempt_id), /^legacy_attempt_/);
  assert.equal(run.status, 'interrupted', 'an expired legacy attempt must be recoverable without being auto-resumed');
  const events = await stage('recovery.events.inspect', () => page.evaluate(async ({ root, attemptId }) => window.narrativeIDE.runtimeEvents({ projectRoot: root, attempt_id: attemptId, after_sequence: 0 }), { root: projectRoot, attemptId: run.attempt_id }));
  const resumeEvents = events.events.filter((event) => event.event_type === 'resume');
  assert.equal(resumeEvents.length, 0, 'Recovery Center must not invoke resume without a user action');
  return {
    lineageId: run.lineage_id,
    attemptId: run.attempt_id,
    completed: run.config.completed_chunks,
    total: run.config.total_chunks,
    sourceCompatible: run.source_compatible,
    status: run.status,
    resumeEvents: resumeEvents.length,
  };
}

async function main() {
  const totalTimer = setTimeout(() => { throw new Error(`harness exceeded ${TOTAL_TIMEOUT_MS}ms total timeout`); }, TOTAL_TIMEOUT_MS);
  try {
    await stage('fixtures.verify', async () => {
      for (const fixture of [BENCHMARK_FIXTURE, RECOVERY_FIXTURE]) assert((await stat(fixture)).isDirectory(), `missing fixture: ${fixture}`);
    });
    const benchmarkRoot = await copyFixture('w1-benchmark', BENCHMARK_FIXTURE);
    const recoveryRoot = await copyFixture('w1-recovery', RECOVERY_FIXTURE);
    const recoverySource = path.join(recoveryRoot, 'system', 'imports', 'import_a684a04d162f', 'raw_source.txt');
    const recoveryProgressPath = path.join(recoveryRoot, 'import_progress.json');
    const recoveryProgress = JSON.parse(await readFile(recoveryProgressPath, 'utf8'));
    recoveryProgress.source_file_path = recoverySource;
    await stage('recovery.copy.source-remap', () => writeFile(recoveryProgressPath, `${JSON.stringify(recoveryProgress, null, 2)}\n`));

    const outputDirectory = path.join('/tmp', `narrative-ide-w1-actual-fixture-${Date.now()}`);
    artifacts.outputDirectory = outputDirectory;
    await mkdir(outputDirectory, { recursive: true });
    const userData = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-w1-fixture-user-data-'));
    tempDirectories.push(userData);
    resources.vite = await stage('vite.create', () => createViteServer({ root: REPO_ROOT, logLevel: 'error', server: { host: '127.0.0.1', port: 0 } }));
    await stage('vite.listen', () => resources.vite.listen());
    const rendererUrl = resources.vite.resolvedUrls?.local?.[0];
    assert(rendererUrl, 'Vite did not expose a local renderer URL');

    let page;
    let outputs = null;
    let benchmarkFailure = null;
    try {
      page = await launch(rendererUrl, userData, benchmarkRoot);
      outputs = await benchmarkAcceptance(page, benchmarkRoot, outputDirectory);
      log('benchmark.screenshot', outputs.screenshotPath);
      log('benchmark.migration-receipt', outputs.receiptOutputPath);
    } catch (error) {
      benchmarkFailure = error;
      log('benchmark.result', `FAIL: ${String(error)}`);
    } finally {
      await closeApp();
    }

    if (!benchmarkFailure) {
      try {
        page = await launch(rendererUrl, userData, benchmarkRoot);
        await stage('restart.persistence', async () => {
          await openProject(page, benchmarkRoot);
          const persisted = await storeSnapshot(page);
          assert.deepEqual(acceptedPendingCounts(persisted), { accepted: 89, pending: 0 });
          assert.deepEqual(persisted.counts, {
            characters: 20,
            characterTags: 5,
            relationships: 2,
            chapters: 10,
            scenes: 10,
            manuscriptNodes: 20,
            timelineBranches: 1,
            timelineEvents: 9,
            worldContainers: 7,
            worldItems: 24,
          });
        });
      } finally {
        await closeApp();
      }
    } else {
      log('restart.persistence', 'skipped because explicit acceptance did not complete');
    }

    let recoveryResult = null;
    let recoveryFailure = null;
    try {
      page = await launch(rendererUrl, userData, recoveryRoot);
      recoveryResult = await recoveryCenter(page, recoveryRoot);
      const recoveryOutputPath = path.join(outputDirectory, 'recovery-result.json');
      await writeFile(recoveryOutputPath, `${JSON.stringify(recoveryResult, null, 2)}\n`);
      log('recovery.result', recoveryOutputPath);
    } catch (error) {
      recoveryFailure = error;
      log('recovery.result', `FAIL: ${String(error)}`);
    } finally {
      await closeApp();
    }

    const failures = [
      benchmarkFailure && `benchmark=${benchmarkFailure.stack || benchmarkFailure}`,
      recoveryFailure && `recovery=${recoveryFailure.stack || recoveryFailure}`,
      shutdownIssues.length && `shutdown=${shutdownIssues.join(' | ')}`,
    ].filter(Boolean);
    if (failures.length) throw new Error(failures.join('\n'));

    await writeFile(path.join(outputDirectory, 'result.json'), `${JSON.stringify({ status: 'PASS', ...outputs, recoveryResult, shutdownIssues }, null, 2)}\n`);
    log('result.artifact', path.join(outputDirectory, 'result.json'));
    log('result', 'PASS');
  } finally {
    clearTimeout(totalTimer);
    await cleanup();
  }
}

main().catch((error) => {
  const failure = error.stack || String(error);
  const persistFailure = artifacts.outputDirectory
    ? writeFile(path.join(artifacts.outputDirectory, 'failure.json'), `${JSON.stringify({ status: 'FAIL', error: failure, shutdownIssues }, null, 2)}\n`)
    : Promise.resolve();
  persistFailure.finally(() => {
    if (artifacts.outputDirectory) console.error(`[w1-actual-fixture] failure artifact: ${path.join(artifacts.outputDirectory, 'failure.json')}`);
    console.error(`[w1-actual-fixture] FAIL: ${failure}`);
    process.exitCode = 1;
  });
});
