import path from 'node:path';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import electron from 'electron';
import { chatCompletion, streamCompletion, generateImage } from './services/aiService.js';
import { openDb, closeDb, closeAllDbs, upsertEntity, getAllEntities, deleteEntity, migrateFromJson, indexEntity, searchEntities } from './db.js';

const { app, BrowserWindow, dialog, ipcMain } = electron;

// ── Sidecar process management ────────────────────────────────────────────────

const PID_DIR = path.join(os.homedir(), '.narrative-ide', 'processes');
/** Maps projectRoot → spawned ChildProcess */
const sidecarProcesses = new Map();
/** Maps projectRoot → sidecar port number */
const sidecarPorts = new Map();
/** Maps BrowserWindow → projectRoot */
const windowProjectMap = new Map();

function getSidecarPidFile(projectRoot) {
  fs.mkdirSync(PID_DIR, { recursive: true });
  const projectId = Buffer.from(projectRoot).toString('base64url').slice(0, 40);
  return path.join(PID_DIR, `${projectId}.json`);
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function isPidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function spawnSidecar(projectRoot) {
  // Check for existing PID file
  const pidFile = getSidecarPidFile(projectRoot);
  if (fs.existsSync(pidFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(pidFile, 'utf8'));
      if (data.pid && isPidAlive(data.pid)) {
        // Sidecar already running — reuse
        sidecarPorts.set(projectRoot, data.port);
        return data.port;
      }
      // Stale PID — delete and respawn
      fs.unlinkSync(pidFile);
    } catch { /* corrupt file — ignore */ }
  }

  const port = await findFreePort();
  const sidecarEntry = path.resolve(__dirname, '../../sidecar/main.py');

  const proc = spawn('python', [sidecarEntry, '--port', String(port), '--project-path', projectRoot], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  });

  proc.stdout.on('data', (d) => console.log(`[sidecar:${port}]`, d.toString().trim()));
  proc.stderr.on('data', (d) => console.error(`[sidecar:${port}:err]`, d.toString().trim()));
  proc.on('exit', (code) => {
    console.log(`[sidecar:${port}] exited with code ${code}`);
    sidecarProcesses.delete(projectRoot);
    sidecarPorts.delete(projectRoot);
    try { fs.unlinkSync(getSidecarPidFile(projectRoot)); } catch { /* ignore */ }
  });

  sidecarProcesses.set(projectRoot, proc);
  sidecarPorts.set(projectRoot, port);

  // Write PID file
  fs.writeFileSync(pidFile, JSON.stringify({ pid: proc.pid, port, projectPath: projectRoot }, null, 2), 'utf8');

  return port;
}

function killSidecar(projectRoot) {
  const proc = sidecarProcesses.get(projectRoot);
  if (proc) {
    try { proc.kill(); } catch { /* ignore */ }
    sidecarProcesses.delete(projectRoot);
    sidecarPorts.delete(projectRoot);
  }
  const pidFile = getSidecarPidFile(projectRoot);
  if (fs.existsSync(pidFile)) {
    try { fs.unlinkSync(pidFile); } catch { /* ignore */ }
  }
}

function killAllSidecars() {
  for (const projectRoot of [...sidecarProcesses.keys()]) {
    killSidecar(projectRoot);
  }
}

