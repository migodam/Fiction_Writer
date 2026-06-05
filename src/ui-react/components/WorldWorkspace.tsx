import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ExternalLink, Globe, GripVertical, Map as MapIcon, Plus, Trash2 } from 'lucide-react';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { useI18n } from '../i18n';
import { TagTreePanel } from './TagTreePanel';
import type { WorldCategoryNode, WorldItem } from '../models/project';

const CONTAMINATION_CONTAINER_NAMES = new Set([
  '人物关系图', '人物关系', '关系图', '关系网络',
  '事件时间线', '时间线', '时间轴',
]);

// ---------------------------------------------------------------------------
// Drag/drop sub-components
// ---------------------------------------------------------------------------

function DraggableWorldItem({
  item,
  isActive,
  onClick,
  onContextMenu,
}: {
  item: WorldItem;
  isActive: boolean;
  onClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: item.id });
  return (
    <div
      ref={setNodeRef}
      data-testid={`world-item-${item.id}`}
      className={cn(
        'group relative w-full border-b border-divider px-4 py-4 text-left transition-colors cursor-pointer',
        isActive ? 'bg-selected' : 'hover:bg-hover',
        isDragging && 'opacity-40',
      )}
      onClick={onClick}
      onContextMenu={onContextMenu}
    >
      <span
        {...listeners}
        {...attributes}
        className="absolute left-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-40 cursor-grab active:cursor-grabbing"
        onClick={(e) => e.stopPropagation()}
        onContextMenu={(e) => e.stopPropagation()}
      >
        <GripVertical size={12} />
      </span>
      <div className="text-sm font-black text-text">{item.name}</div>
      <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-3">{item.description}</div>
    </div>
  );
}

function DroppableCategoryHeader({
  groupName,
  children,
}: {
  groupName: string;
  children: React.ReactNode;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: `category-header-${groupName}` });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        'sticky top-0 z-10 px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] border-b transition-colors',
        isOver
          ? 'bg-brand/20 text-brand border-brand/30'
          : 'bg-bg-elev-1 text-brand-2 border-divider',
      )}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main workspace
// ---------------------------------------------------------------------------

