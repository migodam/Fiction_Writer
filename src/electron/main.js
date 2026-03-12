import path from 'node:path';
import { fileURLToPath } from 'node:url';
import electron from 'electron';

const { app, BrowserWindow, dialog, ipcMain } = electron;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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
