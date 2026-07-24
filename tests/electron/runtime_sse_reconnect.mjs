import assert from 'node:assert/strict';
import { once } from 'node:events';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, rm } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { _electron as electron } from 'playwright';

const REPO_ROOT = process.cwd();
const PYTHON = path.join(REPO_ROOT, 'sidecar/.venv/bin/python');
const TIMEOUT_MS = 30_000;
const resources = { app: null, server: null, userData: null, projectRoot: null };

const within = (label, action, timeoutMs = TIMEOUT_MS) => Promise.race([
  Promise.resolve().then(action),
  new Promise((_, reject) => setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs)),
]);

const seedAttempt = (projectRoot, count) => {
  const script = String.raw`
import json
import sys
from sidecar.runtime.agent_runtime import RuntimeStore

store = RuntimeStore(sys.argv[1])
run = store.get_run_by_lineage("electron-sse-lineage")
if run is None:
    run = store.create_run(workflow_id="W1", lineage_id="electron-sse-lineage", thread_id="electron-sse-thread")
    attempt = store.create_attempt(run["run_id"])
    lease = store.acquire_lease(attempt["attempt_id"], "electron-sse-seeder", ttl_seconds=120)
else:
    attempt = store.list_attempts(run["run_id"])[0]
    lease = store.acquire_lease(attempt["attempt_id"], "electron-sse-seeder", ttl_seconds=120)
for index in range(1, int(sys.argv[2]) + 1):
    store.append_event(
        attempt["attempt_id"], "agent.progress", {"summary": f"event-{index}"},
        owner_id="electron-sse-seeder", fence_token=lease["fence_token"],
        idempotency_key=f"electron-sse-{index}", contract_version="AgentEvent/v1",
        actor={"kind": "tool", "id": "electron-sse-seeder"},
    )
print(json.dumps({"attempt_id": attempt["attempt_id"]}))
`;
  const result = spawnSync(PYTHON, ['-c', script, projectRoot, String(count)], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    timeout: TIMEOUT_MS,
  });
  assert.equal(result.status, 0, `runtime seed failed: ${result.stderr || result.stdout}`);
  return JSON.parse(result.stdout);
};

async function closeResources() {
  const app = resources.app;
  resources.app = null;
  if (app) {
    const child = app.process();
    try {
      const exited = once(child, 'exit');
      void app.evaluate(({ app: electronApp }) => electronApp.quit()).catch(() => {});
      await within('electron close', () => exited, 10_000);
    } catch {
      try { child.kill('SIGKILL'); } catch { /* best effort after a failed smoke */ }
    }
  }
  if (resources.server?.listening) {
    resources.server.closeAllConnections?.();
    await new Promise((resolve) => resources.server.close(resolve));
  }
  await Promise.all([resources.userData, resources.projectRoot].filter(Boolean).map((directory) => rm(directory, { recursive: true, force: true })));
}

async function main() {
  resources.userData = await mkdtemp(path.join(os.tmpdir(), 'narrative-runtime-sse-user-'));
  resources.projectRoot = await mkdtemp(path.join(os.tmpdir(), 'narrative-runtime-sse-project-'));
  try {
    const { attempt_id: attemptId } = seedAttempt(resources.projectRoot, 1);
    resources.server = http.createServer((_request, response) => {
      response.writeHead(200, { 'content-type': 'text/html' });
      response.end('<!doctype html><title>runtime sse smoke</title>');
    });
    await new Promise((resolve, reject) => {
      resources.server.once('error', reject);
      resources.server.listen(0, '127.0.0.1', resolve);
    });
    const address = resources.server.address();
    assert(address && typeof address !== 'string');
    resources.app = await within('electron launch', () => electron.launch({
      args: ['.'], cwd: REPO_ROOT,
      env: {
        ...process.env,
        NARRATIVE_IDE_RUNTIME_SMOKE: '1',
        NARRATIVE_IDE_RENDERER_URL: `http://127.0.0.1:${address.port}`,
        NARRATIVE_IDE_USER_DATA: resources.userData,
        NARRATIVE_IDE_SMOKE_PROJECT_ROOT: resources.projectRoot,
      },
    }));
    const page = await within('electron first window', () => resources.app.firstWindow());
    const first = await within('initial real SSE subscription', () => page.evaluate(async ({ projectRoot, attemptId }) => {
      const bridge = window.narrativeIDE;
      await bridge.pickDirectory({ mode: 'open' });
      const spawned = await bridge.sidecarSpawn({ projectRoot });
      if (!spawned.ok) throw new Error('sidecar spawn failed');
      const events = [];
      const statuses = [];
      const unsubscribeEvents = bridge.onRuntimeEvent((message) => events.push(message));
      const unsubscribeStatuses = bridge.onRuntimeEventStreamStatus((message) => statuses.push(message));
      const subscriptionId = 'electron-sse-first';
      const result = await bridge.runtimeEventStreamSubscribe({ projectRoot, attempt_id: attemptId, after_sequence: 0, subscription_id: subscriptionId });
      if (!result.ok) throw new Error(result.error || 'subscription failed');
      const deadline = Date.now() + 10_000;
      while (!events.some((message) => message.event?.sequence === 1)) {
        if (Date.now() > deadline) throw new Error('first SSE event missing');
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
      await bridge.runtimeEventStreamUnsubscribe({ subscription_id: subscriptionId });
      unsubscribeEvents();
      unsubscribeStatuses();
      return { events, statuses, port: spawned.port };
    }, { projectRoot: resources.projectRoot, attemptId }));
    assert(first.statuses.some((status) => status.status === 'open'), JSON.stringify(first));
    assert.deepEqual(first.events.map((message) => message.event.sequence), [1]);

    seedAttempt(resources.projectRoot, 3);
    const resumed = await within('cursor real SSE subscription', () => page.evaluate(async ({ projectRoot, attemptId }) => {
      const bridge = window.narrativeIDE;
      const events = [];
      const statuses = [];
      const unsubscribeEvents = bridge.onRuntimeEvent((message) => events.push(message));
      const unsubscribeStatuses = bridge.onRuntimeEventStreamStatus((message) => statuses.push(message));
      const subscriptionId = 'electron-sse-resumed';
      const result = await bridge.runtimeEventStreamSubscribe({ projectRoot, attempt_id: attemptId, after_sequence: 1, subscription_id: subscriptionId });
      if (!result.ok) throw new Error(result.error || 'resume subscription failed');
      const deadline = Date.now() + 10_000;
      while (!events.some((message) => message.event?.sequence === 3)) {
        if (Date.now() > deadline) throw new Error('replayed SSE events missing');
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
      await bridge.runtimeEventStreamUnsubscribe({ subscription_id: subscriptionId });
      unsubscribeEvents();
      unsubscribeStatuses();
      return { events, statuses };
    }, { projectRoot: resources.projectRoot, attemptId }));
    assert(resumed.statuses.some((status) => status.status === 'open'), JSON.stringify(resumed));
    assert.deepEqual(resumed.events.map((message) => message.event.sequence), [2, 3]);
    assert.equal(new Set(resumed.events.map((message) => message.event.event_id)).size, 2);
    console.log('electron runtime SSE reconnect smoke: passed');
  } finally {
    await closeResources();
  }
}

main().then(() => process.exit(0), (error) => {
  console.error(error);
  process.exit(1);
});
