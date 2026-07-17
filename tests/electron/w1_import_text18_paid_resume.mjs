import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { cp, mkdir, mkdtemp, readFile, readdir, realpath, rm, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { _electron as electron } from 'playwright';
import { createServer as createViteServer } from 'vite';

// This runner has no implicit paid path. `--execute-paid` is intentionally required.
const REPO_ROOT = process.cwd();
const PROJECT_ROOT = "/Volumes/migodam's-external-brain/home/narrative_ide/import_test18";
const EXPECTED_SOURCE_HASH = '6c7cfd49949e89cecb8b00a4bd9ab374e7393ff1b4fe84a0e8a809e060cb522d';
const EXPECTED_MODEL = 'deepseek-v4-flash';
const MAX_COST_USD = 3;
const SOURCE_PATH = "/Volumes/migodam's-external-brain/home/narrative_ide/novels/凡人修仙传_前10章.txt";
const IMPORT_ID = 'import_a684a04d162f';
const IMPORT_ROOT = path.join(PROJECT_ROOT, 'system', 'imports', IMPORT_ID);
const CHECKPOINT_PATH = path.join(PROJECT_ROOT, 'import_progress.json');
const MANIFEST_PATH = path.join(IMPORT_ROOT, 'manifest.json');
const SETTINGS_FILE = 'narrative-ide-app-settings.json';
const POLL_INTERVAL_MS = 1_000;
const HARD_WALL_CLOCK_TIMEOUT_MS = 20 * 60_000;
const STATIC_ONLY = !process.argv.includes('--execute-paid');
const RECONCILE_ONLY = process.argv.includes('--reconcile-only');
const startedAt = Date.now();
const resources = { app: null, vite: null, page: null, closing: false };
let reconcileUserData = null;
let receiptDirectory = null;
let resumeInvocations = 0;

const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const log = (stage, message) => console.log(`[w1-import-text18-paid-resume +${Date.now() - startedAt}ms] ${stage}: ${message}`);

function requireSafeString(value, label) {
  assert.equal(typeof value, 'string', `${label} must be a string`);
  assert(value.length > 0, `${label} must not be empty`);
  return value;
}

async function stage(name, operation, timeoutMs = HARD_WALL_CLOCK_TIMEOUT_MS) {
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

function sanitizedError(error) {
  return String(error?.message || error)
    .replaceAll(PROJECT_ROOT, '<project>')
    .replaceAll(SOURCE_PATH, '<source>');
}

function noCredentialEnv() {
  return Object.fromEntries(Object.entries(process.env).filter(([key]) => !/(api[_-]?key|openai|deepseek|anthropic|gemini)/i.test(key)));
}

async function existingFile(file, label) {
  const details = await stat(file).catch(() => null);
  assert(details?.isFile(), `${label} is missing: ${file}`);
}

async function readJson(file, label) {
  await existingFile(file, label);
  try {
    return JSON.parse(await readFile(file, 'utf8'));
  } catch (error) {
    throw new Error(`${label} is not valid JSON: ${sanitizedError(error)}`);
  }
}

function assertNoUnknownCalls(run) {
  assert(Array.isArray(run.unknown_calls), 'runtime response did not expose unknown_calls');
  assert.equal(run.unknown_calls.length, 0, 'unknown_outcome calls must be empty; this runner never authorizes them');
}

function assertBudget(config) {
  const budget = config?.budget_config;
  assert(budget && typeof budget === 'object', 'missing durable budget_config');
  assert.equal(budget.max_cost_usd, MAX_COST_USD, `max_cost_usd must be exactly ${MAX_COST_USD}`);
  assert.equal(budget.fail_on_unknown_pricing, true, 'fail_on_unknown_pricing must be enabled');
  assert.equal(budget.fail_on_missing_usage, true, 'fail_on_missing_usage must be enabled');
}

async function staticPreflight() {
  const [checkpoint, manifest] = await Promise.all([
    readJson(CHECKPOINT_PATH, 'checkpoint'),
    readJson(MANIFEST_PATH, 'import manifest'),
  ]);
  await Promise.all([
    existingFile(SOURCE_PATH, 'original source'),
    existingFile(path.join(IMPORT_ROOT, 'raw_source.txt'), 'project raw source'),
    existingFile(path.join(PROJECT_ROOT, 'project.db'), 'project database'),
  ]);
  const [sourceHash, rawSourceHash] = await Promise.all([
    readFile(SOURCE_PATH).then(sha256),
    readFile(path.join(IMPORT_ROOT, 'raw_source.txt')).then(sha256),
  ]);
  assert.equal(sourceHash, EXPECTED_SOURCE_HASH, 'original source hash changed');
  assert.equal(rawSourceHash, EXPECTED_SOURCE_HASH, 'project raw source hash changed');
  assert.equal(manifest.source_hash, EXPECTED_SOURCE_HASH, 'manifest source hash changed');
  assert.equal(manifest.model, EXPECTED_MODEL, 'manifest model changed');
  assert.equal(checkpoint.total_chunks, 10, 'checkpoint must describe ten chunks');
  assert.deepEqual([...checkpoint.completed_chunk_ids].sort((a, b) => a - b), [0, 1, 2, 3], 'checkpoint must contain exactly the trusted 4/10 prefix');
  assert.equal(checkpoint.chunk_extractions?.length, 4, 'checkpoint must contain exactly four chunk extractions');
  return { checkpoint, manifest, sourceHash, rawSourceHash };
}

async function copyIfPresent(source, destination) {
  const details = await stat(source).catch(() => null);
  if (!details?.isFile()) return null;
  await cp(source, destination, { force: false, preserveTimestamps: true });
  return path.basename(destination);
}

async function preflightBackup() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  receiptDirectory = path.join(os.homedir(), 'narrative-ide-recovery-receipts', `import-text18-${stamp}`);
  const projectBackup = path.join(receiptDirectory, 'project-before-resume');
  await mkdir(receiptDirectory, { recursive: true });
  await stage('backup.project', () => cp(PROJECT_ROOT, projectBackup, { recursive: true, force: false, preserveTimestamps: true }), HARD_WALL_CLOCK_TIMEOUT_MS);
  const checkpointBackup = path.join(receiptDirectory, 'import_progress.before-resume.json');
  await stage('backup.checkpoint', () => cp(CHECKPOINT_PATH, checkpointBackup, { force: false, preserveTimestamps: true }));
  return { projectBackup, checkpointBackup, runtimeDatabaseBackups: [] };
}

async function backupRuntimeDatabases(backup) {
  const runtimeRoot = path.join(PROJECT_ROOT, 'system', 'runtime');
  const names = await readdir(runtimeRoot).catch(() => []);
  const candidates = [
    path.join(PROJECT_ROOT, 'project.db'),
    path.join(PROJECT_ROOT, 'project.db-wal'),
    path.join(PROJECT_ROOT, 'project.db-shm'),
    ...names.filter((name) => /\.db(?:-wal|-shm)?$/).map((name) => path.join(runtimeRoot, name)),
  ];
  const copied = [];
  for (const source of candidates) {
    const destination = path.join(receiptDirectory, `runtime-before-resume-${path.basename(source)}`);
    const name = await copyIfPresent(source, destination);
    if (name) copied.push(name);
  }
  assert(copied.some((name) => name.includes('.db')), 'no runtime/project SQLite database was backed up');
  backup.runtimeDatabaseBackups = copied;
}

async function closeApp() {
  const app = resources.app;
  resources.app = null;
  if (!app) return;
  resources.closing = true;
  const child = app.process();
  try {
    await stage('electron.close', async () => {
      if (!child || child.exitCode !== null) return;
      const exited = once(child, 'exit');
      void app.evaluate(({ app: electronApp }) => electronApp.quit()).catch(() => {});
      if (child.exitCode === null) await exited;
    }, 15_000);
  } catch {
    try { child?.kill('SIGKILL'); } catch { /* bounded cleanup */ }
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
    await vite.close();
  }
  if (reconcileUserData) {
    await rm(reconcileUserData, { recursive: true, force: true }).catch(() => {});
    reconcileUserData = null;
  }
}

async function launch(userData) {
  resources.vite = await stage('vite.create', () => createViteServer({ root: REPO_ROOT, logLevel: 'error', server: { host: '127.0.0.1', port: 0 } }), 60_000);
  await stage('vite.listen', () => resources.vite.listen(), 60_000);
  const rendererUrl = resources.vite.resolvedUrls?.local?.[0];
  assert(rendererUrl, 'Vite did not expose a local renderer URL');
  resources.app = await stage('electron.launch', () => electron.launch({
    args: ['.'], cwd: REPO_ROOT,
    // Credentials must come only from the supplied Electron settings profile.
    env: { ...noCredentialEnv(), NARRATIVE_IDE_RENDERER_URL: rendererUrl, NARRATIVE_IDE_USER_DATA: userData, NARRATIVE_IDE_RUNTIME_SMOKE: '1', NARRATIVE_IDE_SMOKE_PROJECT_ROOT: PROJECT_ROOT },
  }), 60_000);
  const page = await stage('electron.first-window', () => resources.app.firstWindow(), 60_000);
  resources.page = page;
  page.on('dialog', (dialog) => (resources.closing ? dialog.accept() : dialog.dismiss()).catch(() => {}));
  await stage('renderer.ready', () => page.waitForSelector('[data-testid="activity-btn-workbench"]'), 60_000);
  return page;
}

async function openProject(page) {
  await stage('project.open', () => page.getByTestId('toolbar-open-project').click(), 60_000);
  await stage('project.dialog', () => page.getByTestId('project-dialog').waitFor({ state: 'visible' }), 60_000);
  await stage('project.pick', () => page.getByTestId('project-folder-pick').click(), 60_000);
  const folder = page.getByTestId('project-folder-input');
  await stage('project.selected', () => folder.waitFor({ state: 'visible' }), 60_000);
  assert.equal(await folder.inputValue(), await realpath(PROJECT_ROOT), 'Electron did not select Import Text 18');
  await stage('project.submit', () => page.getByTestId('project-dialog-submit').click(), 60_000);
  await stage('project.loaded', () => page.getByTestId('project-dialog').waitFor({ state: 'hidden' }), 60_000);
}

async function waitForRecoverable(page) {
  let result = null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    result = await page.evaluate((root) => window.narrativeIDE.runtimeRecoverable({ projectRoot: root }), PROJECT_ROOT);
    if (Array.isArray(result?.runs)) return result;
    if (attempt === 20) await page.evaluate((root) => window.narrativeIDE.sidecarSpawn({ projectRoot: root }), PROJECT_ROOT);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`runtime recovery bridge did not become ready: ${sanitizedError(result?.error || 'unknown')}`);
}

