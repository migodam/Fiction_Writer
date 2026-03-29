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

  async pickFiles(): Promise<string[]> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    const result = (await ipcRenderer.invoke('dialog:pick-files')) as { canceled: boolean; paths: string[] } | null;
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
};
