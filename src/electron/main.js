import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import electron from 'electron';
import { chatCompletion, streamCompletion, generateImage } from './services/aiService.js';

const { app, BrowserWindow, dialog, ipcMain } = electron;

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
ipcMain.handle('dialog:pick-files', async (_event, _payload) => {
  const result = await dialog.showOpenDialog({
    title: 'Import Reference Files',
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Text Files', extensions: ['txt', 'md'] }],
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

ipcMain.on('ai:stream-cancel', (_event, { requestId }) => {
  streamControllers.get(requestId)?.abort();
  streamControllers.delete(requestId);
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
