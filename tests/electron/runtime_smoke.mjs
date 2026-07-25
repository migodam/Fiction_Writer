import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { once } from 'node:events';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, mkdir, readFile, realpath, rename, rm, symlink, unlink, writeFile } from 'node:fs/promises';
import { _electron as electron } from 'playwright';
import { createServer as createViteServer } from 'vite';

const fixture = `<!doctype html>
<html><body><button id="target">target</button><output id="result"></output>
<script>
  document.getElementById('target').addEventListener('contextmenu', (event) => {
    event.preventDefault();
    document.getElementById('result').textContent = 'context-menu-received';
  });
</script></body></html>`;

const startedAt = process.hrtime.bigint();
const resources = { app: undefined, vite: undefined, sidecarPid: undefined, sidecarPort: undefined, userData: undefined };
let cleanupPromise;

let providerModelsRequest;
const server = http.createServer((request, response) => {
  if (request.url === '/v1/models') {
    providerModelsRequest = { method: request.method, authorization: request.headers.authorization };
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ data: [{ id: 'model-a' }, { id: 'model-b' }] }));
    return;
  }
  if (request.url === '/v1/unauthorized/models') {
    response.writeHead(401, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: { message: 'invalid key' } }));
    return;
  }
  if (request.url === '/v1/rate-limited/models') {
    response.writeHead(429, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: { message: 'retry later' } }));
    return;
  }
  if (request.url === '/v1/server-error/models') {
    response.writeHead(503, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: { message: 'unavailable' } }));
    return;
  }
  if (request.url === '/v1/invalid/models') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ unexpected: true }));
    return;
  }
  response.writeHead(200, { 'content-type': 'text/html' });
  response.end(fixture);
});

const log = (stage, message) => {
  const elapsedMs = Number(process.hrtime.bigint() - startedAt) / 1e6;
  console.log(`[electron-smoke +${elapsedMs.toFixed(0)}ms] ${stage}: ${message}`);
};

const describeError = (error) => error instanceof Error ? `${error.name}: ${error.message}` : String(error);

