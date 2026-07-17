import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readFile, readdir, realpath, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { _electron as electron } from 'playwright';
import { createServer as createViteServer } from 'vite';

const REPO_ROOT = process.cwd();
const PROJECT_ROOT = path.join(REPO_ROOT, 'benchmark_results', 'w1_reviewer_ready_final_20260714');
const BACKUP_ROOT = path.join(REPO_ROOT, 'benchmark_results', '_recovery_backups', '20260715_pre_resilience');
const BACKUP_PROJECT_ROOT = path.join(BACKUP_ROOT, 'w1_reviewer_ready_final_20260714');
const RUN_ID = 'live_smoke_20260713_033431_6ee129ee';
const IMPORT_ROOT = path.join(PROJECT_ROOT, 'system', 'imports', RUN_ID);
const STAGED_PROJECTION = path.join(IMPORT_ROOT, 'staged_manuscript_projection.json');
const EVIDENCE_ROOT = path.join(REPO_ROOT, 'benchmark_results', '_evidence', '20260715_w1_original_repair_only');
const TIMEOUT_MS = 60_000;
const TOTAL_TIMEOUT_MS = 240_000;
const startedAt = Date.now();
const resources = { app: null, vite: null };
const events = [];

const log = (stage, message) => {
  const entry = { elapsedMs: Date.now() - startedAt, stage, message };
  events.push(entry);
  console.log(`[w1-original-repair-only +${entry.elapsedMs}ms] ${stage}: ${message}`);
};

const sha256 = (value) => createHash('sha256').update(value).digest('hex');