export const WorldWorkspace = () => {
  const navigate = useNavigate();
  const { sidebarSection, openContextMenu, setLastActionStatus } = useUIStore();
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
  const [activeContainerId, setActiveContainerId] = useState(worldContainers[0]?.id || null);
  const [activeItemId, setActiveItemId] = useState(worldItems[0]?.id || null);
  const [activeMapId, setActiveMapId] = useState(worldMaps[0]?.id || null);
  const [renamingContainerId, setRenamingContainerId] = useState<string | null>(null);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [showCategoryTree, setShowCategoryTree] = useState(true);
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const activeContainer = worldContainers.find((container) => container.id === activeContainerId) || worldContainers[0] || null;
  const activeItem = worldItems.find((item) => item.id === activeItemId) || null;
  const activeMap = worldMaps.find((map) => map.id === activeMapId) || worldMaps[0] || null;
  const containerItems = useMemo(() => worldItems.filter((item) => item.containerId === activeContainer?.id), [worldItems, activeContainer]);
  const groupedItems = useMemo(() => {
    const base = selectedCategoryId
      ? (() => {
          const cat = worldCategories.find((c) => c.id === selectedCategoryId);
          return containerItems.filter((item) => cat && item.categoryPath?.includes(cat.name));
        })()
      : containerItems;
    const groups = new Map<string, typeof containerItems>();
    const ungrouped: typeof containerItems = [];
    for (const item of base) {
      if (item.categoryPath && item.categoryPath.length >= 2) {
        const groupKey = item.categoryPath[1];
        if (!groups.has(groupKey)) groups.set(groupKey, []);
        groups.get(groupKey)!.push(item);
      } else {
        ungrouped.push(item);
      }
    }
    return { groups, ungrouped };
  }, [containerItems, selectedCategoryId, worldCategories]);
  const activeMapMarkers = useMemo(() => {
    if (!activeMap) return [];
    return worldItems.flatMap((item) => item.mapMarkers).filter((marker) => activeMap.markerIds.includes(marker.id));
  }, [activeMap, worldItems]);

  const handleDragEnd = (event: DragEndEvent) => {
    setDraggingItemId(null);
    const { active, over } = event;
    if (!over || !active) return;
    const itemId = String(active.id);
    const overId = String(over.id);
    if (!overId.startsWith('category-header-')) return;
    const targetGroupName = overId.replace('category-header-', '');

    // Find the container whose name matches the drop target group name
    const targetContainer = worldContainers.find(
      (c) => c.name === targetGroupName || c.importCategoryKey === targetGroupName,
    );
    if (!targetContainer) return;

    const item = worldItems.find((i) => i.id === itemId);
    if (!item || item.containerId === targetContainer.id) return;

    const newCategory = (targetContainer as any).importCategoryKey ?? 'concept';
    const newCategoryPath = [
      item.categoryPath?.[0] ?? '世界模型',
      targetContainer.name,
      item.name,
    ];
    moveWorldItemToCategory(itemId, newCategory, targetContainer.id, newCategoryPath);
  };

  const makeItemContextMenu = (item: WorldItem) => (e: React.MouseEvent) => {
    e.preventDefault();
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [{
        id: 'delete',
        label: t('common.delete'),
        action: () => {
          deleteWorldItem(item.id);
          if (activeItemId === item.id) setActiveItemId(null);
          setLastActionStatus(t('world.itemDeleted', 'World item deleted'));
        },
        destructive: true,
      }],
    });
  };

  if (sidebarSection === 'settings') {
    return (
      <div className="h-full overflow-y-auto custom-scrollbar bg-bg p-10">
        <div className="mx-auto max-w-5xl rounded-[32px] border border-border bg-card p-8">
          <div className="mb-8">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('world.settings', 'World Settings')}</div>
            <div className="mt-2 text-3xl font-black text-text">{t('world.projectFoundations', 'Project Foundations')}</div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label={t('world.projectType', 'Project Type')} value={worldSettings.projectType} onChange={(value) => updateWorldSettings({ ...worldSettings, projectType: value })} />
            <Field label={t('world.narrativePacing', 'Narrative Pacing')} value={worldSettings.narrativePacing} onChange={(value) => updateWorldSettings({ ...worldSettings, narrativePacing: value })} />
            <Field label={t('world.languageStyle', 'Language Style')} value={worldSettings.languageStyle} onChange={(value) => updateWorldSettings({ ...worldSettings, languageStyle: value })} />
            <Field label={t('world.narrativePerspective', 'Narrative Perspective')} value={worldSettings.narrativePerspective} onChange={(value) => updateWorldSettings({ ...worldSettings, narrativePerspective: value })} />
            <Field label={t('world.lengthStrategy', 'Length Strategy')} value={worldSettings.lengthStrategy} onChange={(value) => updateWorldSettings({ ...worldSettings, lengthStrategy: value })} />
          </div>
          <div className="mt-6">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('world.worldRulesSummary', 'World Rules Summary')}</div>
            <textarea value={worldSettings.worldRulesSummary} onChange={(event) => updateWorldSettings({ ...worldSettings, worldRulesSummary: event.target.value })} className="h-52 w-full rounded-3xl border border-border bg-bg p-5 text-sm leading-relaxed text-text-2 outline-none" />
          </div>
        </div>
      </div>
    );
  }

  if (sidebarSection === 'map') {
    return (
      <div className="flex h-full overflow-hidden bg-bg">
        <aside className="w-72 border-r border-border bg-bg-elev-1">
          <div className="border-b border-border bg-bg-elev-2 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('world.maps', 'Maps')}</div>
                <div className="text-sm font-black text-text">{t('world.multipleMaps', 'Multiple Maps')}</div>
              </div>
              <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => createWorldMap({ id: `map_${Date.now()}`, title: t('world.newMap', 'New Map'), description: '', assetPath: activeMap?.assetPath || null, markerIds: [], sortOrder: worldMaps.length })}>
                <Plus size={16} />
              </button>
            </div>
          </div>
          <div className="h-full overflow-y-auto custom-scrollbar p-2">
            {worldMaps.map((map) => (
              <button key={map.id} type="button" className={cn('mb-2 w-full rounded-2xl border px-4 py-4 text-left', activeMapId === map.id ? 'border-brand bg-selected' : 'border-border bg-card')} onClick={() => setActiveMapId(map.id)}>
                <div className="text-sm font-black text-text">{map.title}</div>
                <div className="mt-2 text-xs text-text-2">{map.description || t('world.noDescription', 'No description')}</div>
              </button>
            ))}
          </div>
        </aside>
        <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
          {activeMap ? (
            <div className="mx-auto max-w-6xl">
              <div className="mb-8 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('world.currentMap', 'Current Map')}</div>
                  <div className="mt-2 text-3xl font-black text-text">{activeMap.title}</div>
                </div>
                <MapIcon size={24} className="text-brand" />
              </div>
              <div className="rounded-3xl border border-border bg-card p-4">
                <div className="relative overflow-hidden rounded-2xl border border-border bg-bg">
                  {activeMap.assetPath ? (
                    <img src={activeMap.assetPath} alt={activeMap.title} className="h-[560px] w-full object-cover" data-testid="world-map-image" />
                  ) : (
                    <div className="flex h-[560px] items-center justify-center text-text-3">{t('world.noMapAsset', 'No map asset')}</div>
                  )}
                  {activeMapMarkers.map((marker) => (
                    <button key={marker.id} type="button" className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/20 bg-brand px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-white shadow-2" style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }} onClick={() => marker.linkedEntityId && navigate(`/timeline/timeline?location=${marker.linkedEntityId}`)}>
                      {marker.label}
                    </button>
                  ))}
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <input value={activeMap.title} onChange={(event) => updateWorldMap({ ...activeMap, title: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
                  <input value={activeMap.description} onChange={(event) => updateWorldMap({ ...activeMap, description: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('world.mapDescription', 'Map description')} />
                </div>
              </div>
            </div>
          ) : null}
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-72 border-r border-border bg-bg-elev-1">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('world.entries', 'World Entries')}</div>
              <div className="text-sm font-black text-text">{t('world.containersAndEntries', 'Containers and Entries')}</div>
            </div>
            <button type="button" data-testid="create-container-btn" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => addWorldContainer({ id: `cont_${Date.now()}`, name: t('world.newContainer', 'New Container'), type: 'notebook', sortOrder: worldContainers.length, isCollapsed: false })}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2" data-testid="world-container-list">
          {worldContainers
            .filter((container) => !CONTAMINATION_CONTAINER_NAMES.has(container.name.trim()))
            .map((container) => (
            <button
              key={container.id}
              type="button"
              data-testid={`world-container-${container.id}`}
              className={cn('mb-2 w-full rounded-2xl border px-4 py-4 text-left', activeContainerId === container.id ? 'border-brand bg-selected' : 'border-border bg-card')}
              onClick={() => setActiveContainerId(container.id)}
              onContextMenu={(e) => {
                e.preventDefault();
                openContextMenu({
                  x: e.clientX,
                  y: e.clientY,
                  items: [
                    {
                      id: 'rename',
                      label: t('world.renameContainer'),
                      action: () => setRenamingContainerId(container.id),
                    },
                    {
                      id: 'delete',
                      label: t('world.deleteContainer'),
                      action: () => {
                        deleteWorldContainer(container.id);
                        if (activeContainerId === container.id) setActiveContainerId(null);
                      },
                      destructive: true,
                    },
                  ],
                });
              }}
            >
              {renamingContainerId === container.id ? (
                <input
                  data-testid="world-container-rename-input"
                  autoFocus
                  className="w-full bg-transparent text-sm font-black text-text outline-none border-b border-brand"
                  defaultValue={container.name}
                  onClick={(e) => e.stopPropagation()}
                  onBlur={(e) => {
                    updateWorldContainer({ ...container, name: e.target.value });
                    setRenamingContainerId(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      updateWorldContainer({ ...container, name: e.currentTarget.value });
                      setRenamingContainerId(null);
                    } else if (e.key === 'Escape') {
                      setRenamingContainerId(null);
                    }
                  }}
                />
              ) : (
                <div className="text-sm font-black text-text">{container.name}</div>
              )}
              <div className="mt-2 text-xs text-text-2">{container.type}</div>
            </button>
          ))}
        </div>
      </aside>

      <aside className="w-80 border-r border-border bg-bg shadow-xl">
        <div className="border-b border-border bg-bg-elev-1 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{activeContainer?.type}</div>
              <div className="text-sm font-black text-text">{activeContainer?.name}</div>
            </div>
            <button type="button" data-testid="add-world-item-btn" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => {
              if (!activeContainer) return;
              const itemId = `item_${Date.now()}`;
              addWorldItem({ id: itemId, containerId: activeContainer.id, type: activeContainer.id.includes('location') ? 'location' : 'note', name: t('world.newEntry', 'New Entry'), description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], assetPath: null, tagIds: [] });
              setActiveItemId(itemId);
            }}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        {worldCategories.length > 0 && (
          <div className="border-b border-border">
            <button
              type="button"
              data-testid="world-category-tree-toggle"
              className="flex w-full items-center justify-between px-4 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-brand-2 hover:bg-hover"
              onClick={() => setShowCategoryTree((v) => !v)}
            >
              <span>{t('world.categories', 'Categories')}</span>
              <Plus size={12} className={showCategoryTree ? 'rotate-45 transition-transform' : 'transition-transform'} />
            </button>
            {showCategoryTree && (
              <div className="px-2 pb-2" data-testid="world-category-tree">
                <TagTreePanel<WorldCategoryNode>
                  nodes={worldCategories}
                  renderNodeContent={(node) => (
                    <button
                      type="button"
                      data-testid={`world-category-node-${node.id}`}
                      className={cn('w-full rounded-xl px-3 py-1.5 text-left text-xs font-bold transition-colors', selectedCategoryId === node.id ? 'bg-brand/15 text-brand-2' : 'text-text-2 hover:bg-hover')}
                      onClick={() => setSelectedCategoryId(selectedCategoryId === node.id ? null : node.id)}
                    >
                      {node.name}
                      <span className="ml-1 text-text-3">
                        ({containerItems.filter((i) => i.categoryPath?.includes(node.name)).length})
                      </span>
                    </button>
                  )}
                  onMove={(dragId, newParentId, insertBeforeSiblingId) => moveWorldCategory(dragId, newParentId, insertBeforeSiblingId)}
                  onToggleCollapse={toggleWorldCategoryCollapsed}
                  testIdPrefix="world-category"
                />
                <button
                  type="button"
                  data-testid="add-world-category-btn"
                  className="mt-2 flex w-full items-center gap-1 rounded-xl border border-dashed border-border px-3 py-1.5 text-xs text-text-3 hover:border-brand hover:text-brand"
                  onClick={() => {
                    const id = `wcat_${Date.now()}`;
                    addWorldCategory({ id, name: t('world.newCategory', 'New Category'), parentId: null, sortOrder: worldCategories.length, scope: 'world' });
                  }}
                >
                  <Plus size={10} />
                  {t('world.addCategory', 'Add Category')}
                </button>
              </div>
            )}
          </div>
        )}

        <DndContext
          sensors={sensors}
          onDragStart={(e: DragStartEvent) => setDraggingItemId(String(e.active.id))}
          onDragEnd={handleDragEnd}
        >
          <div className="h-full overflow-y-auto custom-scrollbar" data-testid="world-item-list">
            {groupedItems.groups.size > 0 ? (
              <>
                {Array.from(groupedItems.groups.entries()).map(([groupName, items]) => (
                  <div key={groupName} data-testid={`world-category-group-${groupName}`}>
                    <DroppableCategoryHeader groupName={groupName}>
                      {groupName}
                    </DroppableCategoryHeader>
                    {items.map((item) => (
                      <DraggableWorldItem
                        key={item.id}
                        item={item}
                        isActive={activeItemId === item.id}
                        onClick={() => setActiveItemId(item.id)}
                        onContextMenu={makeItemContextMenu(item)}
                      />
                    ))}
                  </div>
                ))}
                {groupedItems.ungrouped.map((item) => (
                  <DraggableWorldItem
                    key={item.id}
                    item={item}
                    isActive={activeItemId === item.id}
                    onClick={() => setActiveItemId(item.id)}
                    onContextMenu={makeItemContextMenu(item)}
                  />
                ))}
              </>
            ) : (
              containerItems.map((item) => (
                <DraggableWorldItem
                  key={item.id}
                  item={item}
                  isActive={activeItemId === item.id}
                  onClick={() => setActiveItemId(item.id)}
                  onContextMenu={makeItemContextMenu(item)}
                />
              ))
            )}
          </div>
          <DragOverlay>
            {draggingItemId && (() => {
              const item = worldItems.find((i) => i.id === draggingItemId);
              return item ? (
                <div className="bg-card border border-white/20 rounded-xl px-4 py-3 text-sm font-black text-text shadow-xl opacity-90">
                  {item.name}
                </div>
              ) : null;
            })()}
          </DragOverlay>
        </DndContext>
      </aside>

      <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
        {activeItem ? (
          <div className="mx-auto max-w-5xl space-y-8">
            <div>
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.entryName', 'Entry Name')}</div>
              <input data-testid="world-item-name-input" value={activeItem.name} onChange={(event) => updateWorldItem({ ...activeItem, name: event.target.value })} className="w-full bg-transparent text-5xl font-black tracking-tight outline-none" />
            </div>
            <div>
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.descriptionLabel', 'Description')}</div>
              <textarea data-testid="world-item-description-input" value={activeItem.description} onChange={(event) => updateWorldItem({ ...activeItem, description: event.target.value })} className="h-40 w-full rounded-3xl border border-border bg-bg p-5 font-serif text-sm leading-relaxed text-text-2 outline-none" />
            </div>
            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.attributes', 'Attributes')}</div>
                <button type="button" data-testid="dynamic-field-add-row" className="rounded-xl border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-2 hover:border-brand" onClick={() => updateWorldItem({ ...activeItem, attributes: [...activeItem.attributes, { key: '', value: '' }] })}>
                  {t('world.addRow', 'Add Row')}
                </button>
              </div>
              <div className="space-y-3">
                {activeItem.attributes.map((attribute, index) => (
                  <div key={`${attribute.key}-${index}`} className="flex gap-3">
                    <input data-testid="dynamic-field-key-input" value={attribute.key} onChange={(event) => updateWorldItem({ ...activeItem, attributes: activeItem.attributes.map((entry, entryIndex) => entryIndex === index ? { ...entry, key: event.target.value } : entry) })} className="flex-1 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('world.attribute', 'Attribute')} />
                    <input data-testid="dynamic-field-value-input" value={attribute.value} onChange={(event) => updateWorldItem({ ...activeItem, attributes: activeItem.attributes.map((entry, entryIndex) => entryIndex === index ? { ...entry, value: event.target.value } : entry) })} className="flex-[1.4] rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('world.value', 'Value')} />
                    <button type="button" className="rounded-2xl border border-red/40 px-3 text-red" onClick={() => updateWorldItem({ ...activeItem, attributes: activeItem.attributes.filter((_, entryIndex) => entryIndex !== index) })}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <button type="button" data-testid="inspector-save" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" onClick={() => setLastActionStatus('Saved')}>
              {t('common.save', 'Save')}
            </button>
            <div className="grid gap-6 lg:grid-cols-2">
              <LinkPanel title={t('world.linkedTimeline', 'Linked Timeline')} items={timelineEvents.filter((event) => event.linkedWorldItemIds.includes(activeItem.id) || event.locationIds.includes(activeItem.id)).map((event) => ({ id: event.id, label: event.title, onClick: () => navigate(`/timeline/timeline?event=${event.id}`) }))} />
              <LinkPanel title={t('world.linkedScenes', 'Linked Scenes')} items={scenes.filter((scene) => scene.linkedWorldItemIds.includes(activeItem.id)).map((scene) => ({ id: scene.id, label: scene.title, onClick: () => navigate(`/writing/scenes?scene=${scene.id}`) }))} />
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-text-3"><Globe size={120} className="opacity-10" /></div>
        )}
      </main>
    </div>
  );
};

const Field = ({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) => (
  <label className="block">
    <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <input value={value} onChange={(event) => onChange(event.target.value)} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
  </label>
);

const LinkPanel = ({ title, items }: { title: string; items: { id: string; label: string; onClick: () => void }[] }) => (
  <div className="rounded-3xl border border-border bg-card p-6">
    <div className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{title}</div>
    <div className="space-y-3">
      {items.map((item) => (
        <button key={item.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={item.onClick}>
          <span className="text-sm font-bold text-text">{item.label}</span>
          <ExternalLink size={14} />
        </button>
      ))}
    </div>
  </div>
);
