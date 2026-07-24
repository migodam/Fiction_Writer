import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  Clock3,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileText,
  Folder,
  Globe,
  GripVertical,
  Map as MapIcon,
  NotebookTabs,
  Plus,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useProjectStore, useUIStore } from "../store";
import { cn } from "../utils";
import { useI18n } from "../i18n";
import type { WorldContainer, WorldItem } from "../models/project";
import { commandClipboard } from "../commands/clipboard";
import { toMenuItem } from "../commands/menu";
import {
  getWorldFolderContextCommands,
  getWorldItemContextCommands,
} from "../commands/worldContextCommands";

const CONTAMINATION_CONTAINER_NAMES = new Set([
  "人物关系图",
  "人物关系",
  "关系图",
  "关系网络",
  "事件时间线",
  "时间线",
  "时间轴",
]);

const CONTAMINATION_CONTAINER_IDS = new Set([
  "world_container_timeline",
  "world_container_relationships",
]);

function folderOwner(item: WorldItem) {
  return item.folderId ?? item.containerId;
}

function DraggableWorldItem({ item, isActive, onClick, onContextMenu }: { item: WorldItem; isActive: boolean; onClick: () => void; onContextMenu: (event: React.MouseEvent) => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: item.id });
  return <div ref={setNodeRef} data-testid={`world-item-${item.id}`} className={cn("group relative min-w-0 cursor-pointer border-b border-divider px-4 py-3 text-left", isActive ? "bg-selected" : "hover:bg-hover", isDragging && "opacity-40")} onClick={onClick} onContextMenu={onContextMenu}>
    <span data-testid={`world-item-drag-handle-${item.id}`} {...listeners} {...attributes} className="absolute left-1 top-1/2 -translate-y-1/2 cursor-grab opacity-0 group-hover:opacity-40 active:cursor-grabbing" onClick={(event) => event.stopPropagation()} onContextMenu={(event) => event.stopPropagation()}><GripVertical size={12} /></span>
    <div className="min-w-0 truncate text-sm font-black text-text">{item.name}</div>
    <div className="mt-1 line-clamp-2 min-w-0 break-words text-xs leading-relaxed text-text-3">{item.description}</div>
  </div>;
}

