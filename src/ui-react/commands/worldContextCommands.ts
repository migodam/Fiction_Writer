import type { WorldContainer, WorldItem } from "../models/project";
import { useProjectStore } from "../store";
import { commandClipboard } from "./clipboard";
import type { AppCommand, CommandContext } from "./types";

export interface WorldItemMenuContext extends CommandContext {
  item: WorldItem;
  containerId: string;
  addWorldItem: (item: WorldItem) => void;
  deleteWorldItem: (id: string) => void;
  rename: () => void;
  open: () => void;
  remove: () => void;
}

export const getWorldItemContextCommands = (
  canPaste: boolean,
): AppCommand<WorldItemMenuContext>[] => [
  {
    id: "world-item-open",
    label: { key: "contextMenu.world.open", fallback: "Open" },
    execute: ({ open }) => open(),
  },
  {
    id: "world-item-edit",
    label: { key: "contextMenu.edit", fallback: "Edit" },
    execute: ({ rename }) => rename(),
  },
  {
    id: "world-item-duplicate",
    label: { key: "contextMenu.duplicate", fallback: "Duplicate" },
    execute: ({ item, containerId, addWorldItem }) =>
      addWorldItem({
        ...item,
        id: `world_${Date.now()}`,
        folderId: containerId,
        containerId,
        name: `${item.name} (copy)`,
      }),
  },
  {
    id: "world-item-copy",
    label: { key: "contextMenu.copy", fallback: "Copy" },
    shortcut: "Ctrl+C",
    execute: ({ item }) => commandClipboard.set("world-item", "copy", item),
  },
  {
    id: "world-item-cut",
    label: { key: "contextMenu.cut", fallback: "Cut" },
    shortcut: "Ctrl+X",
    execute: ({ item }) => commandClipboard.set("world-item", "cut", item),
  },
  {
    id: "world-item-paste",
    label: { key: "contextMenu.paste", fallback: "Paste" },
    shortcut: "Ctrl+V",
    disabled: !canPaste,
    disabledReason: canPaste
      ? undefined
      : {
          key: "contextMenu.world.pasteUnavailable",
          fallback: "Copy a world item first",
        },
    execute: ({ containerId, addWorldItem }) => {
      const entry = commandClipboard.get<WorldItem>("world-item");
      if (!entry) return;
      if (entry.operation === "cut")
        useProjectStore.getState().moveWorldItem(entry.value.id, containerId);
      else
        addWorldItem({
          ...entry.value,
          id: `world_${Date.now()}`,
          folderId: containerId,
          containerId,
          name: `${entry.value.name} (copy)`,
        });
      commandClipboard.clear();
    },
  },
  {
    id: "world-item-rename",
    label: { key: "contextMenu.rename", fallback: "Rename" },
    execute: ({ rename }) => rename(),
  },
  {
    id: "world-item-delete",
    label: { key: "contextMenu.delete", fallback: "Delete" },
    destructive: true,
    execute: ({ remove }) => remove(),
  },
];

export interface WorldFolderMenuContext extends CommandContext {
  folder: WorldContainer;
  addWorldContainer: (container: WorldContainer) => void;
  addWorldItem: (item: WorldItem) => void;
  setRenaming: () => void;
  remove: () => void;
}

export const getWorldFolderContextCommands =
  (canPaste: boolean): AppCommand<WorldFolderMenuContext>[] => [
    {
      id: "world-folder-new",
      label: { key: "contextMenu.new", fallback: "New" },
      execute: ({ folder, addWorldContainer }) =>
        addWorldContainer({
          id: `cont_${Date.now()}`,
          name: "New Folder",
          type: "notebook",
          parentId: folder.id,
          sortOrder: (folder.sortOrder ?? 0) + 1,
          isCollapsed: false,
        }),
    },
    {
      id: "world-folder-paste",
      label: { key: "contextMenu.paste", fallback: "Paste" },
      shortcut: "Ctrl+V",
      disabled: !canPaste,
      disabledReason: canPaste
        ? undefined
        : {
            key: "contextMenu.world.pasteUnavailable",
            fallback: "Copy a world item first",
          },
      execute: ({ folder, addWorldItem }) => {
        const entry = commandClipboard.get<WorldItem>("world-item");
        if (!entry) return;
        if (entry.operation === "cut")
          useProjectStore.getState().moveWorldItem(entry.value.id, folder.id);
        else
          addWorldItem({
            ...entry.value,
            id: `world_${Date.now()}`,
            folderId: folder.id,
            containerId: folder.id,
            name: `${entry.value.name} (copy)`,
          });
        commandClipboard.clear();
      },
    },
    {
      id: "world-folder-rename",
      label: { key: "contextMenu.rename", fallback: "Rename" },
      execute: ({ setRenaming }) => setRenaming(),
    },
    {
      id: "world-folder-delete",
      label: { key: "contextMenu.delete", fallback: "Delete" },
      destructive: true,
      execute: ({ remove }) => remove(),
    },
  ];
