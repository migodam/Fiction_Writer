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
};
