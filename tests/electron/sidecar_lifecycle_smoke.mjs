import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, readFile, realpath, rm } from 'node:fs/promises';
import { _electron as electron } from 'playwright';

const TIMEOUT_MS = 10_000;
const fixture = '<!doctype html><html><body>sidecar lifecycle smoke</body></html>';
const resources = { app: null, server: null, sidecarPid: null };

function within(timeoutMs, operation, label) {
  let timer;
  return Promise.race([
    Promise.resolve().then(operation),
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs); }),
  ]).finally(() => clearTimeout(timer));
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error?.code === 'ESRCH') return false;
    throw error;
  }
}

async function removeTreeEventually(directory) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    try {
      await rm(directory, { recursive: true, force: true });
      return;
    } catch (error) {
      if (error?.code !== 'ENOTEMPTY' || attempt === 9) throw error;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
}

async function closeResources() {
  const app = resources.app;
  resources.app = null;
  if (app && processIsAlive(app.process().pid)) {
    try { app.process().kill('SIGKILL'); } catch { /* bounded best effort after failure */ }
  }
  if (resources.server?.listening) {
    resources.server.closeAllConnections?.();
    resources.server.close();
  }
}

async function main() {
  const userData = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-sidecar-lifecycle-user-'));
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-sidecar-lifecycle-project-'));
  try {
    resources.server = http.createServer((_request, response) => {
      response.writeHead(200, { 'content-type': 'text/html' });
      response.end(fixture);
    });
    await within(TIMEOUT_MS, () => new Promise((resolve, reject) => {
      resources.server.once('error', reject);
      resources.server.listen(0, '127.0.0.1', resolve);
    }), 'fixture server listen');
    const address = resources.server.address();
    assert(address && typeof address !== 'string');

    resources.app = await within(TIMEOUT_MS, () => electron.launch({
      args: ['.'],
      cwd: process.cwd(),
      env: {
        ...process.env,
        NARRATIVE_IDE_RUNTIME_SMOKE: '1',
        NARRATIVE_IDE_RENDERER_URL: `http://127.0.0.1:${address.port}`,
        NARRATIVE_IDE_USER_DATA: userData,
        NARRATIVE_IDE_SMOKE_PROJECT_ROOT: projectRoot,
      },
    }), 'electron launch');
    const page = await within(TIMEOUT_MS, () => resources.app.firstWindow(), 'first window');
    const lifecycle = await within(TIMEOUT_MS * 2, () => page.evaluate(async (root) => {
      const bridge = window.narrativeIDE;
      await bridge.pickDirectory({ mode: 'open' });
      const spawns = await Promise.all([
        bridge.sidecarSpawn({ projectRoot: root }),
        bridge.sidecarSpawn({ projectRoot: root }),
        bridge.sidecarSpawn({ projectRoot: root }),
      ]);
      return { spawns, recoverable: await bridge.runtimeRecoverable({ projectRoot: root }) };
    }, projectRoot), 'spawn and immediate runtime call');

    assert(lifecycle.spawns.every((result) => result.ok), JSON.stringify(lifecycle.spawns));
    assert.equal(new Set(lifecycle.spawns.map((result) => result.port)).size, 1);
    assert.notEqual(lifecycle.recoverable.error, 'sidecar_offline');

    const canonicalProjectRoot = await realpath(projectRoot);
    const projectIdentity = createHash('sha256').update(canonicalProjectRoot, 'utf8').digest('hex').slice(0, 40);
    const pidFile = path.join(os.homedir(), '.narrative-ide', 'processes', `${projectIdentity}.json`);
    resources.sidecarPid = JSON.parse(await readFile(pidFile, 'utf8')).pid;
    const electronProcess = resources.app.process();
    const exitPromise = once(electronProcess, 'exit');
    const quitRequest = resources.app.evaluate(({ app }) => app.quit()).catch(() => {});
    try {
      await within(TIMEOUT_MS, () => exitPromise, 'Electron quit');
    } catch (error) {
      await quitRequest;
      console.error(JSON.stringify({
        electronPid: electronProcess.pid,
        exitCode: electronProcess.exitCode,
        signalCode: electronProcess.signalCode,
        killed: electronProcess.killed,
        alive: processIsAlive(electronProcess.pid),
      }));
      try {
        console.error(await readFile(path.join(userData, 'electron-lifecycle-smoke.jsonl'), 'utf8'));
      } catch { /* diagnostics unavailable */ }
      throw error;
    }
    assert.equal(processIsAlive(resources.sidecarPid), false, `Sidecar ${resources.sidecarPid} survived Electron quit`);
    const diagnostics = (await readFile(path.join(userData, 'electron-lifecycle-smoke.jsonl'), 'utf8'))
      .trim().split('\n').map((line) => JSON.parse(line));
    const shutdown = diagnostics.findLast((entry) => entry.event === 'shutdown-complete');
    assert(shutdown, 'Missing shutdown-complete lifecycle diagnostic');
    assert.equal(shutdown.sidecars, 0);
    assert.equal(shutdown.runtimeStreams, 0);
    assert.equal(shutdown.workflowStreams, 0);
    resources.app = null;
    console.log('sidecar lifecycle smoke passed');
  } finally {
    await closeResources();
    await removeTreeEventually(userData);
    await removeTreeEventually(projectRoot);
  }
}

main().then(
  () => process.exit(0),
  (error) => {
    console.error(error);
    process.exit(1);
  },
);
