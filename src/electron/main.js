import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import electron from 'electron';

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
ipcMain.handle('settings:test-provider', async (_event, payload = {}) => ({
  ok: Boolean(payload?.endpoint && payload?.provider),
  message: payload?.endpoint && payload?.provider ? 'connected_placeholder' : 'missing_endpoint_or_provider',
}));

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