async function assertSelectedModel(userData) {
  const settings = await readJson(path.join(userData, SETTINGS_FILE), 'Electron settings');
  const profiles = Array.isArray(settings.modelProfiles) ? settings.modelProfiles : [];
  const selected = profiles.find((profile) => profile?.id === settings.selectedModelProfileId) ?? profiles[0];
  assert.equal(selected?.model, EXPECTED_MODEL, `selected Electron model must be ${EXPECTED_MODEL}`);
  const providers = Array.isArray(settings.providerProfiles) ? settings.providerProfiles : [];
  const provider = providers.find((profile) => profile?.id === settings.selectedProviderProfileId) ?? providers[0];
  assert.equal(provider?.provider, 'deepseek', 'selected Electron provider must be deepseek');
  assert(typeof provider?.apiKey === 'string' && provider.apiKey.length > 0, 'selected provider credentials are missing');
  // Do not return, log, serialize, or otherwise expose the credential.
  return { model: selected.model, provider: typeof provider.provider === 'string' ? provider.provider : null };
}

async function runReconcileOnly() {
  reconcileUserData = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-reconcile-'));
  const page = await launch(reconcileUserData);
  await openProject(page);
  const inventory = await waitForRecoverable(page);
  assert.equal(inventory?.error, undefined, `runtime recoverable request failed: ${sanitizedError(inventory?.error)}`);
  assert.equal(inventory.runs?.length, 1, 'expected exactly one recoverable Import Text 18 run');
  const run = inventory.runs[0];
  assert.equal(run.status, 'interrupted', 'cold start must interrupt the expired attempt');
  assert.equal(run.unknown_calls?.length, 1, 'cold start must expose exactly one pending unknown outcome');
  assert.equal(run.unknown_calls[0].decision_state, 'pending', 'unknown outcome must remain human-gated');
  assert.equal(run.config?.completed_chunks, 4, 'cold start must preserve 4 completed chunks');
  assert.equal(run.config?.total_chunks, 10, 'cold start must preserve 10 total chunks');
  const detail = await page.evaluate(({ root, lineage }) => window.narrativeIDE.runtimeRun({ projectRoot: root, lineage_id: lineage }), { root: PROJECT_ROOT, lineage: run.lineage_id });
  const attempt = detail?.attempt ?? detail?.attempts?.find((item) => item.attempt_id === run.attempt_id);
  assert.equal(attempt?.status, 'interrupted', 'runtime detail must remain interrupted');
  assert.equal(attempt?.unknown_calls?.length ?? detail?.unknown_calls?.length, 1, 'runtime detail must retain one unknown outcome');
  const checkpoint = await readJson(CHECKPOINT_PATH, 'import progress checkpoint');
  assert.deepEqual([...checkpoint.completed_chunk_ids].sort((a, b) => a - b), [0, 1, 2, 3], 'checkpoint must remain at 4/10');
  assert.equal(resumeInvocations, 0, 'reconcile-only must never invoke runtimeResume');
  log('result', 'RECONCILE-ONLY PASS; real sidecar cold start observed interrupted + one pending unknown_outcome, checkpoint preserved at 4/10, no settings/API key read, and no resume invoked.');
}