function WorldNotebookWorkspace() {
  const navigate = useNavigate();
  const { locale, openContextMenu, setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const {
    worldContainers,
    worldItems,
    timelineEvents,
    timelineBranches,
    scenes,
    chapters,
    characters,
    addWorldContainer,
    addWorldItem,
    updateWorldContainer,
    updateWorldItem,
    deleteWorldContainer,
    deleteWorldItem,
    moveWorldItem,
  } = useProjectStore();
  const tr = useCallback((english: string, chinese: string) => locale === "zh-CN" ? chinese : english, [locale]);
  const containers = useMemo(
    () => worldContainers
      .filter((container) => !CONTAMINATION_CONTAINER_NAMES.has(container.name.trim()))
      .filter((container) => !CONTAMINATION_CONTAINER_IDS.has(container.id))
      .sort((left, right) => (left.sortOrder ?? 0) - (right.sortOrder ?? 0)),
    [worldContainers],
  );
  const notebooks = useMemo(
    () => containers.filter((container) => !container.parentId),
    [containers],
  );
  const [activeNotebookId, setActiveNotebookId] = useState<string | null>(notebooks[0]?.id ?? null);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(notebooks[0]?.id ?? null);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null);
  const [renamingFolderId, setRenamingFolderId] = useState<string | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  useEffect(() => {
    const notebook = notebooks.find((entry) => entry.id === activeNotebookId) ?? notebooks[0] ?? null;
    if (notebook && notebook.id !== activeNotebookId) setActiveNotebookId(notebook.id);
    if (notebook && !containers.some((entry) => entry.id === activeFolderId)) setActiveFolderId(notebook.id);
  }, [activeFolderId, activeNotebookId, containers, notebooks]);

  const activeNotebook = notebooks.find((entry) => entry.id === activeNotebookId) ?? null;
  const activeFolder = containers.find((entry) => entry.id === activeFolderId) ?? activeNotebook;
  const activeItem = worldItems.find((entry) => entry.id === activeItemId) ?? null;
  const folderItems = useMemo(
    () => worldItems.filter((item) => folderOwner(item) === activeFolder?.id),
    [activeFolder?.id, worldItems],
  );
  const childrenFor = useCallback((parentId: string) => containers.filter((entry) => entry.parentId === parentId), [containers]);
  const branchById = useMemo(() => new Map(timelineBranches.map((branch) => [branch.id, branch])), [timelineBranches]);

  const linkedEvents = useMemo(() => {
    if (!activeItem) return [];
    const ids = new Set(activeItem.linkedEventIds);
    timelineEvents.forEach((event) => {
      if (event.locationIds.includes(activeItem.id) || event.linkedWorldItemIds.includes(activeItem.id)) ids.add(event.id);
    });
    return Array.from(ids).map((id) => ({ id, event: timelineEvents.find((entry) => entry.id === id) ?? null }));
  }, [activeItem, timelineEvents]);
  const linkedScenes = useMemo(() => {
    if (!activeItem) return [];
    const ids = new Set(activeItem.linkedSceneIds);
    scenes.forEach((scene) => { if (scene.linkedWorldItemIds.includes(activeItem.id)) ids.add(scene.id); });
    return Array.from(ids).map((id) => ({ id, scene: scenes.find((entry) => entry.id === id) ?? null }));
  }, [activeItem, scenes]);

  const createNotebook = () => {
    const id = `world_notebook_${Date.now()}`;
    addWorldContainer({ id, name: tr("New notebook", "新笔记本"), type: "notebook", sortOrder: containers.length, parentId: null, isCollapsed: false });
    setActiveNotebookId(id);
    setActiveFolderId(id);
  };
  const createFolder = () => {
    if (!activeFolder) return;
    const id = `world_folder_${Date.now()}`;
    addWorldContainer({ id, name: tr("New folder", "新文件夹"), type: "notebook", sortOrder: containers.length, parentId: activeFolder.id, isCollapsed: false });
    setActiveFolderId(id);
  };
  const createItem = () => {
    if (!activeFolder) return;
    const id = `world_item_${Date.now()}`;
    addWorldItem({
      id,
      folderId: activeFolder.id,
      containerId: activeFolder.id,
      type: "note",
      name: tr("New entry", "新条目"),
      description: "",
      attributes: [],
      linkedCharacterIds: [],
      linkedEventIds: [],
      linkedSceneIds: [],
      mapMarkers: [],
      tagIds: [],
    });
    setActiveItemId(id);
  };
  const finishDrag = () => setDraggingItemId(null);
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    finishDrag();
    const targetId = String(over?.id ?? "");
    if (!targetId.startsWith("world-folder-drop-")) return;
    const folderId = targetId.slice("world-folder-drop-".length);
    const itemId = String(active.id);
    const item = worldItems.find((entry) => entry.id === itemId);
    if (!item || !containers.some((entry) => entry.id === folderId) || folderOwner(item) === folderId) return;
    moveWorldItem(itemId, folderId);
    setActiveFolderId(folderId);
    setLastActionStatus(tr("Entry moved", "条目已移动"));
  };
  const openItemContextMenu = (item: WorldItem, event: React.MouseEvent) => {
    event.preventDefault();
    const context = {
      target: { kind: "world-item" as const, id: item.id }, source: "context-menu" as const, item,
      containerId: folderOwner(item), addWorldItem, deleteWorldItem,
      rename: () => setActiveItemId(item.id), open: () => setActiveItemId(item.id),
      remove: () => { deleteWorldItem(item.id); if (activeItemId === item.id) setActiveItemId(null); },
    };
    openContextMenu({
      x: event.clientX, y: event.clientY, returnFocus: event.currentTarget as HTMLElement,
      items: getWorldItemContextCommands(Boolean(commandClipboard.get<WorldItem>("world-item"))).map((command) => toMenuItem(command, context, t)),
    });
  };

  const openFolderContextMenu = (folder: WorldContainer, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const context = {
      target: { kind: "world-folder" as const, id: folder.id },
      source: "context-menu" as const,
      folder,
      addWorldContainer,
      addWorldItem,
      setRenaming: () => { setActiveFolderId(folder.id); setRenamingFolderId(folder.id); },
      remove: () => { deleteWorldContainer(folder.id); if (activeFolderId === folder.id) setActiveFolderId(folder.parentId ?? activeNotebookId); },
    };
    openContextMenu({ x: event.clientX, y: event.clientY, returnFocus: event.currentTarget as HTMLElement, items: getWorldFolderContextCommands(Boolean(commandClipboard.get<WorldItem>("world-item"))).map((command) => toMenuItem(command, context, t)) });
  };

  const commitFolderRename = (folder: WorldContainer, name: string) => {
    const trimmed = name.trim();
    if (trimmed && trimmed !== folder.name) updateWorldContainer({ ...folder, name: trimmed });
    setRenamingFolderId(null);
  };

  const renderFolder = (folder: WorldContainer, depth: number): React.ReactNode => (
    <FolderTreeNode
      key={folder.id}
      folder={folder}
      depth={depth}
      active={folder.id === activeFolder?.id}
      onSelect={() => setActiveFolderId(folder.id)}
      onToggle={() => updateWorldContainer({ ...folder, isCollapsed: !folder.isCollapsed })}
      onContextMenu={(event) => openFolderContextMenu(folder, event)}
    >
      {!folder.isCollapsed && childrenFor(folder.id).map((child) => renderFolder(child, depth + 1))}
    </FolderTreeNode>
  );

  return (
    <div className="flex h-full min-w-0 overflow-hidden bg-bg" data-testid="world-notebook-workspace">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-bg-elev-1 min-[1440px]:flex">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div><div className="text-[10px] font-black uppercase tracking-[0.18em] text-brand-2">{tr("Notebooks", "笔记本")}</div></div>
          <button type="button" data-testid="create-container-btn" title={tr("New notebook", "新建笔记本")} className="rounded border border-border p-1.5 text-brand hover:border-brand" onClick={createNotebook}><Plus size={15} /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2" data-testid="world-container-list" onContextMenu={(event) => { if (activeNotebook) openFolderContextMenu(activeNotebook, event); }}>
          {notebooks.map((notebook) => (
            <div key={notebook.id} onContextMenu={(event) => openFolderContextMenu(notebook, event)}>
              {renamingFolderId === notebook.id ? <input autoFocus data-testid="world-container-rename-input" defaultValue={notebook.name} className="mb-1 w-full rounded border border-brand bg-bg px-3 py-2 text-sm text-text outline-none" onBlur={(event) => commitFolderRename(notebook, event.currentTarget.value)} onKeyDown={(event) => { if (event.key === "Enter") commitFolderRename(notebook, event.currentTarget.value); if (event.key === "Escape") setRenamingFolderId(null); }} /> : <button type="button" data-testid={`world-container-${notebook.id}`} className={cn("mb-1 flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm", notebook.id === activeNotebook?.id ? "bg-selected text-text" : "text-text-2 hover:bg-hover")} onClick={() => { setActiveNotebookId(notebook.id); setActiveFolderId(notebook.id); }} onContextMenu={(event) => openFolderContextMenu(notebook, event)}><NotebookTabs size={15} className="shrink-0 text-brand" />{notebook.name}</button>}
            </div>
          ))}
          {!notebooks.length && <EmptyWorldState text={tr("Create a notebook to begin organizing the world.", "新建笔记本以开始整理世界观。")} />}
        </div>
      </aside>

      <aside className="flex w-64 min-w-[15rem] max-w-[17rem] shrink-0 flex-col border-r border-border bg-bg">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="min-w-0 flex-1"><div className="text-[10px] font-black uppercase tracking-[0.18em] text-brand-2">{tr("Folders", "文件夹")}</div><select aria-label={tr("Notebook", "笔记本")} data-testid="world-notebook-select" value={activeNotebook?.id ?? ""} onChange={(event) => { setActiveNotebookId(event.target.value); setActiveFolderId(event.target.value); }} className="mt-0.5 max-w-full truncate bg-transparent text-sm font-bold text-text outline-none min-[1440px]:pointer-events-none min-[1440px]:appearance-none"><option value="">{tr("No notebook", "未选择笔记本")}</option>{notebooks.map((notebook) => <option key={notebook.id} value={notebook.id}>{notebook.name}</option>)}</select></div>
          <button type="button" data-testid="add-world-folder-btn" title={tr("New folder", "新建文件夹")} className="rounded border border-border p-1.5 text-brand hover:border-brand" onClick={createFolder} disabled={!activeFolder}><Plus size={15} /></button>
        </div>
        <DndContext sensors={sensors} onDragStart={({ active }) => setDraggingItemId(String(active.id))} onDragEnd={handleDragEnd} onDragCancel={finishDrag}>
          <div className="min-h-0 flex-1 overflow-y-auto p-2" data-testid="world-folder-tree">
            {activeNotebook && renderFolder(activeNotebook, 0)}
          </div>
          <div className="border-t border-border px-4 py-3"><button type="button" data-testid="add-world-item-btn" className="flex w-full items-center justify-center gap-2 rounded bg-brand px-3 py-2 text-xs font-bold text-white disabled:opacity-50" onClick={createItem} disabled={!activeFolder}><Plus size={14} />{tr("New entry", "新建条目")}</button></div>
          <div className="max-h-[38%] overflow-y-auto border-t border-border" data-testid="world-item-list">
            {folderItems.map((item) => <DraggableWorldItem key={item.id} item={item} isActive={item.id === activeItem?.id} onClick={() => setActiveItemId(item.id)} onContextMenu={(event) => openItemContextMenu(item, event)} />)}
            {!folderItems.length && <EmptyWorldState text={tr("No entries in this folder.", "此文件夹暂无条目。")} />}
          </div>
          <DragOverlay>{draggingItemId ? <div className="rounded border border-border bg-card px-3 py-2 text-sm shadow-lg">{worldItems.find((item) => item.id === draggingItemId)?.name}</div> : null}</DragOverlay>
        </DndContext>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto p-6 sm:p-8">
        {activeItem ? <WorldItemDetail item={activeItem} events={linkedEvents} scenes={linkedScenes} chapters={chapters} characters={characters} branches={branchById} locale={locale} onUpdate={updateWorldItem} onSave={() => { updateWorldItem(activeItem); setLastActionStatus(tr("Saved", "已保存")); }} onOpenEvent={(id) => navigate(`/timeline/timeline?event=${id}`)} onOpenAll={() => navigate(`/timeline/timeline?worldItem=${activeItem.id}`)} onOpenScene={(id) => navigate(`/writing/scenes?scene=${id}`)} /> : <div className="flex h-full min-h-72 items-center justify-center"><EmptyWorldState text={tr("Select an entry to view its evidence and narrative links.", "选择条目以查看证据和叙事关联。")} /></div>}
      </main>
    </div>
  );
}