function getSidecarPort(projectRoot) {
  return sidecarPorts.get(projectRoot) ?? null;
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const APP_SETTINGS_FILE = 'narrative-ide-app-settings.json';

function getSettingsPath() {
  return path.join(app.getPath('userData'), APP_SETTINGS_FILE);
}

function loadAppSettings() {
  const settingsPath = getSettingsPath();
  if (!fs.existsSync(settingsPath)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
}

function saveAppSettings(partial) {
  const current = loadAppSettings() || {};
  const next = { ...current, ...partial };
  fs.mkdirSync(path.dirname(getSettingsPath()), { recursive: true });
  fs.writeFileSync(getSettingsPath(), JSON.stringify(next, null, 2), 'utf8');
  return next;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1600,
    height: 960,
    minWidth: 1200,
    minHeight: 720,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

  if (isDev) {
    win.loadURL('http://localhost:3000');
    win.webContents.openDevTools();
  } else {
    win.loadFile(path.join(__dirname, '../../dist/index.html'));
  }

  win.on('closed', () => {
    // Abort all in-flight AI streams
    for (const controller of streamControllers.values()) {
      controller.abort();
    }
    streamControllers.clear();
    // Kill per-project sidecar for this window
    const projectRoot = windowProjectMap.get(win);
    windowProjectMap.delete(win);
    if (projectRoot) killSidecar(projectRoot);
  });
}

ipcMain.handle('dialog:pick-directory', async (_event, payload = { mode: 'open' }) => {
  const result = await dialog.showOpenDialog({
    title: payload.mode === 'create' ? 'Choose Project Parent Folder' : 'Open Narrative Project Folder',
    properties: ['openDirectory', 'createDirectory'],
  });

  return {
    canceled: result.canceled,
    path: result.canceled ? null : result.filePaths[0],
  };
});

ipcMain.handle('settings:load-app', async () => loadAppSettings());
ipcMain.handle('settings:save-app', async (_event, payload = {}) => saveAppSettings(payload));
ipcMain.handle('dialog:pick-files', async (_event, payload) => {
  const filters = payload?.filters ?? [{ name: 'Text Files', extensions: ['txt', 'md'] }];
  const multiple = payload?.multiple !== false;
  const properties = multiple ? ['openFile', 'multiSelections'] : ['openFile'];
  const result = await dialog.showOpenDialog({
    title: 'Select Files',
    properties,
    filters,
  });
  return { canceled: result.canceled, paths: result.canceled ? [] : result.filePaths };
});

ipcMain.handle('settings:test-provider', async (_event, payload = {}) => ({
  ok: Boolean(payload?.endpoint && payload?.provider),
  message: payload?.endpoint && payload?.provider ? 'connected_placeholder' : 'missing_endpoint_or_provider',
}));

// Map of active stream abort controllers
const streamControllers = new Map();

// Helper: get active AI text config from app settings
function getAITextConfig(settings) {
  const profiles = settings.providerProfiles ?? [];
  const modelProfiles = settings.modelProfiles ?? [];
  const profile =
    profiles.find((p) => p.id === settings.selectedProviderProfileId) ?? profiles[0];
  const modelProfile =
    modelProfiles.find((m) => m.id === settings.selectedModelProfileId) ?? modelProfiles[0];
  if (!profile) throw new Error('No AI provider configured');
  return {
    endpoint: profile.endpoint,
    apiKey: profile.apiKey,
    model: modelProfile?.model ?? 'gpt-4o-mini',
    temperature: modelProfile?.temperature ?? 0.7,
    maxTokens: modelProfile?.maxTokens ?? 2048,
  };
}

function getAIImageConfig(settings) {
  const profiles = settings.providerProfiles ?? [];
  const profile =
    profiles.find((p) => p.id === settings.selectedProviderProfileId) ?? profiles[0];
  if (!profile) throw new Error('No AI provider configured');
  return {
    endpoint: profile.endpoint,
    apiKey: profile.apiKey,
    model: profile.imageModel ?? 'dall-e-3',
    size: '1024x1024',
  };
}

// Single-turn chat
ipcMain.handle('ai:chat', async (_event, { messages }) => {
  const settings = loadAppSettings() ?? {};
  const config = getAITextConfig(settings);
  return await chatCompletion(messages, config);
});

// Image generation
ipcMain.handle('ai:generate-image', async (_event, { prompt }) => {
  const settings = loadAppSettings() ?? {};
  const config = getAIImageConfig(settings);
  return await generateImage(prompt, config);
});

// Streaming chat
ipcMain.on('ai:stream-start', async (event, { requestId, messages }) => {
  try {
    const settings = loadAppSettings() ?? {};
    const config = getAITextConfig(settings);
    const controller = new AbortController();
    streamControllers.set(requestId, controller);
    await streamCompletion(
      messages,
      config,
      (text) => event.reply(`ai:chunk:${requestId}`, text),
      controller.signal,
    );
    streamControllers.delete(requestId);
    event.reply(`ai:done:${requestId}`);
  } catch (err) {
    streamControllers.delete(requestId);
    event.reply(`ai:error:${requestId}`, err.message);
  }
});

// Save portrait image to project folder
ipcMain.handle('portrait:save', async (_event, { projectRoot, characterId, imageData }) => {
  if (!/^[a-zA-Z0-9_\-]+$/.test(characterId)) throw new Error('Invalid characterId');
  const portraitsDir = path.join(projectRoot, 'characters', 'portraits');
  const resolvedRoot = path.resolve(projectRoot);
  const resolvedPortraitsDir = path.resolve(portraitsDir);
  if (!resolvedPortraitsDir.startsWith(resolvedRoot + path.sep) && resolvedPortraitsDir !== resolvedRoot) {
    throw new Error('Path traversal detected');
  }
  await fsPromises.mkdir(portraitsDir, { recursive: true });
  const filePath = path.join(portraitsDir, `${characterId}.png`);

  if (imageData.startsWith('http')) {
    const response = await fetch(imageData);
    if (!response.ok) throw new Error(`Failed to download image: ${response.status}`);
    const buffer = Buffer.from(await response.arrayBuffer());
    await fsPromises.writeFile(filePath, buffer);
  } else if (imageData.startsWith('file://')) {
    const srcPath = imageData.replace(/^file:\/\//, '');
    await fsPromises.copyFile(srcPath, filePath);
  } else if (imageData.startsWith('/') || /^[A-Za-z]:\\/.test(imageData)) {
    await fsPromises.copyFile(imageData, filePath);
  } else {
    const base64 = imageData.replace(/^data:image\/\w+;base64,/, '');
    await fsPromises.writeFile(filePath, Buffer.from(base64, 'base64'));
  }

  return pathToFileURL(filePath).href;
});

// Upload portrait from local file path by copying to project portraits folder
ipcMain.handle('portrait:upload', async (_event, { projectRoot, characterId, sourcePath }) => {
  if (!/^[a-zA-Z0-9_\-]+$/.test(characterId)) throw new Error('Invalid characterId');
  const portraitsDir = path.join(projectRoot, 'characters', 'portraits');
  const resolvedRoot = path.resolve(projectRoot);
  const resolvedPortraitsDir = path.resolve(portraitsDir);
  if (!resolvedPortraitsDir.startsWith(resolvedRoot + path.sep) && resolvedPortraitsDir !== resolvedRoot) {
    throw new Error('Path traversal detected');
  }
  await fsPromises.mkdir(portraitsDir, { recursive: true });
  const filePath = path.join(portraitsDir, `${characterId}.png`);
  await fsPromises.copyFile(sourcePath, filePath);
  return pathToFileURL(filePath).href;
});

ipcMain.on('ai:stream-cancel', (_event, { requestId }) => {
  streamControllers.get(requestId)?.abort();
  streamControllers.delete(requestId);
});

// --- DB IPC handlers ---

// Open/migrate DB when project opens
ipcMain.handle('db:open', async (_event, { projectRoot, projectJson }) => {
  const db = openDb(projectRoot);
  if (projectJson) await migrateFromJson(projectRoot, projectJson);
  // Suppress unused variable warning — db used internally via openDbs map
  void db;
  return { ok: true };
});

// Close DB when project closes
ipcMain.handle('db:close', async (_event, { projectRoot }) => {
  closeDb(projectRoot);
  return { ok: true };
});

// Upsert entity
ipcMain.handle('db:upsert', async (_event, { projectRoot, table, id, data }) => {
  const db = openDb(projectRoot);
  upsertEntity(db, table, id, data);
  return { ok: true };
});

// Get all entities from a table
ipcMain.handle('db:getAll', async (_event, { projectRoot, table }) => {
  const db = openDb(projectRoot);
  return getAllEntities(db, table);
});

// Delete entity
ipcMain.handle('db:delete', async (_event, { projectRoot, table, id }) => {
  const db = openDb(projectRoot);
  deleteEntity(db, table, id);
  return { ok: true };
});

// Index entity for FTS
ipcMain.handle('db:indexEntity', async (_event, { projectRoot, entityType, entityId, title, content }) => {
  const db = openDb(projectRoot);
  indexEntity(db, entityType, entityId, title, content);
  return { ok: true };
});

// Full-text search
ipcMain.handle('db:search', async (_event, { projectRoot, query }) => {
  const db = openDb(projectRoot);
  return searchEntities(db, query);
});

// ── Sidecar IPC handlers ──────────────────────────────────────────────────────

// Spawn sidecar for a project (called when project opens)
ipcMain.handle('sidecar:spawn', async (_event, { projectRoot }) => {
  try {
    const port = await spawnSidecar(projectRoot);
    // Associate the sender window with this project
    const win = BrowserWindow.fromWebContents(_event.sender);
    if (win) windowProjectMap.set(win, projectRoot);
    return { ok: true, port };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// Poll workflow lock status (UI polls every 2s)
ipcMain.handle('workflow:status', async (_event, { projectRoot }) => {
  const port = getSidecarPort(projectRoot);
  if (!port) return { status: 'offline', workflowId: null, progress: 0 };
  try {
    const res = await fetch(`http://127.0.0.1:${port}/workflow/status`);
    return await res.json();
  } catch {
    return { status: 'offline', workflowId: null, progress: 0 };
  }
});

// Force-clear a stale workflow.lock file
ipcMain.handle('workflow:force-clear', async (_event, { projectRoot }) => {
  const lockPath = path.join(projectRoot, 'workflow.lock');
  if (fs.existsSync(lockPath)) {
    try { fs.unlinkSync(lockPath); } catch (err) {
      return { ok: false, error: err.message };
    }
  }
  return { ok: true };
});

// SSE bridge: subscribe to sidecar stream, forward events to renderer
ipcMain.on('workflow:stream-subscribe', async (event, { projectRoot }) => {
  const port = getSidecarPort(projectRoot);
  if (!port) return;
  try {
    const res = await fetch(`http://127.0.0.1:${port}/workflow/stream`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const read = async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        // Parse SSE lines and forward W3 progress events separately
        for (const line of text.split('\n')) {
          if (!line.startsWith('data:')) continue;
          try {
            const data = JSON.parse(line.slice(5).trim());
            if (data.workflow_id === 'W3') event.reply('w3:progress', data);
          } catch { /* non-JSON SSE line */ }
        }
        event.reply('workflow:stream-event', text);
      }
    };
    read().catch(() => {/* stream ended */});
  } catch { /* sidecar offline */ }
});

// ── Generic sidecar HTTP proxy ────────────────────────────────────────────────

async function proxyToSidecar(projectRoot, path, method = 'GET', body = null) {
  const port = getSidecarPort(projectRoot);
  if (!port) throw new Error('sidecar_offline');
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`http://127.0.0.1:${port}${path}`, opts);
  return res.json();
}

// ── W3 Writing Assistant IPC handlers ─────────────────────────────────────────

ipcMain.handle('w3:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w3/start', 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w3:select', async (_event, { projectRoot, sessionId, selectedOption }) => {
  try {
    return await proxyToSidecar(projectRoot, '/workflow/w3/select', 'POST', {
      session_id: sessionId,
      selected_option: selectedOption,
    });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w3:status', async (_event, { projectRoot }) => {
  try {
    return await proxyToSidecar(projectRoot, '/workflow/w3/status', 'GET');
  } catch {
    return { status: 'offline', progress: 0, workflow_id: null };
  }
});

// ── W1 Import IPC handlers ─────────────────────────────────────────────────

ipcMain.handle('w1:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w1/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w1:cancel', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w1/cancel', 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w1:status', async (_event, { projectRoot, session_id }) => {
  try {
    const qs = session_id ? `?session_id=${session_id}` : '';
    return await proxyToSidecar(projectRoot, `/workflow/w1/status${qs}`, 'GET');
  } catch {
    return { status: 'offline', progress: 0, errors: [], completed_chunks: 0, total_chunks: 0 };
  }
});

// ── W2 Manuscript Sync IPC handlers ────────────────────────────────────────

ipcMain.handle('w2:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w2/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W4 Consistency Check IPC handlers ──────────────────────────────────────

ipcMain.handle('w4:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w4/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w4:status', async (_event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(projectRoot, `/workflow/w4/status?session_id=${session_id}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W5 Simulation Engine IPC handlers ──────────────────────────────────────

ipcMain.handle('w5:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w5/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w5:status', async (_event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(projectRoot, `/workflow/w5/status?session_id=${session_id}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W6 Beta Reader IPC handlers ─────────────────────────────────────────────

ipcMain.handle('w6:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/workflow/w6/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w6:status', async (_event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(projectRoot, `/workflow/w6/status?session_id=${session_id}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W7 Metadata Ingestion IPC handlers ─────────────────────────────────────

ipcMain.handle('metadata:ingest', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/metadata/ingest', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('metadata:status', async (_event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(projectRoot, `/metadata/status?session_id=${session_id}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── Orchestrator IPC handlers ───────────────────────────────────────────────

ipcMain.handle('orchestrator:start', async (_event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(projectRoot, '/orchestrator/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('orchestrator:status', async (_event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(projectRoot, `/orchestrator/status?session_id=${session_id}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('orchestrator:grant', async (_event, payload) => {
  try {
    const { projectRoot, stepId, ...rest } = payload;
    return await proxyToSidecar(projectRoot, `/orchestrator/permission/${stepId}/grant`, 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('orchestrator:deny', async (_event, payload) => {
  try {
    const { projectRoot, stepId, ...rest } = payload;
    return await proxyToSidecar(projectRoot, `/orchestrator/permission/${stepId}/deny`, 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  closeAllDbs();
  killAllSidecars();
});