async function stage(name, operation, timeoutMs = TIMEOUT_MS) {
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

async function listFiles(root) {
  if (!existsSync(root)) return [];
  if ((await stat(root)).isFile()) return [root];
  const entries = await readdir(root, { withFileTypes: true });
  const children = await Promise.all(entries.sort((a, b) => a.name.localeCompare(b.name)).map(async (entry) => {
    const candidate = path.join(root, entry.name);
    return entry.isDirectory() ? listFiles(candidate) : [candidate];
  }));
  return children.flat();
}

async function inventory(paths) {
  const files = (await Promise.all(paths.map(listFiles))).flat().sort();
  return Object.fromEntries(await Promise.all(files.map(async (file) => [
    path.relative(PROJECT_ROOT, file),
    sha256(await readFile(file)),
  ])));
}

async function captureCanonicalInventory() {
  return inventory([
    path.join(PROJECT_ROOT, 'characters'),
    path.join(PROJECT_ROOT, 'entities', 'candidates.json'),
    path.join(PROJECT_ROOT, 'entities', 'character-tags.json'),
    path.join(PROJECT_ROOT, 'entities', 'relationships.json'),
    path.join(PROJECT_ROOT, 'entities', 'timeline'),
    path.join(PROJECT_ROOT, 'timeline'),
    path.join(PROJECT_ROOT, 'entities', 'world'),
    path.join(PROJECT_ROOT, 'world'),
    path.join(PROJECT_ROOT, 'writing', 'chapters'),
    path.join(PROJECT_ROOT, 'writing', 'scenes'),
    path.join(PROJECT_ROOT, 'writing', 'manuscript'),
  ]);
}

function noCredentialEnv() {
  return Object.fromEntries(Object.entries(process.env).filter(([key]) => !/(api[_-]?key|openai|deepseek|anthropic|gemini)/i.test(key)));
}

async function closeApp() {
  const app = resources.app;
  resources.app = null;
  if (!app) return;
  const child = app.process();
  try {
    await stage('electron.close', async () => {
      if (!child || child.exitCode !== null) return;
      const exited = once(child, 'exit');
      await app.evaluate(({ app: electronApp }) => electronApp.quit());
      if (child.exitCode === null) await exited;
    }, 15_000);
  } catch (error) {
    try { child?.kill('SIGKILL'); } catch { /* bounded cleanup */ }
    throw error;
  }
}

async function launch(rendererUrl, userData) {
  resources.app = await stage('electron.launch', () => electron.launch({
    args: ['.'],
    cwd: REPO_ROOT,
    env: {
      ...noCredentialEnv(),
      NARRATIVE_IDE_RENDERER_URL: rendererUrl,
      NARRATIVE_IDE_USER_DATA: userData,
      NARRATIVE_IDE_RUNTIME_SMOKE: '1',
      NARRATIVE_IDE_SMOKE_PROJECT_ROOT: PROJECT_ROOT,
    },
  }));
  const page = await stage('electron.first-window', () => resources.app.firstWindow());
  page.on('dialog', (dialog) => dialog.dismiss().catch(() => {}));
  await stage('renderer.ready', () => page.waitForSelector('[data-testid="activity-btn-workbench"]'));
  return page;
}

async function openOriginalProject(page) {
  await stage('project.open', () => page.getByTestId('toolbar-open-project').click());
  await stage('project.dialog', () => page.getByTestId('project-dialog').waitFor({ state: 'visible' }));
  await stage('project.pick', () => page.getByTestId('project-folder-pick').click());
  const folder = page.getByTestId('project-folder-input');
  await stage('project.selected', () => folder.waitFor({ state: 'visible' }));
  assert.equal(await folder.inputValue(), await realpath(PROJECT_ROOT), 'Electron did not select the ORIGINAL benchmark project.');
  await stage('project.submit', () => page.getByTestId('project-dialog-submit').click());
  await stage('project.loaded', () => page.getByTestId('project-dialog').waitFor({ state: 'hidden' }));
}

async function openPackage(page) {
  await stage('workbench.open', () => page.getByTestId('activity-btn-workbench').click());
  await stage('workbench.inbox', async () => {
    await page.getByTestId('sidebar-section-workbench-inbox').click();
    await page.getByTestId('workbench-inbox-list').waitFor({ state: 'visible' });
  });
}

async function snapshot(page) {
  return page.evaluate(() => {
    const state = window.__narrativeStore.getState();
    const proposalShape = (proposal) => ({
      id: proposal.id,
      status: proposal.status || 'pending',
      lastBlockReason: proposal.lastBlockReason ?? null,
      operations: proposal.operations ?? null,
      proposedOperations: proposal.proposedOperations ?? null,
    });
    return {
      proposals: state.proposals.map(proposalShape),
      proposalHistory: state.proposalHistory.map(proposalShape),
      canonicalCounts: {
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
    };
  });
}

function pendingAndAccepted(state) {
  return {
    pending: state.proposals.filter((proposal) => proposal.status === 'pending').length,
    accepted: [...state.proposals, ...state.proposalHistory].filter((proposal) => proposal.status === 'accepted').length,
  };
}

function assertArtifactRefV2(state) {
  const descriptors = state.proposals.flatMap((proposal) => (proposal.operations || []).flatMap((operation) => {
    const descriptor = operation?.fields?.stagedManuscriptProjection;
    return descriptor ? [{ proposalId: proposal.id, descriptor }] : [];
  }));
  assert(descriptors.length > 0, 'No staged manuscript descriptors were found in the real operations field.');
  for (const { proposalId, descriptor } of descriptors) {
    assert.equal(descriptor.contract_version, 'w1-staged-manuscript-v2', `${proposalId} does not use the ArtifactRef v2 contract.`);
    assert.equal(descriptor.artifact_path, undefined, `${proposalId} retained a legacy artifact_path descriptor.`);
    assert.deepEqual(descriptor.artifactRef, {
      relativePath: `system/imports/${RUN_ID}/staged_manuscript_projection.json`,
      sha256: descriptor.artifactRef?.sha256,
      contractVersion: 'w1-staged-manuscript-v2',
      lineageId: RUN_ID,
      attemptId: 'legacy',
    }, `${proposalId} ArtifactRef v2 is not the expected contained legacy reference.`);
    assert.match(descriptor.artifactRef.sha256, /^[a-f0-9]{64}$/, `${proposalId} ArtifactRef v2 has no SHA-256.`);
  }
  return { descriptorCount: descriptors.length, operationField: 'operations' };
}

async function inspectTransaction() {
  const transactionsRoot = path.join(PROJECT_ROOT, 'system', 'transactions');
  const ids = (await readdir(transactionsRoot)).filter((name) => name.startsWith(`repair-package-${RUN_ID}`));
  assert.equal(ids.length, 1, `Expected exactly one repair transaction; found ${ids.length}.`);
  const transaction = ids[0];
  const transactionRoot = path.join(transactionsRoot, transaction);
  const committed = JSON.parse(await readFile(path.join(transactionRoot, 'committed.json'), 'utf8'));
  const manifest = JSON.parse(await readFile(path.join(transactionRoot, 'manifest.json'), 'utf8'));
  assert.equal(committed.state, 'committed', 'Repair transaction was not committed.');
  assert(manifest.targets.some((target) => target.relativePath === `system/imports/${RUN_ID}/staged_manuscript_projection.json`), 'Repair receipt does not target the staged projection.');
  return { id: transaction, committed, manifest };
}

async function inspectProjection() {
  const projection = JSON.parse(await readFile(STAGED_PROJECTION, 'utf8'));
  assert.equal(Object.hasOwn(projection, 'source_file_path'), false, 'Projection retained source_file_path.');
  assert.deepEqual(projection.source_ref, {
    relativePath: `system/imports/${RUN_ID}/raw_source.txt`,
    sha256: projection.source_ref?.sha256,
    contractVersion: 'w1-raw-source-v1',
    lineageId: RUN_ID,
    attemptId: 'legacy',
  }, 'Projection source_ref is invalid.');
  assert.match(projection.source_ref.sha256, /^[a-f0-9]{64}$/, 'Projection source_ref has no SHA-256.');
  return { sha256: sha256(await readFile(STAGED_PROJECTION)), sourceRef: projection.source_ref };
}

async function waitForVisible(locator, message) {
  await stage(message, () => locator.waitFor({ state: 'visible' }));
}

async function main() {
  const totalTimer = setTimeout(() => { throw new Error(`Repair-only migration exceeded ${TOTAL_TIMEOUT_MS}ms.`); }, TOTAL_TIMEOUT_MS);
  const receipt = { startedAt: new Date().toISOString(), projectRoot: PROJECT_ROOT, backupRoot: BACKUP_ROOT, events };
  try {
    await stage('preflight.backup', async () => {
      assert((await stat(BACKUP_ROOT)).isDirectory(), `Missing required backup root: ${BACKUP_ROOT}`);
      assert((await stat(BACKUP_PROJECT_ROOT)).isDirectory(), `Missing required original-project backup: ${BACKUP_PROJECT_ROOT}`);
      assert((await stat(PROJECT_ROOT)).isDirectory(), `Missing original benchmark: ${PROJECT_ROOT}`);
    });
    await mkdir(EVIDENCE_ROOT, { recursive: true });
    receipt.before = {
      canonicalInventory: await stage('inventory.before.canonical', captureCanonicalInventory),
      inboxSha256: sha256(await readFile(path.join(PROJECT_ROOT, 'system', 'inbox.json'))),
      stagedProjectionSha256: sha256(await readFile(STAGED_PROJECTION)),
      backupManifestSha256: sha256(await readFile(path.join(BACKUP_ROOT, 'BACKUP_MANIFEST.md'))),
    };
    assert.equal(Object.keys(receipt.before.canonicalInventory).length > 0, true, 'Canonical inventory is unexpectedly empty.');

    resources.vite = await stage('vite.create', () => createViteServer({ root: REPO_ROOT, configFile: path.join(REPO_ROOT, 'vite.config.ts'), server: { host: '127.0.0.1', port: 0 } }));
    await stage('vite.listen', () => resources.vite.listen());
    const rendererUrl = resources.vite.resolvedUrls.local[0];
    const userData = await stage('userdata.create', () => mkdtemp(path.join(os.tmpdir(), 'narrative-ide-repair-only-')));

    const page = await launch(rendererUrl, userData);
    await openOriginalProject(page);
    const beforeUi = await snapshot(page);
    assert.equal(beforeUi.proposals.length, 89, 'Original benchmark must begin with 89 proposals.');
    assert.deepEqual(pendingAndAccepted(beforeUi), { pending: 89, accepted: 0 }, 'Original benchmark must begin with 89 pending and zero accepted proposals.');
    assert.equal(beforeUi.proposalHistory.length, 0, 'Original benchmark must begin with empty proposal history.');

    await openPackage(page);
    const repairButton = page.locator('[data-testid^="repair-blocked-package-"]');
    const acceptButton = page.locator('[data-testid^="accept-import-package-"]');
    await waitForVisible(repairButton, 'repair.visible');
    assert.equal(await repairButton.count(), 1, 'Expected exactly one blocked package Repair action.');
    assert.equal(await acceptButton.count(), 0, 'Accept must not be visible before repair.');
    log('repair.click', await repairButton.getAttribute('data-testid'));
    await stage('repair.only', () => repairButton.click());
    await waitForVisible(acceptButton, 'repair.accept-visible');

    const afterRepair = await snapshot(page);
    assert.deepEqual(afterRepair.canonicalCounts, beforeUi.canonicalCounts, 'Repair changed in-memory canonical collections.');
    assert.deepEqual(pendingAndAccepted(afterRepair), { pending: 89, accepted: 0 }, 'Repair changed proposal pending/accepted status.');
    assert.equal(afterRepair.proposalHistory.length, 0, 'Repair created proposal history.');
    assert(afterRepair.proposals.every((proposal) => proposal.lastBlockReason === null), 'Repair did not clear every lastBlockReason.');
    receipt.repair = {
      descriptorVerification: assertArtifactRefV2(afterRepair),
      projection: await inspectProjection(),
      transaction: await inspectTransaction(),
      screenshot: path.join(EVIDENCE_ROOT, 'repair-only-package-valid.png'),
    };
    await stage('screenshot.repair-only', () => page.screenshot({ path: receipt.repair.screenshot, fullPage: true }));
    // Deliberately no Accept interaction: visibility is the final UI assertion before restart.
    await closeApp();

    const restartPage = await launch(rendererUrl, userData);
    await openOriginalProject(restartPage);
    await openPackage(restartPage);
    const afterRestart = await snapshot(restartPage);
    assert.equal(afterRestart.proposals.length, 89, 'Restart lost pending proposals.');
    assert.deepEqual(pendingAndAccepted(afterRestart), { pending: 89, accepted: 0 }, 'Restart changed proposal pending/accepted status.');
    assert.equal(afterRestart.proposalHistory.length, 0, 'Restart created proposal history.');
    assert(afterRestart.proposals.every((proposal) => proposal.lastBlockReason === null), 'Restart restored lastBlockReason.');
    assertArtifactRefV2(afterRestart);
    assert.equal(await restartPage.locator('[data-testid^="accept-import-package-"]').count(), 1, 'Restarted package is not valid with explicit Accept visible.');
    await closeApp();

    receipt.after = {
      canonicalInventory: await stage('inventory.after.canonical', captureCanonicalInventory),
      inboxSha256: sha256(await readFile(path.join(PROJECT_ROOT, 'system', 'inbox.json'))),
      stagedProjectionSha256: sha256(await readFile(STAGED_PROJECTION)),
      restart: { proposals: afterRestart.proposals.length, ...pendingAndAccepted(afterRestart), proposalHistory: afterRestart.proposalHistory.length, explicitAcceptVisible: true },
    };
    assert.deepEqual(receipt.after.canonicalInventory, receipt.before.canonicalInventory, 'Repair changed canonical character/chapter/scene/timeline/world/manuscript files.');
    receipt.status = 'passed';
  } catch (error) {
    receipt.status = 'failed';
    receipt.error = String(error?.stack || error);
    throw error;
  } finally {
    clearTimeout(totalTimer);
    try { await closeApp(); } catch (closeError) { receipt.closeError = String(closeError); }
    if (resources.vite) await resources.vite.close();
    receipt.finishedAt = new Date().toISOString();
    await mkdir(EVIDENCE_ROOT, { recursive: true });
    await writeFile(path.join(EVIDENCE_ROOT, 'repair-only-receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`);
  }
}

await main();