function FolderTreeNode({ folder, depth, active, onSelect, onToggle, onContextMenu, children }: { folder: WorldContainer; depth: number; active: boolean; onSelect: () => void; onToggle: () => void; onContextMenu: (event: React.MouseEvent) => void; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: `world-folder-drop-${folder.id}` });
  return <div ref={setNodeRef} data-testid={`world-folder-drop-${folder.id}`} className={cn("rounded", isOver && "bg-brand/15")}>
    <div onContextMenu={onContextMenu} className={cn("flex items-center gap-1 rounded px-1 py-1 text-sm", active ? "bg-selected text-text" : "text-text-2 hover:bg-hover")} style={{ paddingLeft: `${depth * 14 + 4}px` }}>
      <button type="button" title={folder.isCollapsed ? "Expand" : "Collapse"} className="rounded p-0.5" onClick={onToggle}>{folder.isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}</button>
      <button type="button" data-testid={`world-folder-${folder.id}`} className="flex min-w-0 flex-1 items-center gap-2 truncate text-left" onClick={onSelect}><Folder size={14} className="shrink-0 text-brand" /><span className="truncate">{folder.name}</span></button>
    </div>
    {children}
  </div>;
}

function WorldItemDetail({ item, events, scenes, chapters, characters, branches, locale, onUpdate, onSave, onOpenEvent, onOpenAll, onOpenScene }: { item: WorldItem; events: { id: string; event: import("../models/project").TimelineEvent | null }[]; scenes: { id: string; scene: import("../models/project").Scene | null }[]; chapters: import("../models/project").Chapter[]; characters: import("../models/project").Character[]; branches: Map<string, import("../models/project").TimelineBranch>; locale: string; onUpdate: (item: WorldItem) => void; onSave: () => void; onOpenEvent: (id: string) => void; onOpenAll: () => void; onOpenScene: (id: string) => void }) {
  const tr = (english: string, chinese: string) => locale === "zh-CN" ? chinese : english;
  const updateAttribute = (index: number, field: "key" | "value", value: string) => onUpdate({ ...item, attributes: item.attributes.map((attribute, attributeIndex) => attributeIndex === index ? { ...attribute, [field]: value } : attribute) });
  const removeAttribute = (index: number) => onUpdate({ ...item, attributes: item.attributes.filter((_, attributeIndex) => attributeIndex !== index) });
  return <div className="mx-auto min-w-0 max-w-5xl space-y-7" data-testid={`world-item-detail-${item.id}`}>
    <div className="flex min-w-0 items-start justify-between gap-4"><div className="min-w-0 flex-1"><div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{tr("World entry", "世界条目")}</div><input data-testid="world-item-name-input" value={item.name} onChange={(event) => onUpdate({ ...item, name: event.target.value })} className="w-full bg-transparent text-3xl font-black text-text outline-none" /></div><button type="button" data-testid="inspector-save" onClick={onSave} className="shrink-0 rounded bg-brand px-3 py-2 text-xs font-bold text-white hover:opacity-90">{tr("Save", "保存")}</button></div>
    <textarea data-testid="world-item-description-input" value={item.description} onChange={(event) => onUpdate({ ...item, description: event.target.value })} className="h-36 w-full rounded border border-border bg-bg p-4 text-sm leading-relaxed text-text outline-none" placeholder={tr("Description", "描述")} />
    <section className="min-w-0 border-t border-border pt-5" data-testid="world-item-attributes"><div className="mb-3 flex items-center justify-between gap-3"><h2 className="text-sm font-bold text-text">{tr("Attributes", "自定义属性")}</h2><button type="button" data-testid="dynamic-field-add-row" onClick={() => onUpdate({ ...item, attributes: [...item.attributes, { key: "", value: "" }] })} className="inline-flex items-center gap-1 rounded border border-border bg-card px-2.5 py-1.5 text-xs font-bold text-brand hover:border-brand"><Plus size={13} />{tr("Add", "新增")}</button></div><div className="space-y-2">{item.attributes.map((attribute, index) => <div key={`${item.id}-attribute-${index}`} data-testid={`dynamic-field-row-${index}`} className="grid min-w-0 grid-cols-[minmax(7rem,0.8fr)_minmax(9rem,1.4fr)_2rem] items-center gap-2"><input data-testid={index === 0 ? "dynamic-field-key-input" : `dynamic-field-key-input-${index}`} aria-label={tr("Attribute name", "属性名称")} value={attribute.key} onChange={(event) => updateAttribute(index, "key", event.target.value)} placeholder={tr("Name", "名称")} className="min-w-0 rounded border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-brand" /><input data-testid={index === 0 ? "dynamic-field-value-input" : `dynamic-field-value-input-${index}`} aria-label={tr("Attribute value", "属性值")} value={attribute.value} onChange={(event) => updateAttribute(index, "value", event.target.value)} placeholder={tr("Value", "值")} className="min-w-0 rounded border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-brand" /><button type="button" data-testid={`dynamic-field-delete-${index}`} title={tr("Delete attribute", "删除属性")} aria-label={tr("Delete attribute", "删除属性")} onClick={() => removeAttribute(index)} className="flex h-8 w-8 items-center justify-center rounded text-text-3 hover:bg-hover hover:text-red"><Trash2 size={14} /></button></div>)}{!item.attributes.length && <div className="rounded border border-dashed border-border px-3 py-4 text-center text-xs text-text-3">{tr("No custom attributes", "暂无自定义属性")}</div>}</div></section>
    <section className="min-w-0 border-y border-border py-5"><div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-2"><h2 className="text-sm font-bold text-text">{tr("Timeline events", "关联事件")}</h2><button type="button" data-testid="open-world-timeline-btn" onClick={onOpenAll} className="inline-flex shrink-0 items-center gap-1 text-xs font-bold text-brand hover:underline"><Clock3 size={14} />{tr("View timeline", "查看时间线")}</button></div><div className="min-w-0 space-y-2">{events.map(({ id, event }) => event ? <button key={id} type="button" data-testid={`world-link-event-${id}`} onClick={() => onOpenEvent(id)} className="flex min-w-0 w-full items-start justify-between gap-3 rounded border border-border bg-card px-4 py-3 text-left hover:border-brand"><span className="min-w-0"><span className="block break-words text-sm font-bold text-text">{event.title}</span><span className="mt-1 block break-words text-xs text-text-3">{event.time || tr("Time unknown", "时间未知")} · {branches.get(event.branchId)?.name || tr("Missing branch", "缺失分支")}</span></span><ExternalLink size={14} className="mt-1 shrink-0 text-text-3" /></button> : <BrokenWorldReference key={id} testId={`world-broken-event-${id}`} text={`${tr("Missing event", "缺失事件")}: ${id}`} />)}{!events.length && <EmptyWorldState text={tr("No linked timeline events.", "没有关联时间线事件。")} />}</div></section>
    <section className="min-w-0 border-b border-border pb-5"><h2 className="mb-3 text-sm font-bold text-text">{tr("Scenes", "关联场景")}</h2><div className="min-w-0 space-y-2">{scenes.map(({ id, scene }) => { if (!scene) return <BrokenWorldReference key={id} testId={`world-broken-scene-${id}`} text={`${tr("Missing scene", "缺失场景")}: ${id}`} />; const chapter = chapters.find((entry) => entry.id === scene.chapterId); const pov = characters.find((entry) => entry.id === scene.povCharacterId); return <button key={id} type="button" data-testid={`world-link-scene-${id}`} onClick={() => onOpenScene(id)} className="flex min-w-0 w-full items-start justify-between gap-3 rounded border border-border bg-card px-4 py-3 text-left hover:border-brand"><span className="min-w-0"><span className="block break-words text-sm font-bold text-text">{scene.title}</span><span className="mt-1 block break-words text-xs text-text-3">{chapter?.title || tr("Missing chapter", "缺失章节")} · {pov?.name || tr("No POV", "无 POV")}</span><span className="mt-1 line-clamp-2 block break-words text-xs text-text-2">{scene.summary || tr("No summary", "暂无摘要")}</span></span><FileText size={14} className="mt-1 shrink-0 text-text-3" /></button>; })}{!scenes.length && <EmptyWorldState text={tr("No linked scenes.", "没有关联场景。")} />}</div></section>
  </div>;
}