function assertRecoverableRun(result) {
  assert.equal(result?.error, undefined, `runtime recoverable request failed: ${sanitizedError(result?.error)}`);
  assert.equal(result.runs?.length, 1, 'expected exactly one recoverable Import Text 18 run');
  const run = result.runs[0];
  assert.equal(run.status, 'interrupted', 'recovery must start interrupted and must not auto-resume');
  assert.equal(run.config?.completed_chunks, 4, 'runtime must report 4 completed chunks');
  assert.equal(run.config?.total_chunks, 10, 'runtime must report 10 total chunks');
  assert.equal(run.source_compatible, true, 'runtime source is incompatible');
  assert.equal(run.config?.source_hash, EXPECTED_SOURCE_HASH, 'runtime source hash differs from approved source');
  assertBudget(run.config);
  assertNoUnknownCalls(run);
  return run;
}

function eventText(event) {
  return JSON.stringify({ event_type: event?.event_type, payload: event?.payload || {} }).toLowerCase();
}

function assertNoFatalEvent(events) {
  for (const event of events) {
    const text = eventText(event);
    if (/unknown_outcome|waiting_human|needs_credentials|missing_usage|usage.*missing|budget_exhausted|max_cost_usd|source_incompatible|source.*mismatch|authorization|unauthori[sz]ed/.test(text)) {
      throw new Error(`durable runtime event stopped the recovery: ${event.event_type || 'unknown'}`);
    }
  }
}