async function runStage(stage, timeoutMs, operation) {
  log(stage, `start (timeout ${timeoutMs}ms)`);
  let timer;
  try {
    const result = await Promise.race([
      Promise.resolve().then(operation),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${stage} timed out after ${timeoutMs}ms`)), timeoutMs);
      }),
    ]);
    log(stage, 'complete');
    return result;
  } catch (error) {
    log(stage, `failed: ${describeError(error)}`);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function startManaged(stage, timeoutMs, start, dispose) {
  const startPromise = Promise.resolve().then(start);
  try {
    return await runStage(stage, timeoutMs, () => startPromise);
  } catch (error) {
    // A timed-out start may still resolve later; dispose it instead of orphaning a server or Electron child.
    startPromise.then((resource) => dispose(resource)).catch(() => {});
    throw error;
  }
}

async function listenWithTimeout(timeoutMs = 10_000) {
  await runStage('fixture-server.listen', timeoutMs, () => new Promise((resolve, reject) => {
    const onError = (error) => {
      reject(error);
    };
    server.once('error', onError);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', onError);
      resolve();
    });
  }));
}

async function closeServer() {
  if (!server.listening) return;
  server.closeAllConnections?.();
  await runStage('fixture-server.close', 10_000, () => new Promise((resolve, reject) => {
    server.close((error) => error ? reject(error) : resolve());
  }));
}

async function closeElectronApp(app, stage = 'electron.app.close') {
  if (!app) return;
  try {
    await runStage(stage, 9_000, async () => {
      const child = app.process();
      const exitPromise = once(child, 'exit');
      void app.evaluate(({ app: electronApp }) => electronApp.quit()).catch(() => {});
      await exitPromise;
    });
    const diagnostics = (await readFile(path.join(resources.userData, 'electron-lifecycle-smoke.jsonl'), 'utf8'))
      .trim().split('\n').map((line) => JSON.parse(line));
    const shutdown = diagnostics.findLast((entry) => entry.event === 'shutdown-complete');
    assert(shutdown, 'Missing shutdown-complete lifecycle diagnostic');
    assert.equal(shutdown.sidecars, 0);
    assert.equal(shutdown.runtimeStreams, 0);
    assert.equal(shutdown.workflowStreams, 0);
    if (resources.sidecarPid) {
      let alive = false;
      try {
        process.kill(resources.sidecarPid, 0);
        alive = true;
      } catch (error) {
        if (error?.code !== 'ESRCH') throw error;
      }
      assert.equal(alive, false, `Sidecar child ${resources.sidecarPid} survived Electron quit`);
    }
  } catch (error) {
    const child = app.process();
    try {
      const diagnostics = await readFile(path.join(resources.userData, 'electron-lifecycle-smoke.jsonl'), 'utf8');
      log(stage, `main lifecycle diagnostics: ${diagnostics.trim()}`);
    } catch { /* diagnostics unavailable */ }
    log(stage, `forcing process termination after close failure (pid ${child?.pid ?? 'unknown'})`);
    try { child?.kill('SIGKILL'); } catch (killError) { log(stage, `force kill failed: ${describeError(killError)}`); }
    throw error;
  }
}

async function closeElectron() {
  const app = resources.app;
  resources.app = undefined;
  await closeElectronApp(app);
}

async function closeViteInstance(vite, stage = 'vite.close') {
  if (!vite) return;
  vite.httpServer?.closeAllConnections?.();
  await runStage(stage, 15_000, () => vite.close());
}

async function closeVite() {
  const vite = resources.vite;
  resources.vite = undefined;
  await closeViteInstance(vite);
}

async function cleanup(tempDirectories = []) {
  if (cleanupPromise) return cleanupPromise;
  cleanupPromise = (async () => {
    log('cleanup', 'start');
    let electronCloseError;
    try {
      await closeElectron();
    } catch (error) {
      electronCloseError = error;
    }
    try {
      await closeVite();
    } catch (error) {
      log('vite.close', `ignored cleanup failure: ${describeError(error)}`);
    }
    try {
      await closeServer();
    } catch (error) {
      log('fixture-server.close', `ignored cleanup failure: ${describeError(error)}`);
    }
    for (const directory of tempDirectories) {
      try {
        await runStage(`cleanup.rm ${path.basename(directory)}`, 15_000, () => rm(directory, { recursive: true, force: true }));
      } catch (error) {
        log('cleanup', `ignored removal failure for ${directory}: ${describeError(error)}`);
      }
    }
    log('cleanup', 'complete');
    if (electronCloseError) throw electronCloseError;
  })();
  return cleanupPromise;
}

function runRuntimeFixture(stage, script, args = []) {
  const python = path.join(process.cwd(), 'sidecar', '.venv', 'bin', 'python');
  const result = spawnSync(python, ['-c', script, ...args], {
    cwd: process.cwd(),
    encoding: 'utf8',
    timeout: 20_000,
  });
  assert.equal(result.status, 0, `${stage} failed: ${result.stderr || result.stdout}`);
  return JSON.parse(result.stdout);
}

const resumableRuntimeFixtureScript = String.raw`
import hashlib
import json
import sqlite3
import sys

from sidecar.models.state import make_source_span
from sidecar.runtime.agent_runtime import RuntimeStore
from sidecar.runtime.w1_supervisor_snapshot import write_w1_supervisor_snapshot
from sidecar.supervisor import policy
from sidecar.workflows.w1_agentic_adapter import build_supervisor_snapshot_identities

project = sys.argv[1]
source_text = "第1章\\n韩立进入七玄门。\\n"
source_path = f"{project}/runtime-smoke-source.txt"
with open(source_path, "w", encoding="utf-8") as handle:
    handle.write(source_text)
source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
store = RuntimeStore(project)
run = store.create_run(
    workflow_id="W1",
    lineage_id="electron-runtime-lineage",
    thread_id="electron-runtime-thread",
    config={
        "project_path": project,
        "source_file_path": source_path,
        "source_hash": source_hash,
        "model": "deepseek-v4-flash",
        "profile": "balanced",
        "prompt_profile": "balanced",
        "execution_mode": "supervisor",
        "import_mode": "import_all",
        "budget_config": {"max_cost_usd": 3.0},
    },
)
attempt = store.create_attempt(run["run_id"], attempt_id="electron-runtime-parent")
lease = store.acquire_lease(attempt["attempt_id"], "electron-runtime-fixture", ttl_seconds=60)
staged_relative = "system/imports/electron-runtime-lineage/attempts/electron-runtime-parent/raw_source.txt"
staged_path = f"{project}/{staged_relative}"
import os
os.makedirs(os.path.dirname(staged_path), exist_ok=True)
with open(staged_path, "w", encoding="utf-8") as handle:
    handle.write(source_text)
span = make_source_span(source_text, 0, len(source_text))
state = policy._snapshot_state({
    "source_text": source_text,
    "import_run_id": "electron-runtime-import",
    "source_language": "zh",
    "chunks": [{"chunk_id": 0, "source_span": span, "content": source_text}],
    "chunk_extractions": [],
    "entity_registry": {"characters": {}, "events": {}, "world": {}, "world_detailed": {}},
    "relationships": [], "raw_relationships": [], "character_tags": [],
    "world_settings": {}, "world_containers": [], "organizer_output": {},
    "timeline_architecture": {}, "timeline_branches": [], "reducer_artifact": {},
    "import_review_report": {}, "judge_artifact": {}, "gate_failures": [],
    "manuscript_chapters": [], "proposals": [], "evidence_cards": [],
    "import_run_manifest": {"import_run_id": "electron-runtime-import"},
    "project_structure_digest": {},
})
config = {
    "project_path": project, "source_file_path": source_path, "source_hash": source_hash,
    "model": "deepseek-v4-flash", "prompt_profile": "balanced",
    "execution_mode": "supervisor", "import_mode": "import_all",
    "budget_config": {"max_cost_usd": 3.0},
    "w1_supervisor_staged_source_relative_path": staged_relative,
}
source_identity, config_identity = build_supervisor_snapshot_identities(config, project_path=project)
checkpoint_id = "electron-runtime-checkpoint"
reference = write_w1_supervisor_snapshot(
    project, lineage_id=run["lineage_id"], attempt_id=attempt["attempt_id"],
    checkpoint_id=checkpoint_id, node="reduce_repair", next_node="architect_timeline",
    source_identity=source_identity, config_identity=config_identity, state=state,
    completed_nodes=["validate_file", "extract_window", "reduce_repair"],
    budget_snapshot={"budget_limit_usd": 3.0, "spent_usd": 0.0},
)
store.record_checkpoint_metadata(
    attempt["attempt_id"], checkpoint_id, node="reduce_repair", sequence=1,
    metadata={"recovery_mode": "resumable", "snapshot_ref": reference.to_dict(), "next_node": "architect_timeline"},
    owner_id="electron-runtime-fixture", fence_token=lease["fence_token"],
)
store.set_attempt_status(attempt["attempt_id"], "paused", owner_id="electron-runtime-fixture", fence_token=lease["fence_token"])
store.append_event(
    attempt["attempt_id"], "agent.progress", {"summary": "fixture-event-1"},
    owner_id="electron-runtime-fixture", fence_token=lease["fence_token"],
    idempotency_key="electron-runtime-event-1", contract_version="AgentEvent/v1",
    actor={"kind": "system", "id": "electron-runtime-fixture"},
)
with sqlite3.connect(store.database_path) as connection:
    connection.execute("DELETE FROM run_leases WHERE attempt_id = ?", (attempt["attempt_id"],))
print(json.dumps({"attempt_id": attempt["attempt_id"], "checkpoint_id": checkpoint_id, "lineage_id": run["lineage_id"]}))
`;

const appendRuntimeEventFixtureScript = String.raw`
import json
import sqlite3
import sys

from sidecar.runtime.agent_runtime import RuntimeStore

store = RuntimeStore(sys.argv[1])
attempt_id = sys.argv[2]
lease = store.acquire_lease(attempt_id, "electron-runtime-fixture", ttl_seconds=60)
event = store.append_event(
    attempt_id, "agent.progress", {"summary": "fixture-event-2"},
    owner_id="electron-runtime-fixture", fence_token=lease["fence_token"],
    idempotency_key="electron-runtime-event-2", contract_version="AgentEvent/v1",
    actor={"kind": "system", "id": "electron-runtime-fixture"},
)
with sqlite3.connect(store.database_path) as connection:
    connection.execute("DELETE FROM run_leases WHERE attempt_id = ?", (attempt_id,))
print(json.dumps({"sequence": event["sequence"], "event_id": event["event_id"]}))
`;

async function assertSidecarPortClosed(port) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1_000);
  try {
    await fetch(`http://127.0.0.1:${port}/health`, { signal: controller.signal });
    throw new Error(`Sidecar port ${port} remained reachable after Electron quit`);
  } catch (error) {
    if (error instanceof Error && error.message.includes('remained reachable')) throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  const userData = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-electron-smoke-'));
  resources.userData = userData;
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-electron-smoke-project-'));
  const unauthorizedRoot = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-electron-untrusted-project-'));
  const canonicalProjectRoot = await realpath(projectRoot);
  const portraitSourcePath = path.join(projectRoot, 'portrait-source.png');
  const unauthorizedPortraitPath = path.join(unauthorizedRoot, 'portrait-secret.png');
  const portraitSentinelPath = path.join(unauthorizedRoot, 'portrait-target-sentinel.png');
  try {
    await writeFile(portraitSourcePath, 'portrait-source');
    await writeFile(unauthorizedPortraitPath, 'portrait-secret');
    await writeFile(portraitSentinelPath, 'portrait-target-sentinel');
    await mkdir(path.join(projectRoot, 'characters', 'portraits'), { recursive: true });
    const canonicalPortraitSourcePath = await realpath(portraitSourcePath);
    await listenWithTimeout();
    resources.vite = await startManaged('vite.createServer', 20_000, () => createViteServer({
      root: process.cwd(),
      logLevel: 'error',
      server: { host: '127.0.0.1', port: 0 },
    }), (vite) => closeViteInstance(vite, 'vite.late-close'));
    await runStage('vite.listen', 20_000, () => resources.vite.listen());
    const address = server.address();
    assert(address && typeof address !== 'string', 'Electron smoke HTTP server did not expose a port');
    const rendererUrl = `http://127.0.0.1:${address.port}`;
    const viteUrl = resources.vite.resolvedUrls?.local?.[0];
    assert(viteUrl, 'Vite smoke server did not expose a local URL');

    resources.app = await startManaged('electron.launch', 30_000, () => electron.launch({
      args: ['.'],
      cwd: process.cwd(),
      env: {
        ...process.env,
        NARRATIVE_IDE_RUNTIME_SMOKE: '1',
        NARRATIVE_IDE_RENDERER_URL: rendererUrl,
        NARRATIVE_IDE_USER_DATA: userData,
        NARRATIVE_IDE_SMOKE_PROJECT_ROOT: projectRoot,
        NARRATIVE_IDE_SMOKE_SOURCE_PATH: portraitSourcePath,
      },
    }), (app) => closeElectronApp(app, 'electron.late-close'));
    const page = await runStage('electron.firstWindow', 30_000, () => resources.app.firstWindow());
    page.on('dialog', (dialog) => {
      log('electron.dialog', `${dialog.type()} dismissed`);
      dialog.dismiss().catch((error) => log('electron.dialog', `dismiss failed: ${describeError(error)}`));
    });
    await runStage('fixture-page.ready', 15_000, () => page.waitForSelector('#target', { timeout: 15_000 }));

  const runtime = await runStage('fixture-page.bridge-evaluate', 45_000, () => page.evaluate(async ({ expectedProjectRoot, untrustedProjectRoot, providerEndpoint, directModelsEndpoint, unauthorizedProviderEndpoint, rateLimitedProviderEndpoint, serverErrorProviderEndpoint, invalidProviderEndpoint }) => {
    const bridge = window.narrativeIDE;
    const files = await bridge.pickFiles({ multiple: false, filters: [{ name: 'Text', extensions: ['txt'] }] });
    const directory = await bridge.pickDirectory({ mode: 'open' });
    const bridgeDirectory = `${expectedProjectRoot}/bridge-smoke`;
    const bridgeFile = `${bridgeDirectory}/project.json`;
    const projectFileOperation = (name, operation) => {
      try {
        return operation();
      } catch (error) {
        throw new Error(`${name}: ${String(error)}`);
      }
    };
    projectFileOperation('mkdir', () => bridge.projectFileMkdir({ path: bridgeDirectory }));
    projectFileOperation('write first', () => bridge.projectFileWrite({ path: bridgeFile, data: '{"version":1}', encoding: 'utf8' }));
    projectFileOperation('write overwrite', () => bridge.projectFileWrite({ path: bridgeFile, data: '{"version":2}', encoding: 'utf8' }));
    const bridgeFileContents = projectFileOperation('read', () => bridge.projectFileRead({ path: bridgeFile }));
    let outsideFileError = '';
    try {
      bridge.projectFileWrite({ path: `${untrustedProjectRoot}/outside.json`, data: '{}', encoding: 'utf8' });
    } catch (error) {
      outsideFileError = String(error);
    }
    const saved = await bridge.saveAppSettings({ locale: 'en', density: 'compact' });
    const loaded = await bridge.loadAppSettings();
    const providerConnection = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: providerEndpoint, apiKey: 'smoke-secret-key' });
    const providerDirectModels = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: directModelsEndpoint, apiKey: 'smoke-secret-key' });
    const providerUnauthorized = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: unauthorizedProviderEndpoint, apiKey: 'smoke-secret-key' });
    const providerRateLimited = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: rateLimitedProviderEndpoint, apiKey: 'smoke-secret-key' });
    const providerServerError = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: serverErrorProviderEndpoint, apiKey: 'smoke-secret-key' });
    const providerInvalidResponse = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: invalidProviderEndpoint, apiKey: 'smoke-secret-key' });
    const providerUnsafeEndpoint = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: 'https://169.254.169.254/v1', apiKey: 'smoke-secret-key' });
    const providerInvalidEndpoint = await bridge.testProviderConnection({ provider: 'smoke-provider', endpoint: 'http://example.com/v1', apiKey: 'smoke-secret-key' });
    const [firstSpawn, secondSpawn, thirdSpawn] = await Promise.all([
      bridge.sidecarSpawn({ projectRoot: expectedProjectRoot }),
      bridge.sidecarSpawn({ projectRoot: expectedProjectRoot }),
      bridge.sidecarSpawn({ projectRoot: expectedProjectRoot }),
    ]);
    const runtimeRecoverable = await bridge.runtimeRecoverable({ projectRoot: expectedProjectRoot });
    const w1 = await bridge.w1Status({ projectRoot: expectedProjectRoot, session_id: 'w1 smoke/&?' });
    let unauthorizedError = '';
    try {
      await bridge.dbOpen({ projectRoot: untrustedProjectRoot });
    } catch (error) {
      unauthorizedError = String(error);
    }
    return {
      files,
      directory,
      saved,
      loaded,
      providerConnection,
      providerDirectModels,
      providerUnauthorized,
      providerRateLimited,
      providerServerError,
      providerInvalidResponse,
      providerUnsafeEndpoint,
      providerInvalidEndpoint,
      firstSpawn,
      secondSpawn,
      thirdSpawn,
      runtimeRecoverable,
      w1,
      unauthorizedError,
      bridgeFileContents,
      outsideFileError,
      hasNodeRequire: typeof window.require !== 'undefined',
      hasNodeProcess: typeof window.process !== 'undefined',
      bridgeKeys: Object.keys(bridge),
      sha256: bridge.sha256('abc'),
    };
  }, { expectedProjectRoot: projectRoot, untrustedProjectRoot: unauthorizedRoot, providerEndpoint: `http://127.0.0.1:${address.port}/v1`, directModelsEndpoint: `http://127.0.0.1:${address.port}/v1/models`, unauthorizedProviderEndpoint: `http://127.0.0.1:${address.port}/v1/unauthorized`, rateLimitedProviderEndpoint: `http://127.0.0.1:${address.port}/v1/rate-limited`, serverErrorProviderEndpoint: `http://127.0.0.1:${address.port}/v1/server-error`, invalidProviderEndpoint: `http://127.0.0.1:${address.port}/v1/invalid` }));

  assert.deepEqual(runtime.files, { canceled: false, paths: [canonicalPortraitSourcePath] });
  assert.deepEqual(runtime.directory, { canceled: false, path: canonicalProjectRoot });
  assert.equal(runtime.saved.locale, 'en');
  assert.equal(runtime.loaded.density, 'compact');
  assert.deepEqual(runtime.providerConnection, { ok: true, code: 'connected', message: 'Connection verified.', httpStatus: 200, latencyMs: runtime.providerConnection.latencyMs, modelCount: 2 });
  assert.equal(typeof runtime.providerConnection.latencyMs, 'number');
  assert.equal(runtime.providerDirectModels.code, 'connected');
  assert.equal(runtime.providerUnauthorized.code, 'authentication_failed');
  assert.equal(runtime.providerUnauthorized.httpStatus, 401);
  assert.equal(runtime.providerRateLimited.code, 'rate_limited');
  assert.equal(runtime.providerRateLimited.httpStatus, 429);
  assert.equal(runtime.providerRateLimited.retryable, true);
  assert.equal(runtime.providerServerError.code, 'server_error');
  assert.equal(runtime.providerServerError.httpStatus, 503);
  assert.equal(runtime.providerServerError.retryable, true);
  assert.equal(runtime.providerInvalidResponse.code, 'invalid_response');
  assert.equal(runtime.providerUnsafeEndpoint.code, 'unsafe_endpoint');
  assert.equal(runtime.providerInvalidEndpoint.code, 'invalid_endpoint');
  assert.equal(JSON.stringify(runtime.providerConnection).includes('smoke-secret-key'), false);
  assert.deepEqual(providerModelsRequest, { method: 'GET', authorization: 'Bearer smoke-secret-key' });
  assert.equal(runtime.firstSpawn.ok, true);
  assert.equal(runtime.secondSpawn.ok, true);
  assert.equal(runtime.thirdSpawn.ok, true);
  assert.equal(runtime.firstSpawn.port, runtime.secondSpawn.port);
  assert.equal(runtime.secondSpawn.port, runtime.thirdSpawn.port);
  assert.notEqual(runtime.runtimeRecoverable.error, 'sidecar_offline');
  assert.equal(runtime.w1.status, 'runtime-smoke');
  assert.equal(runtime.w1.projectRoot, canonicalProjectRoot);
  assert.match(runtime.w1.path, /^\/workflow\/w1\/status\?session_id=w1%20smoke%2F%26%3F$/);
  assert.match(runtime.unauthorizedError, /Unauthorized projectRoot/);
  assert.equal(runtime.bridgeFileContents, '{"version":2}');
  assert.match(runtime.outsideFileError, /escapes authorized root/);
  assert.equal(runtime.hasNodeRequire, false);
  assert.equal(runtime.hasNodeProcess, false);
  assert.equal(runtime.bridgeKeys.includes('invoke'), false);
  assert.equal(runtime.bridgeKeys.includes('send'), false);
  assert.equal(runtime.sha256, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');

  const projectIdentity = createHash('sha256').update(canonicalProjectRoot, 'utf8').digest('hex').slice(0, 40);
  const pidFile = path.join(os.homedir(), '.narrative-ide', 'processes', `${projectIdentity}.json`);
  resources.sidecarPid = JSON.parse(await readFile(pidFile, 'utf8')).pid;
  resources.sidecarPort = runtime.firstSpawn.port;
  assert.equal(typeof resources.sidecarPid, 'number');

  const resumableFixture = await runStage('runtime.seed-resumable-fixture', 30_000, () =>
    runRuntimeFixture('runtime resumable fixture', resumableRuntimeFixtureScript, [projectRoot]));
  const runtimeBridge = await runStage('fixture-page.runtime-bridge-real-api', 35_000, () => page.evaluate(async ({ projectRoot, attemptId, checkpointId }) => {
    const bridge = window.narrativeIDE;
    const recoverable = await bridge.runtimeRecoverable({ projectRoot });
    const checkpoints = await bridge.runtimeCheckpoints({ projectRoot, attempt_id: attemptId });
    const polled = await bridge.runtimeEvents({ projectRoot, attempt_id: attemptId, after_sequence: 0 });
    const events = [];
    const statuses = [];
    const unsubscribeEvents = bridge.onRuntimeEvent((message) => events.push(message));
    const unsubscribeStatuses = bridge.onRuntimeEventStreamStatus((message) => statuses.push(message));
    try {
      const subscription = await bridge.runtimeEventStreamSubscribe({
        projectRoot, attempt_id: attemptId, after_sequence: 0, subscription_id: 'electron-runtime-resume-1',
      });
      if (!subscription.ok) throw new Error(subscription.error || 'initial SSE subscription failed');
      const deadline = Date.now() + 10_000;
      while (!events.some((message) => message.event?.sequence === 1)) {
        if (Date.now() >= deadline) throw new Error('initial real SSE event missing');
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
      await bridge.runtimeEventStreamUnsubscribe({ subscription_id: 'electron-runtime-resume-1' });
    } finally {
      unsubscribeEvents();
      unsubscribeStatuses();
    }
    const fork = await bridge.runtimeFork({
      projectRoot, attempt_id: attemptId, checkpoint_id: checkpointId, decision_id: 'electron-runtime-fork-1',
    });
    return { recoverable, checkpoints, polled, events, statuses, fork };
  }, { projectRoot, attemptId: resumableFixture.attempt_id, checkpointId: resumableFixture.checkpoint_id }));
  assert.equal(runtimeBridge.recoverable.error, undefined, JSON.stringify(runtimeBridge.recoverable));
  assert(runtimeBridge.recoverable.runs.some((run) => run.attempt_id === resumableFixture.attempt_id), 'recoverable attempt must come from the real sidecar runtime API');
  assert.equal(runtimeBridge.checkpoints.error, undefined, JSON.stringify(runtimeBridge.checkpoints));
  assert.equal(runtimeBridge.checkpoints.checkpoints.length, 1);
  assert.equal(runtimeBridge.checkpoints.checkpoints[0].checkpoint_id, resumableFixture.checkpoint_id);
  assert.equal(runtimeBridge.polled.events.length, 1);
  assert.equal(runtimeBridge.polled.events[0].sequence, 1);
  assert(runtimeBridge.statuses.some((status) => status.status === 'open'), JSON.stringify(runtimeBridge.statuses));
  assert.deepEqual(runtimeBridge.events.map((message) => message.event.sequence), [1]);
  assert.equal(runtimeBridge.fork.error, undefined, JSON.stringify(runtimeBridge.fork));
  assert.equal(runtimeBridge.fork.fork_snapshot.resumable, true);
  assert.equal(runtimeBridge.fork.fork_snapshot.state_reference.kind, 'w1_supervisor_snapshot/v1');
  assert.equal(runtimeBridge.fork.fork_snapshot.state_reference.resumable, true);
  assert.equal(runtimeBridge.fork.fork_snapshot.snapshot_ref, undefined, 'snapshot ref must only exist in state_reference');
  assert.equal(runtimeBridge.fork.fork_snapshot.state_reference.snapshot_ref.checkpoint_id, resumableFixture.checkpoint_id);

  const secondEvent = await runStage('runtime.append-reconnect-event', 30_000, () =>
    runRuntimeFixture('runtime reconnect event', appendRuntimeEventFixtureScript, [projectRoot, resumableFixture.attempt_id]));
  assert(secondEvent.sequence > 1, 'fixture reconnect event must follow the initial durable event');
  const reconnectedBridge = await runStage('fixture-page.runtime-bridge-sse-reconnect', 30_000, () => page.evaluate(async ({ projectRoot, attemptId, reconnectCursor, expectedSequence }) => {
    const bridge = window.narrativeIDE;
    const replayed = [];
    const statuses = [];
    const unsubscribeEvents = bridge.onRuntimeEvent((message) => replayed.push(message));
    const unsubscribeStatuses = bridge.onRuntimeEventStreamStatus((message) => statuses.push(message));
    try {
      const subscription = await bridge.runtimeEventStreamSubscribe({
        projectRoot, attempt_id: attemptId, after_sequence: reconnectCursor, subscription_id: 'electron-runtime-resume-2',
      });
      if (!subscription.ok) throw new Error(subscription.error || 'reconnect SSE subscription failed');
      const deadline = Date.now() + 10_000;
      while (!replayed.some((message) => message.event?.sequence === expectedSequence)) {
        if (Date.now() >= deadline) throw new Error('reconnected real SSE event missing');
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
      const polled = await bridge.runtimeEvents({ projectRoot, attempt_id: attemptId, after_sequence: reconnectCursor });
      await bridge.runtimeEventStreamUnsubscribe({ subscription_id: 'electron-runtime-resume-2' });
      return { replayed, statuses, polled };
    } finally {
      unsubscribeEvents();
      unsubscribeStatuses();
    }
  }, { projectRoot, attemptId: resumableFixture.attempt_id, reconnectCursor: secondEvent.sequence - 1, expectedSequence: secondEvent.sequence }));
  assert(reconnectedBridge.statuses.some((status) => status.status === 'open'), JSON.stringify(reconnectedBridge.statuses));
  assert.deepEqual(reconnectedBridge.replayed.map((message) => message.event.sequence), [secondEvent.sequence]);
  assert.deepEqual(reconnectedBridge.polled.events.map((event) => event.sequence), [secondEvent.sequence]);

  const portraitSecurity = await runStage('fixture-page.portrait-source-grants', 30_000, () => page.evaluate(async ({ expectedProjectRoot, unauthorizedPath }) => {
    const bridge = window.narrativeIDE;
    const failure = async (operation) => {
      try {
        await operation();
      } catch (error) {
        return String(error);
      }
      return '';
    };
    const unselectedAbsolute = await failure(() => bridge.portraitUpload({
      projectRoot: expectedProjectRoot,
      characterId: 'unselected-absolute',
      sourcePath: unauthorizedPath,
    }));
    const unselectedFileUrl = await failure(() => bridge.portraitSave({
      projectRoot: expectedProjectRoot,
      characterId: 'unselected-file-url',
      imageData: `file://${unauthorizedPath}`,
    }));
    const selected = await bridge.pickFiles({ multiple: false, filters: [{ name: 'Images', extensions: ['png'] }] });
    const uploaded = await bridge.portraitUpload({
      projectRoot: expectedProjectRoot,
      characterId: 'selected-upload',
      sourcePath: selected.paths[0],
    });
    const replay = await failure(() => bridge.portraitUpload({
      projectRoot: expectedProjectRoot,
      characterId: 'selected-replay',
      sourcePath: selected.paths[0],
    }));
    const selectedForFileUrl = await bridge.pickFiles({ multiple: false, filters: [{ name: 'Images', extensions: ['png'] }] });
    const savedFileUrl = await bridge.portraitSave({
      projectRoot: expectedProjectRoot,
      characterId: 'selected-file-url',
      imageData: `file://${selectedForFileUrl.paths[0]}`,
    });
    const loopbackUrl = await failure(() => bridge.portraitSave({
      projectRoot: expectedProjectRoot,
      characterId: 'loopback-url',
      imageData: 'https://127.0.0.1/portrait.png',
    }));
    return { unselectedAbsolute, unselectedFileUrl, uploaded, replay, savedFileUrl, loopbackUrl };
  }, { expectedProjectRoot: projectRoot, unauthorizedPath: unauthorizedPortraitPath }));
  assert.match(portraitSecurity.unselectedAbsolute, /not selected through the file dialog/);
  assert.match(portraitSecurity.unselectedFileUrl, /not selected through the file dialog/);
  assert.match(portraitSecurity.uploaded, /\/characters\/portraits\/selected-upload-[0-9a-f-]{36}\.png$/);
  assert.match(portraitSecurity.replay, /not selected through the file dialog/);
  assert.match(portraitSecurity.savedFileUrl, /\/characters\/portraits\/selected-file-url-[0-9a-f-]{36}\.png$/);
  assert.match(portraitSecurity.loopbackUrl, /public address/);

  const portraitsDir = path.join(projectRoot, 'characters', 'portraits');
  const originalPortraitsDir = path.join(projectRoot, 'characters', 'portraits-original');
  await rename(portraitsDir, originalPortraitsDir);
  await symlink(unauthorizedRoot, portraitsDir);
  const parentSymlinkError = await page.evaluate(async (expectedProjectRoot) => {
    try {
      await window.narrativeIDE.portraitSave({
        projectRoot: expectedProjectRoot,
        characterId: 'parent-symlink',
        imageData: 'data:image/png;base64,b3V0c2lkZS13cml0ZQ==',
      });
    } catch (error) {
      return String(error);
    }
    return '';
  }, projectRoot);
  assert.match(parentSymlinkError, /Portrait directory escapes authorized root/);
  assert.equal(await readFile(portraitSentinelPath, 'utf8'), 'portrait-target-sentinel');
  await unlink(portraitsDir);
  await rename(originalPortraitsDir, portraitsDir);

  await mkdir(path.join(projectRoot, 'links'), { recursive: true });
  await writeFile(path.join(unauthorizedRoot, 'outside.bin'), 'outside');
  await symlink(unauthorizedRoot, path.join(projectRoot, 'links', 'outside'));
  const symlinkErrors = await runStage('fixture-page.symlink-evaluate', 20_000, () => page.evaluate((expectedProjectRoot) => {
    const source = `${expectedProjectRoot}/links/outside/outside.bin`;
    const operations = [
      () => window.narrativeIDE.projectFileRead({ path: source, encoding: 'base64' }),
      () => window.narrativeIDE.projectFileCopy({ path: source, destination: `${expectedProjectRoot}/copied.bin` }),
      () => window.narrativeIDE.projectFileRename({ path: source, destination: `${expectedProjectRoot}/renamed.bin` }),
      () => window.narrativeIDE.projectFileUnlink({ path: source }),
    ];
    return operations.map((operation) => {
      try {
        operation();
      } catch (error) {
        return String(error);
      }
      return '';
    });
  }, projectRoot));
  for (const symlinkError of symlinkErrors) {
    assert.match(symlinkError, /escapes authorized root|resolves outside authorized root|symbolic link/);
  }

  await runStage('fixture-page.context-menu', 15_000, async () => {
    await page.click('#target', { button: 'right', timeout: 10_000 });
    await page.waitForFunction(() => document.querySelector('#result')?.textContent === 'context-menu-received', undefined, { timeout: 5_000 });
  });

  await runStage('vite-page.goto', 20_000, () => page.goto(viteUrl, { waitUntil: 'domcontentloaded', timeout: 20_000 }));
  const startupDbCalls = await runStage('vite-page.virtual-project-db-guard', 30_000, () => page.evaluate(async () => {
    const [{ useProjectStore }, { electronApi }] = await Promise.all([
      import('/src/ui-react/store.ts'),
      import('/src/ui-react/services/electronApi.ts'),
    ]);
    const calls = { open: 0, close: 0, sidecar: 0 };
    const original = {
      dbOpen: electronApi.dbOpen,
      dbClose: electronApi.dbClose,
      sidecarSpawn: electronApi.sidecarSpawn,
    };
    electronApi.dbOpen = async () => { calls.open += 1; return { ok: true }; };
    electronApi.dbClose = async () => { calls.close += 1; return { ok: true }; };
    electronApi.sidecarSpawn = async () => { calls.sidecar += 1; return { ok: true }; };
    try {
      await useProjectStore.getState().openProject();
      return calls;
    } finally {
      electronApi.dbOpen = original.dbOpen;
      electronApi.dbClose = original.dbClose;
      electronApi.sidecarSpawn = original.sidecarSpawn;
    }
  }));
  assert.deepEqual(startupDbCalls, { open: 0, close: 0, sidecar: 0 });
  const roundtrip = await runStage('vite-page.project-service-evaluate', 90_000, () => page.evaluate(async (expectedProjectRoot) => {
    const [{ electronApi }, { projectService }] = await Promise.all([
      import('/src/ui-react/services/electronApi.ts'),
      import('/src/ui-react/services/projectService.ts'),
    ]);
    const files = electronApi.projectFiles();
    if (!files) throw new Error('Project file bridge unavailable');
    const binaryPath = `${expectedProjectRoot}/assets/maps/large-roundtrip.bin`;
    const source = new Uint8Array(2 * 1024 * 1024 + 17);
    for (let index = 0; index < source.length; index += 1) source[index] = (index * 31) & 0xff;
    files.mkdirSync(`${expectedProjectRoot}/assets/maps`);
    files.writeFileSync(binaryPath, source);
    const restored = files.readFileSync(binaryPath);
    if (!(restored instanceof Uint8Array) || restored.length !== source.length) throw new Error('Binary roundtrip length mismatch');
    for (let index = 0; index < source.length; index += 65537) {
      if (restored[index] !== source[index]) throw new Error(`Binary roundtrip mismatch at ${index}`);
    }

    const created = projectService.createProject({
      name: 'Bridge Roundtrip',
      rootPath: expectedProjectRoot,
      template: 'blank',
      locale: 'en',
    });
    const saved = projectService.saveProject({
      ...created,
      metadata: { ...created.metadata, name: 'Bridge Roundtrip Saved' },
    });
    const opened = await projectService.openProject(expectedProjectRoot);
    return {
      savedName: saved.metadata.name,
      openedName: opened.metadata.name,
      projectJson: files.readFileSync(`${expectedProjectRoot}/project.json`, 'utf8'),
    };
  }, projectRoot));
  assert.equal(roundtrip.savedName, 'Bridge Roundtrip Saved');
  assert.equal(roundtrip.openedName, 'Bridge Roundtrip Saved');
  assert.match(roundtrip.projectJson, /Bridge Roundtrip Saved/);

  const activeStream = await runStage('fixture-page.runtime-stream-before-close', 20_000, () => page.evaluate(async ({ projectRoot, attemptId }) => {
    const bridge = window.narrativeIDE;
    const statuses = [];
    const unsubscribe = bridge.onRuntimeEventStreamStatus((message) => statuses.push(message));
    const subscription = await bridge.runtimeEventStreamSubscribe({
      projectRoot, attempt_id: attemptId, after_sequence: 2, subscription_id: 'electron-runtime-close-cleanup',
    });
    if (!subscription.ok) throw new Error(subscription.error || 'close-cleanup SSE subscription failed');
    const deadline = Date.now() + 5_000;
    while (!statuses.some((status) => status.status === 'open')) {
      if (Date.now() >= deadline) throw new Error('close-cleanup SSE stream did not open');
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    // Deliberately leave the stream subscribed. Electron shutdown must abort it.
    return { statuses, unsubscribe: typeof unsubscribe };
  }, { projectRoot, attemptId: resumableFixture.attempt_id }));
  assert.equal(activeStream.unsubscribe, 'function');
  assert(activeStream.statuses.some((status) => status.status === 'open'));
  await closeElectron();
  await assertSidecarPortClosed(resources.sidecarPort);

  log('result', 'Electron runtime smoke passed.');
  } finally {
    await cleanup([userData, projectRoot, unauthorizedRoot]);
  }
}

const onSignal = (signal) => {
  log('signal', `${signal} received; beginning bounded cleanup`);
  cleanup().finally(() => process.exit(signal === 'SIGINT' ? 130 : 143));
};

process.once('SIGINT', () => onSignal('SIGINT'));
process.once('SIGTERM', () => onSignal('SIGTERM'));
process.on('unhandledRejection', (error) => {
  console.error(`[electron-smoke] unhandled rejection: ${describeError(error)}`);
  cleanup().finally(() => { process.exitCode = 1; });
});

main().catch((error) => {
  console.error(`[electron-smoke] failed: ${describeError(error)}`);
  process.exitCode = 1;
});
