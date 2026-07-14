const { contextBridge, ipcRenderer } = require('electron');

const requestIdPattern = /^[A-Za-z0-9_-]{1,128}$/;

function validRequestId(requestId) {
  return typeof requestId === 'string' && requestIdPattern.test(requestId);
}

function subscribe(channel, callback) {
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

function projectFileSync(operation, payload) {
  const result = ipcRenderer.sendSync(`projectfs:${operation}`, payload);
  if (!result?.ok) throw new Error(result?.error || 'Project file operation failed');
  return result.value;
}

// Keep renderer access intentionally capability-based. Do not expose ipcRenderer itself.
const narrativeIDE = {
  pickDirectory: (payload) => ipcRenderer.invoke('dialog:pick-directory', payload),
  selectProjectRoot: () => ipcRenderer.invoke('project:selectRoot'),
  projectFileExists: (payload) => projectFileSync('exists', payload),
  projectFileRead: (payload) => projectFileSync('read', payload),
  projectFileWrite: (payload) => projectFileSync('write', payload),
  projectFileMkdir: (payload) => projectFileSync('mkdir', payload),
  projectFileReaddir: (payload) => projectFileSync('readdir', payload),
  projectFileUnlink: (payload) => projectFileSync('unlink', payload),
  projectFileRealpath: (payload) => projectFileSync('realpath', payload),
  projectFileCopy: (payload) => projectFileSync('copy', payload),
  projectFileRename: (payload) => projectFileSync('rename', payload),
  sha256: (value) => {
    const result = ipcRenderer.sendSync('crypto:sha256', value);
    if (!result?.ok) throw new Error(result?.error || 'SHA-256 operation failed');
    return result.value;
  },
  loadAppSettings: () => ipcRenderer.invoke('settings:load-app'),
  saveAppSettings: (payload) => ipcRenderer.invoke('settings:save-app', payload),
  pickFiles: (payload) => ipcRenderer.invoke('dialog:pick-files', payload),
  testProviderConnection: (payload) => ipcRenderer.invoke('settings:test-provider', payload),
  aiChat: (payload) => ipcRenderer.invoke('ai:chat', payload),
  aiGenerateImage: (payload) => ipcRenderer.invoke('ai:generate-image', payload),
  portraitSave: (payload) => ipcRenderer.invoke('portrait:save', payload),
  portraitUpload: (payload) => ipcRenderer.invoke('portrait:upload', payload),
  aiStreamStart: (payload) => ipcRenderer.send('ai:stream-start', payload),
  aiStreamCancel: (payload) => ipcRenderer.send('ai:stream-cancel', payload),
  onAIChunk: (requestId, callback) => validRequestId(requestId) ? subscribe(`ai:chunk:${requestId}`, callback) : () => {},
  onAIDone: (requestId, callback) => validRequestId(requestId) ? subscribe(`ai:done:${requestId}`, callback) : () => {},
  onAIError: (requestId, callback) => validRequestId(requestId) ? subscribe(`ai:error:${requestId}`, callback) : () => {},
  dbOpen: (payload) => ipcRenderer.invoke('db:open', payload),
  dbClose: (payload) => ipcRenderer.invoke('db:close', payload),
  dbUpsert: (payload) => ipcRenderer.invoke('db:upsert', payload),
  dbGetAll: (payload) => ipcRenderer.invoke('db:getAll', payload),
  dbDelete: (payload) => ipcRenderer.invoke('db:delete', payload),
  dbSearch: (payload) => ipcRenderer.invoke('db:search', payload),
  w3Start: (payload) => ipcRenderer.invoke('w3:start', payload),
  w3Select: (payload) => ipcRenderer.invoke('w3:select', payload),
  w3Status: (payload) => ipcRenderer.invoke('w3:status', payload),
  onW3Progress: (callback) => subscribe('w3:progress', callback),
  w1Start: (payload) => ipcRenderer.invoke('w1:start', payload),
  w1Cancel: (payload) => ipcRenderer.invoke('w1:cancel', payload),
  w1Status: (payload) => ipcRenderer.invoke('w1:status', payload),
  w1Console: (payload) => ipcRenderer.invoke('w1:console', payload),
  w1SetBreakpoint: (payload) => ipcRenderer.invoke('w1:set_breakpoint', payload),
  w1Resume: (payload) => ipcRenderer.invoke('w1:resume', payload),
  w1Rewind: (payload) => ipcRenderer.invoke('w1:rewind', payload),
  fetchPrompts: (payload) => ipcRenderer.invoke('prompts:list', payload),
  sidecarSpawn: (payload) => ipcRenderer.invoke('sidecar:spawn', payload),
  w2Start: (payload) => ipcRenderer.invoke('w2:start', payload),
  w2Status: (payload) => ipcRenderer.invoke('w2:status', payload),
  w4Start: (payload) => ipcRenderer.invoke('w4:start', payload),
  w4Status: (payload) => ipcRenderer.invoke('w4:status', payload),
  w5Start: (payload) => ipcRenderer.invoke('w5:start', payload),
  w5Status: (payload) => ipcRenderer.invoke('w5:status', payload),
  w6Start: (payload) => ipcRenderer.invoke('w6:start', payload),
  w6Status: (payload) => ipcRenderer.invoke('w6:status', payload),
  metadataIngest: (payload) => ipcRenderer.invoke('metadata:ingest', payload),
  metadataStatus: (payload) => ipcRenderer.invoke('metadata:status', payload),
  orchestratorStart: (payload) => ipcRenderer.invoke('orchestrator:start', payload),
  orchestratorStatus: (payload) => ipcRenderer.invoke('orchestrator:status', payload),
  orchestratorGrant: (payload) => ipcRenderer.invoke('orchestrator:grant', payload),
  orchestratorDeny: (payload) => ipcRenderer.invoke('orchestrator:deny', payload),
};

contextBridge.exposeInMainWorld('narrativeIDE', narrativeIDE);