async function monitorCompletion(page, attemptId) {
  let sequence = 0;
  const events = [];
  const deadline = Date.now() + HARD_WALL_CLOCK_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const eventResult = await page.evaluate(({ root, attempt, after }) => window.narrativeIDE.runtimeEvents({ projectRoot: root, attempt_id: attempt, after_sequence: after }), { root: PROJECT_ROOT, attempt: attemptId, after: sequence });
    if (eventResult?.error) throw new Error(`durable event polling failed: ${sanitizedError(eventResult.error)}`);
    for (const event of eventResult?.events || []) {
      assert(Number.isSafeInteger(event.sequence) && event.sequence > sequence, 'durable events must have increasing sequence numbers');
      sequence = event.sequence;
      events.push(event);
    }
    assertNoFatalEvent(events);
    const detail = await page.evaluate(({ root, attempt }) => window.narrativeIDE.runtimeRun({ projectRoot: root, lineage_id: attempt }), { root: PROJECT_ROOT, attempt: attemptId });
    const attempt = detail?.attempt ?? detail?.attempts?.find((item) => item.attempt_id === attemptId);
    const status = attempt?.status;
    const unknownCalls = attempt?.unknown_calls ?? detail?.unknown_calls ?? [];
    assert.equal(unknownCalls.length, 0, 'unknown outcome appeared after resume; runner will not authorize it');
    if (['needs_credentials', 'waiting_human', 'failed', 'cancelled', 'error'].includes(status)) throw new Error(`recovery stopped with status=${status}`);
    if (status === 'completed') return { detail, events, finalAttempt: attempt };
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  throw new Error(`hard wall-clock timeout after ${HARD_WALL_CLOCK_TIMEOUT_MS}ms`);
}

