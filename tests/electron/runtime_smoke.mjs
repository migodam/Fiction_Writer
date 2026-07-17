import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
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
const resources = { app: undefined, vite: undefined, sidecarPid: undefined, userData: undefined };
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
  assert.equal(typeof resources.sidecarPid, 'number');

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
