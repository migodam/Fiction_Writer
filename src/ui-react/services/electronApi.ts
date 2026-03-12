export interface PickDirectoryResult {
  canceled: boolean;
  path: string | null;
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
};
