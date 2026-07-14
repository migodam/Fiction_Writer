import type { WorldContainer, WorldItem } from '../models/project';
import { useProjectStore } from '../store';
import { commandClipboard } from './clipboard';
import type { AppCommand, CommandContext } from './types';

export interface WorldItemMenuContext extends CommandContext {
  item: WorldItem;
  containerId: string;
  addWorldItem: (item: WorldItem) => void;
  deleteWorldItem: (id: string) => void;
  rename: () => void;
  remove: () => void;
}

export const getWorldItemContextCommands = (canPaste: boolean): AppCommand<WorldItemMenuContext>[] => [
  { id: 'world-item-new', label: 'New', execute: ({ item, containerId, addWorldItem }) => addWorldItem({ ...item, id: `world_${Date.now()}`, containerId, name: 'New Entry', description: '', attributes: [], mapMarkers: [] }) },
  { id: 'world-item-copy', label: 'Copy', shortcut: 'Ctrl+C', execute: ({ item }) => commandClipboard.set('world-item', 'copy', item) },
  { id: 'world-item-cut', label: 'Cut', shortcut: 'Ctrl+X', execute: ({ item }) => commandClipboard.set('world-item', 'cut', item) },
  {
    id: 'world-item-paste', label: 'Paste', shortcut: 'Ctrl+V', disabled: !canPaste,
    disabledReason: canPaste ? undefined : 'Copy a world item first',
    execute: ({ containerId, addWorldItem }) => {
      const entry = commandClipboard.get<WorldItem>('world-item');
      if (!entry) return;
      if (entry.operation === 'cut') useProjectStore.getState().moveWorldItem(entry.value.id, containerId);
      else addWorldItem({ ...entry.value, id: `world_${Date.now()}`, containerId, name: `${entry.value.name} (copy)` });
      commandClipboard.clear();
    },
  },
  { id: 'world-item-rename', label: 'Rename', execute: ({ rename }) => rename() },
  { id: 'world-item-move', label: 'Move', disabled: true, disabledReason: 'Drag the item onto a folder to move it', execute: () => undefined },
  { id: 'world-item-merge', label: 'Merge', disabled: true, disabledReason: 'World item merge is not available yet', execute: () => undefined },
  { id: 'world-item-delete', label: 'Delete', destructive: true, execute: ({ remove }) => remove() },
];

export interface WorldFolderMenuContext extends CommandContext {
  folder: WorldContainer;
  addWorldContainer: (container: WorldContainer) => void;
  setRenaming: () => void;
  remove: () => void;
}

export const getWorldFolderContextCommands = (): AppCommand<WorldFolderMenuContext>[] => [
  { id: 'world-folder-new', label: 'New', execute: ({ folder, addWorldContainer }) => addWorldContainer({ id: `cont_${Date.now()}`, name: 'New Folder', type: 'notebook', parentId: folder.id, sortOrder: (folder.sortOrder ?? 0) + 1, isCollapsed: false }) },
  { id: 'world-folder-copy', label: 'Copy', shortcut: 'Ctrl+C', execute: ({ folder }) => commandClipboard.set('world-folder', 'copy', folder) },
  { id: 'world-folder-cut', label: 'Cut', shortcut: 'Ctrl+X', disabled: true, disabledReason: 'Folder cut is unavailable because child items must stay linked', execute: () => undefined },
  { id: 'world-folder-paste', label: 'Paste', shortcut: 'Ctrl+V', disabled: true, disabledReason: 'Pasting folders is not available yet', execute: () => undefined },
  { id: 'world-folder-rename', label: 'Rename', execute: ({ setRenaming }) => setRenaming() },
  { id: 'world-folder-move', label: 'Move', disabled: true, disabledReason: 'Folder move is not available yet', execute: () => undefined },
  { id: 'world-folder-merge', label: 'Merge', disabled: true, disabledReason: 'Folder merge is not available yet', execute: () => undefined },
  { id: 'world-folder-delete', label: 'Delete', destructive: true, execute: ({ remove }) => remove() },
];
