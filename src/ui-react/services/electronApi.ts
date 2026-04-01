export interface PickDirectoryResult {
  canceled: boolean;
  path: string | null;
}

export interface ProviderConnectionResult {
  ok: boolean;
  message: string;
}

const getIpcRenderer = () => {
  const scope = globalThis as typeof globalThis & { require?: NodeRequire };
  const loader = scope.require;
  if (!loader) {
    return null;
  }

  try {
    return loader('electron').ipcRenderer as {
      invoke: (channel: string, payload?: unknown) => Promise<unknown>;
      send: (channel: string, payload?: unknown) => void;
      on: (channel: string, listener: (...args: unknown[]) => void) => void;
      removeAllListeners: (channel: string) => void;
    };
  } catch {
    return null;
  }
};

export const electronApi = {
  isAvailable(): boolean {
    return Boolean(getIpcRenderer());
  },

  async pickDirectory(mode: 'create' | 'open'): Promise<PickDirectoryResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return { canceled: true, path: null };
    }

    const result = (await ipcRenderer.invoke('dialog:pick-directory', { mode })) as PickDirectoryResult;
    return result;
  },

  async loadAppSettings<T = Record<string, unknown> | null>(): Promise<T | null> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return null;
    }
    return (await ipcRenderer.invoke('settings:load-app')) as T | null;
  },

  async saveAppSettings<T = Record<string, unknown>>(payload: Partial<T>): Promise<T | null> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return null;
    }
    return (await ipcRenderer.invoke('settings:save-app', payload)) as T | null;
  },

  async pickFiles(options?: { filters?: Array<{ name: string; extensions: string[] }>; multiple?: boolean }): Promise<string[]> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    const result = (await ipcRenderer.invoke('dialog:pick-files', options)) as { canceled: boolean; paths: string[] } | null;
    return result?.paths ?? [];
  },

  async testProviderConnection(payload: Record<string, unknown>): Promise<ProviderConnectionResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return { ok: false, message: 'ipc_unavailable' };
    }
    return (await ipcRenderer.invoke('settings:test-provider', payload)) as ProviderConnectionResult;
  },

  async aiChat(messages: Array<{ role: string; content: string }>): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('ai:chat', { messages })) as string;
  },

  async aiGenerateImage(prompt: string): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('ai:generate-image', { prompt })) as string;
  },

  async portraitSave(projectRoot: string, characterId: string, imageData: string): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('portrait:save', { projectRoot, characterId, imageData })) as string;
  },

  async portraitUpload(projectRoot: string, characterId: string, sourcePath: string): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('portrait:upload', { projectRoot, characterId, sourcePath })) as string;
  },

  aiStreamStart(requestId: string, messages: Array<{ role: string; content: string }>): void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return;
    ipcRenderer.send('ai:stream-start', { requestId, messages });
  },

  aiStreamCancel(requestId: string): void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return;
    ipcRenderer.send('ai:stream-cancel', { requestId });
  },

  onAIChunk(requestId: string, callback: (text: string) => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    const channel = `ai:chunk:${requestId}`;
    ipcRenderer.on(channel, (_event: unknown, text: unknown) => callback(text as string));
    return () => ipcRenderer.removeAllListeners(channel);
  },

  onAIDone(requestId: string, callback: () => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    const channel = `ai:done:${requestId}`;
    ipcRenderer.on(channel, () => callback());
    return () => ipcRenderer.removeAllListeners(channel);
  },

  onAIError(requestId: string, callback: (msg: string) => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    const channel = `ai:error:${requestId}`;
    ipcRenderer.on(channel, (_event: unknown, msg: unknown) => callback(msg as string));
    return () => ipcRenderer.removeAllListeners(channel);
  },

  // DB methods
  async dbOpen(projectRoot: string, projectJson?: unknown): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:open', { projectRoot, projectJson })) as { ok: boolean };
  },

  async dbClose(projectRoot: string): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:close', { projectRoot })) as { ok: boolean };
  },

  async dbUpsert(projectRoot: string, table: string, id: string, data: unknown): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:upsert', { projectRoot, table, id, data })) as { ok: boolean };
  },

  async dbGetAll(projectRoot: string, table: string): Promise<unknown[]> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    return (await ipcRenderer.invoke('db:getAll', { projectRoot, table })) as unknown[];
  },

  async dbDelete(projectRoot: string, table: string, id: string): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:delete', { projectRoot, table, id })) as { ok: boolean };
  },

  async dbSearch(projectRoot: string, query: string): Promise<Array<{ entity_type: string; entity_id: string; title: string }>> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    return (await ipcRenderer.invoke('db:search', { projectRoot, query })) as Array<{ entity_type: string; entity_id: string; title: string }>;
  },
};