function EmptyWorldState({ text }: { text: string }) { return <div className="px-4 py-6 text-center text-xs leading-relaxed text-text-3">{text}</div>; }
function BrokenWorldReference({ testId, text }: { testId: string; text: string }) { return <div data-testid={testId} className="flex items-center gap-2 rounded border border-red/30 bg-red/5 px-3 py-2 text-xs text-red"><TriangleAlert size={14} />{text}</div>; }

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

export const WorldWorkspace = () => {
  const navigate = useNavigate();
  const { sidebarSection, openContextMenu, setLastActionStatus, locale } =
    useUIStore();
  const { t } = useI18n();
  const {
    worldContainers,
    worldItems,
    worldSettings,
    worldMaps,
    worldCategories,
    timelineEvents,
    scenes,
    addWorldContainer,
    addWorldItem,
    updateWorldItem,
    deleteWorldItem,
    moveWorldItemToCategory,
    updateWorldSettings,
    createWorldMap,
    updateWorldMap,
    updateWorldContainer,
    deleteWorldContainer,
    addWorldCategory,
    moveWorldCategory,
    toggleWorldCategoryCollapsed,
  } = useProjectStore();
  const [activeContainerId, setActiveContainerId] = useState(
    worldContainers[0]?.id || null,
  );
  const [activeItemId, setActiveItemId] = useState(worldItems[0]?.id || null);
  const [activeMapId, setActiveMapId] = useState(worldMaps[0]?.id || null);
  const [renamingContainerId, setRenamingContainerId] = useState<string | null>(
    null,
  );
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(
    null,
  );
  const [showCategoryTree, setShowCategoryTree] = useState(true);
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null);
  const folderLabel = locale === "zh-CN" ? "文件夹" : "Folder";
  const foldersLabel = locale === "zh-CN" ? "文件夹" : "Folders";
  const addFolderLabel = locale === "zh-CN" ? "添加文件夹" : "Add Folder";

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const activeContainer =
    worldContainers.find((container) => container.id === activeContainerId) ||
    worldContainers[0] ||
    null;
  const activeItem =
    worldItems.find((item) => item.id === activeItemId) || null;
  const activeMap =
    worldMaps.find((map) => map.id === activeMapId) || worldMaps[0] || null;
  const containerItems = useMemo(
    () => worldItems.filter((item) => item.containerId === activeContainer?.id),
    [worldItems, activeContainer],
  );
  const groupedItems = useMemo(() => {
    const base = selectedCategoryId
      ? containerItems.filter((item) => {
          if (item.categoryId) return item.categoryId === selectedCategoryId;
          const cat = worldCategories.find((c) => c.id === selectedCategoryId);
          return cat ? (item.categoryPath?.includes(cat.name) ?? false) : false;
        })
      : containerItems;

    const groups = new Map<string, typeof containerItems>();
    const ungrouped: typeof containerItems = [];
    for (const item of base) {
      const groupKey = item.categoryId
        ? (worldCategories.find((c) => c.id === item.categoryId)?.name ??
          item.categoryPath?.[1] ??
          null)
        : item.categoryPath && item.categoryPath.length >= 2
          ? item.categoryPath[1]
          : null;
      if (groupKey) {
        if (!groups.has(groupKey)) groups.set(groupKey, []);
        groups.get(groupKey)!.push(item);
      } else {
        ungrouped.push(item);
      }
    }
    return { groups, ungrouped };
  }, [containerItems, selectedCategoryId, worldCategories]);
  const visibleCategories = useMemo(() => {
    const hiddenRootIds = new Set(
      worldCategories
        .filter((c) => c.id === "wcat_root" || c.name === "世界模型")
        .map((c) => c.id),
    );
    return worldCategories
      .filter((c) => !hiddenRootIds.has(c.id))
      .map((c) => ({
        ...c,
        parentId:
          c.parentId !== null && hiddenRootIds.has(c.parentId)
            ? null
            : c.parentId,
      }));
  }, [worldCategories]);
  const notebookContainers = useMemo(
    () =>
      worldContainers
        .filter(
          (container) =>
            !CONTAMINATION_CONTAINER_NAMES.has(container.name.trim()),
        )
        .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0)),
    [worldContainers],
  );
  const notebookDepth = useCallback(
    (containerId: string) => {
      let depth = 0;
      let parentId =
        notebookContainers.find((container) => container.id === containerId)
          ?.parentId ?? null;
      const visited = new Set<string>([containerId]);
      while (parentId && !visited.has(parentId)) {
        const parent = notebookContainers.find(
          (container) => container.id === parentId,
        );
        if (!parent) break;
        visited.add(parentId);
        depth += 1;
        parentId = parent.parentId ?? null;
      }
      return depth;
    },
    [notebookContainers],
  );

  const activeMapMarkers = useMemo(() => {
    if (!activeMap) return [];
    return worldItems
      .flatMap((item) => item.mapMarkers)
      .filter((marker) => activeMap.markerIds.includes(marker.id));
  }, [activeMap, worldItems]);

  const finishDrag = (commit: boolean) => {
    const store = useProjectStore.getState();
    if (commit) store.commitUndoTransaction();
    else store.rollbackUndoTransaction();
    setDraggingItemId(null);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || !active) return finishDrag(false);
    const itemId = String(active.id);
    const overId = String(over.id);
    if (!overId.startsWith("category-header-")) return finishDrag(false);
    const targetGroupName = overId.replace("category-header-", "");

    // Find the container whose name matches the drop target group name
    const targetContainer = worldContainers.find(
      (c) =>
        c.name === targetGroupName || c.importCategoryKey === targetGroupName,
    );
    if (!targetContainer) return finishDrag(false);

    const item = worldItems.find((i) => i.id === itemId);
    if (!item || item.containerId === targetContainer.id)
      return finishDrag(false);

    const newCategory = (targetContainer as any).importCategoryKey ?? "concept";
    const newCategoryPath = [
      item.categoryPath?.[0] ?? "世界模型",
      targetContainer.name,
      item.name,
    ];
    const targetFolderNode = worldCategories.find(
      (c) =>
        c.name === targetGroupName ||
        c.id === (targetContainer as any).importCategoryKey,
    );
    moveWorldItemToCategory(
      itemId,
      newCategory,
      targetContainer.id,
      newCategoryPath,
      targetFolderNode?.id ?? null,
    );
    finishDrag(true);
  };

  const makeItemContextMenu = (item: WorldItem) => (e: React.MouseEvent) => {
    e.preventDefault();
    const context = {
      target: { kind: "world-item" as const, id: item.id },
      source: "context-menu" as const,
      item,
      containerId: activeContainer?.id ?? item.containerId,
      addWorldItem,
      deleteWorldItem,
      rename: () => {
        setActiveItemId(item.id);
        requestAnimationFrame(() =>
          document
            .querySelector<HTMLInputElement>(
              '[data-testid="world-item-name-input"]',
            )
            ?.focus(),
        );
      },
      open: () => setActiveItemId(item.id),
      remove: () => {
        deleteWorldItem(item.id);
        if (activeItemId === item.id) setActiveItemId(null);
        setLastActionStatus(t("world.itemDeleted", "World item deleted"));
      },
    };
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      returnFocus: e.currentTarget as HTMLElement,
      items: getWorldItemContextCommands(
        Boolean(commandClipboard.get<WorldItem>("world-item")),
      ).map((command) => toMenuItem(command, context, t)),
    });
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && draggingItemId) finishDrag(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [draggingItemId]);

  if (sidebarSection === "settings") {
    return (
      <div className="h-full overflow-y-auto custom-scrollbar bg-bg p-10">
        <div className="mx-auto max-w-5xl rounded-[32px] border border-border bg-card p-8">
          <div className="mb-8">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
              {t("world.settings", "World Settings")}
            </div>
            <div className="mt-2 text-3xl font-black text-text">
              {t("world.projectFoundations", "Project Foundations")}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field
              label={t("world.projectType", "Project Type")}
              value={worldSettings.projectType}
              onChange={(value) =>
                updateWorldSettings({ ...worldSettings, projectType: value })
              }
            />
            <Field
              label={t("world.narrativePacing", "Narrative Pacing")}
              value={worldSettings.narrativePacing}
              onChange={(value) =>
                updateWorldSettings({
                  ...worldSettings,
                  narrativePacing: value,
                })
              }
            />
            <Field
              label={t("world.languageStyle", "Language Style")}
              value={worldSettings.languageStyle}
              onChange={(value) =>
                updateWorldSettings({ ...worldSettings, languageStyle: value })
              }
            />
            <Field
              label={t("world.narrativePerspective", "Narrative Perspective")}
              value={worldSettings.narrativePerspective}
              onChange={(value) =>
                updateWorldSettings({
                  ...worldSettings,
                  narrativePerspective: value,
                })
              }
            />
            <Field
              label={t("world.lengthStrategy", "Length Strategy")}
              value={worldSettings.lengthStrategy}
              onChange={(value) =>
                updateWorldSettings({ ...worldSettings, lengthStrategy: value })
              }
            />
          </div>
          <div className="mt-6">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
              {t("world.worldRulesSummary", "World Rules Summary")}
            </div>
            <textarea
              value={worldSettings.worldRulesSummary}
              onChange={(event) =>
                updateWorldSettings({
                  ...worldSettings,
                  worldRulesSummary: event.target.value,
                })
              }
              className="h-52 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none"
            />
          </div>
        </div>
      </div>
    );
  }

  if (sidebarSection === "map") {
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <aside className="w-72 border-r border-border bg-bg-elev-1">
          <div className="border-b border-border bg-bg-elev-2 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
                  {t("world.maps", "Maps")}
                </div>
                <div className="text-sm font-black text-text">
                  {t("world.multipleMaps", "Multiple Maps")}
                </div>
              </div>
              <button
                type="button"
                className="rounded-xl border border-border p-2 text-brand hover:border-brand"
                onClick={() =>
                  createWorldMap({
                    id: `map_${Date.now()}`,
                    title: t("world.newMap", "New Map"),
                    description: "",
                    assetPath: activeMap?.assetPath || null,
                    markerIds: [],
                    sortOrder: worldMaps.length,
                  })
                }
              >
                <Plus size={16} />
              </button>
            </div>
          </div>
          <div className="h-full overflow-y-auto custom-scrollbar p-2">
            {worldMaps.map((map) => (
              <button
                key={map.id}
                type="button"
                className={cn(
                  "mb-2 w-full rounded-2xl border px-4 py-4 text-left",
                  activeMapId === map.id
                    ? "border-brand bg-selected"
                    : "border-border bg-card",
                )}
                onClick={() => setActiveMapId(map.id)}
              >
                <div className="text-sm font-black text-text">{map.title}</div>
                <div className="mt-2 text-xs text-text-2">
                  {map.description ||
                    t("world.noDescription", "No description")}
                </div>
              </button>
            ))}
          </div>
        </aside>
        <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
          {activeMap ? (
            <div className="mx-auto max-w-6xl">
              <div className="mb-8 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
                    {t("world.currentMap", "Current Map")}
                  </div>
                  <div className="mt-2 text-3xl font-black text-text">
                    {activeMap.title}
                  </div>
                </div>
                <MapIcon size={24} className="text-brand" />
              </div>
              <div className="rounded-3xl border border-border bg-card p-4">
                <div className="relative overflow-hidden rounded-2xl border border-border bg-bg">
                  {activeMap.assetPath ? (
                    <img
                      src={activeMap.assetPath}
                      alt={activeMap.title}
                      className="h-[560px] w-full object-cover"
                      data-testid="world-map-image"
                    />
                  ) : (
                    <div className="flex h-[560px] items-center justify-center text-text-3">
                      {t("world.noMapAsset", "No map asset")}
                    </div>
                  )}
                  {activeMapMarkers.map((marker) => (
                    <button
                      key={marker.id}
                      type="button"
                      data-testid="world-map-marker"
                      aria-label={`Open timeline for ${marker.label}`}
                      className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/20 bg-brand px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-white shadow-2"
                      style={{
                        left: `${marker.x * 100}%`,
                        top: `${marker.y * 100}%`,
                      }}
                      onClick={() =>
                        marker.linkedEntityId &&
                        navigate(
                          `/timeline/timeline?worldItem=${marker.linkedEntityId}`,
                        )
                      }
                    >
                      {marker.label}
                    </button>
                  ))}
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <input
                    value={activeMap.title}
                    onChange={(event) =>
                      updateWorldMap({
                        ...activeMap,
                        title: event.target.value,
                      })
                    }
                    className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                  />
                  <input
                    value={activeMap.description}
                    onChange={(event) =>
                      updateWorldMap({
                        ...activeMap,
                        description: event.target.value,
                      })
                    }
                    className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
                    placeholder={t("world.mapDescription", "Map description")}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </main>
      </div>
    );
  }

  return <WorldNotebookWorkspace />;
};

const Field = ({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) => (
  <label className="block">
    <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
      {label}
    </div>
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
    />
  </label>
);

const LinkPanel = ({
  title,
  items,
}: {
  title: string;
  items: { id: string; label: string; onClick: () => void }[];
}) => (
  <div className="rounded-3xl border border-border bg-card p-6">
    <div className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">
      {title}
    </div>
    <div className="space-y-3">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand"
          onClick={item.onClick}
        >
          <span className="text-sm font-bold text-text">{item.label}</span>
          <ExternalLink size={14} />
        </button>
      ))}
    </div>
  </div>
);