async function verifyCompletion(page, run, monitor) {
  const attemptId = run.attempt_id;
  const attemptRoot = path.join(PROJECT_ROOT, 'system', 'imports', run.lineage_id, 'attempts', attemptId);
  const ledger = await readJson(path.join(attemptRoot, 'usage_ledger.json'), 'usage ledger');
  assert.equal(ledger.model, EXPECTED_MODEL, 'usage ledger model differs from approved model');
  assert.equal(typeof ledger.actual_calls, 'number', 'usage ledger is missing actual_calls');
  assert(ledger.actual_calls > 0, 'usage ledger has no provider calls');
  assert.equal(typeof ledger.cost_usd, 'number', 'usage ledger is missing cost_usd');
  assert(ledger.cost_usd >= 0 && ledger.cost_usd <= MAX_COST_USD, 'usage ledger cost is outside the approved budget');
  assert.equal(ledger.budget_status?.exhausted, false, 'usage ledger reports budget exhaustion');
  const checkpoint = await readJson(CHECKPOINT_PATH, 'completed checkpoint');
  const trustedChunks = [...checkpoint.completed_chunk_ids].sort((a, b) => a - b);
  assert.equal(checkpoint.total_chunks, 10, 'completed checkpoint total must remain 10');
  assert.deepEqual(trustedChunks, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 'completion must have the trustworthy 10/10 contiguous chunk prefix');
  assert.equal(checkpoint.chunk_extractions?.length, 10, 'completion must include ten persisted chunk extractions');
  const rawHash = sha256(await readFile(path.join(IMPORT_ROOT, 'raw_source.txt')));
  assert.equal(rawHash, EXPECTED_SOURCE_HASH, 'raw source changed during recovery');
  // Reload only to observe the persisted proposal gate. No package action is invoked.
  await stage('proposal-gate.reload', () => page.reload(), 60_000);
  await stage('proposal-gate.renderer-ready', () => page.waitForSelector('[data-testid="activity-btn-workbench"]'), 60_000);
  await openProject(page);
  const proposalState = await page.evaluate(() => {
    const state = window.__narrativeStore.getState();
    return {
      pending: state.proposals.filter((proposal) => !proposal.status || proposal.status === 'pending').length,
      accepted: state.proposals.filter((proposal) => proposal.status === 'accepted').length,
    };
  });
  assert.equal(proposalState.accepted, 0, 'runner must never accept an import package');
  assert(proposalState.pending > 0, 'proposal gate must retain pending proposals after recovery');
  return { ledger, trustedChunks, proposalState, durableEventCount: monitor.events.length };
}

async function writeReceipt({ backup, run, model, completion }) {
  const receipt = {
    status: 'PASS', mode: 'paid_resume', completed_at: new Date().toISOString(),
    project: 'import_test18', source_sha256: EXPECTED_SOURCE_HASH, model,
    max_cost_usd: MAX_COST_USD, actual_calls: completion.ledger.actual_calls, cost_usd: completion.ledger.cost_usd,
    completed_chunks: completion.trustedChunks.length, total_chunks: 10,
    proposal_gate: { pending: completion.proposalState.pending, accepted: completion.proposalState.accepted },
    durable_event_count: completion.durableEventCount,
    backup: { project: path.basename(backup.projectBackup), checkpoint: path.basename(backup.checkpointBackup), runtime_databases: backup.runtimeDatabaseBackups },
    // No API key, source body, checkpoint body, or manuscript text belongs in this receipt.
  };
  await writeFile(path.join(receiptDirectory, 'receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 });
  return receipt;
}

async function main() {
  const preflight = await stage('static.preflight', staticPreflight, 60_000);
  log('static.preflight', `PASS source_sha256=${preflight.sourceHash} completed=4/10`);
  if (RECONCILE_ONLY) {
    try {
      await runReconcileOnly();
    } finally {
      await cleanup();
    }
    return;
  }
  if (STATIC_ONLY) {
    log('result', 'STATIC PASS; no Electron process, provider credential, runtime resume, or paid provider call was used. Re-run with --execute-paid and NARRATIVE_IDE_PAID_RESUME_USER_DATA=<Electron user-data directory> to opt in.');
    return;
  }

  const userData = requireSafeString(process.env.NARRATIVE_IDE_PAID_RESUME_USER_DATA, 'NARRATIVE_IDE_PAID_RESUME_USER_DATA');
  const backup = await preflightBackup();
  try {
    const selected = await assertSelectedModel(userData);
    const page = await launch(userData);
    await openProject(page);
    const inventory = await waitForRecoverable(page);
    const run = assertRecoverableRun(inventory);
    await backupRuntimeDatabases(backup);

    assert.equal(resumeInvocations, 0, 'resume was already invoked');
    resumeInvocations += 1;
    const resumed = await stage('runtime.resume.once', () => page.evaluate(({ root, attempt }) => window.narrativeIDE.runtimeResume({ projectRoot: root, attempt_id: attempt }), { root: PROJECT_ROOT, attempt: run.attempt_id }), 60_000);
    assert.equal(resumeInvocations, 1, 'runner must invoke resume exactly once');
    assert.equal(resumed?.status, 'resumed', `resume was not accepted: ${sanitizedError(resumed?.error || resumed?.status)}`);
    assert.equal(resumed?.restarted, true, 'resume did not launch exactly one recovered worker');

    const monitor = await monitorCompletion(page, run.attempt_id);
    const completion = await verifyCompletion(page, run, monitor);
    await writeReceipt({ backup, run, model: selected.model, completion });
    log('result', `PAID PASS receipt=${path.join(receiptDirectory, 'receipt.json')}`);
  } catch (error) {
    if (receiptDirectory) {
      const failure = { status: 'FAIL', completed_at: new Date().toISOString(), project: 'import_test18', source_sha256: EXPECTED_SOURCE_HASH, resume_invocations: resumeInvocations, error: sanitizedError(error) };
      await writeFile(path.join(receiptDirectory, 'failure.json'), `${JSON.stringify(failure, null, 2)}\n`, { mode: 0o600 }).catch(() => {});
      log('failure.receipt', path.join(receiptDirectory, 'failure.json'));
    }
    throw error;
  } finally {
    await cleanup();
  }
}

main().catch((error) => {
  console.error(`[w1-import-text18-paid-resume] FAIL: ${sanitizedError(error)}`);
  process.exitCode = 1;
});
