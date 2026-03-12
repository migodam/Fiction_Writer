import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Book, ChevronDown, ChevronRight, ExternalLink, Globe, Layers, Map as MapIcon, Pencil, Plus, Trash2 } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

export const WorldWorkspace = () => {
  const {
    worldContainers,
    worldItems,
    timelineEvents,
    scenes,
    selectedEntity,
    setSelectedEntity,
    addWorldContainer,
    updateWorldContainer,
    addWorldItem,
    updateWorldItem,
  } = useProjectStore();
  const { setLastActionStatus, sidebarSection, openContextMenu } = useUIStore();
  const navigate = useNavigate();
  const { t } = useI18n();

  const [activeContainerId, setActiveContainerId] = useState<string | null>(worldContainers[0]?.id || null);
  const [editItem, setEditItem] = useState<typeof worldItems[number] | null>(null);
  const [renamingContainerId, setRenamingContainerId] = useState<string | null>(null);

  useEffect(() => {
    const preferred = sidebarSection === 'maps' ? 'cont_world_map' : sidebarSection === 'organizations' ? 'cont_orgs' : sidebarSection === 'lore' ? 'cont_lore' : 'cont_locations';
    if (worldContainers.some((entry) => entry.id === preferred)) setActiveContainerId(preferred);
  }, [sidebarSection, worldContainers]);

  const activeContainer = worldContainers.find((container) => container.id === activeContainerId) || null;
  const containerItems = useMemo(() => worldItems.filter((item) => item.containerId === activeContainerId), [worldItems, activeContainerId]);
  const mapItem = worldItems.find((item) => item.containerId === 'cont_world_map');

  useEffect(() => {
    if (selectedEntity.type !== 'world_item' || !selectedEntity.id) return setEditItem(null);
    if (selectedEntity.id.startsWith('new_')) {
      setEditItem({
        id: `item_${Date.now()}`,
        containerId: activeContainerId || 'cont_locations',
        type: activeContainerId === 'cont_locations' ? 'location' : activeContainer?.type || 'note',
        name: '',
        description: '',
        attributes: [],
        linkedCharacterIds: [],
        linkedEventIds: [],
        linkedSceneIds: [],
        mapMarkers: [],
        assetPath: null,
        tagIds: [],
      });
      return;
    }
    const item = worldItems.find((entry) => entry.id === selectedEntity.id);
    if (item) setEditItem({ ...item });
  }, [activeContainer, activeContainerId, selectedEntity, worldItems]);

  const openLocationTimeline = (locationId: string) => navigate(`/timeline/events?location=${locationId}`);

  const reverseReferences = useMemo(() => {
    if (!editItem) return { scenes: [], events: [] };
    return {
      scenes: scenes.filter((scene) => scene.linkedWorldItemIds.includes(editItem.id)),
      events: timelineEvents.filter((event) => event.linkedWorldItemIds.includes(editItem.id) || event.locationIds.includes(editItem.id)),
    };
  }, [editItem, scenes, timelineEvents]);

  const sortedContainers = worldContainers.slice().sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-72 border-r border-border bg-bg-elev-1" data-testid="world-container-list">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('world.containers')}</div>
              <div className="text-sm font-black text-text">World Structure</div>
            </div>
            <button type="button" data-testid="create-container-btn" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => {
              const id = `cont_${Date.now()}`;
              addWorldContainer({ id, name: 'New Container', type: 'notebook', sortOrder: sortedContainers.length, isCollapsed: false });
              setActiveContainerId(id);
              setRenamingContainerId(id);
            }}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {sortedContainers.map((container) => (
            <div
              key={container.id}
              data-testid={`world-container-${container.id}`}
              className={cn('mb-2 rounded-2xl border transition-colors', activeContainerId === container.id ? 'border-brand bg-active' : 'border-transparent hover:bg-hover')}
              onContextMenu={(event) => {
                event.preventDefault();
                openContextMenu({
                  x: event.clientX,
                  y: event.clientY,
                  items: [
                    { id: 'rename-container', label: 'Rename Container', action: () => setRenamingContainerId(container.id) },
                    { id: 'toggle-collapse', label: container.isCollapsed ? 'Expand Container' : 'Collapse Container', action: () => updateWorldContainer({ ...container, isCollapsed: !container.isCollapsed }) },
                  ],
                });
              }}
            >
              <div className="flex items-center gap-2 px-3 py-3">
                <button type="button" className="rounded p-1 text-text-3 hover:text-text" onClick={() => updateWorldContainer({ ...container, isCollapsed: !container.isCollapsed })}>
                  {container.isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                </button>
                <button type="button" className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => setActiveContainerId(container.id)}>
                  {container.type === 'map' ? <MapIcon size={14} className="text-brand-2" /> : container.type === 'graph' ? <Layers size={14} className="text-brand-2" /> : <Book size={14} className="text-brand-2" />}
                  {renamingContainerId === container.id ? (
                    <>
                      <span className="sr-only">{container.name}</span>
                      <input autoFocus value={container.name} onChange={(event) => updateWorldContainer({ ...container, name: event.target.value })} onBlur={() => setRenamingContainerId(null)} className="min-w-0 flex-1 bg-transparent text-sm font-bold text-text outline-none" />
                    </>
                  ) : (
                    <span className="truncate text-sm font-bold text-text">{container.name}</span>
                  )}
                </button>
                <button type="button" className="rounded p-1 text-text-3 hover:text-text" onClick={() => setRenamingContainerId(container.id)}>
                  <Pencil size={12} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <aside className="w-80 border-r border-border bg-bg shadow-xl" data-testid="world-item-list">
        <div className="border-b border-border bg-bg-elev-1 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{activeContainer?.type}</div>
              <div className="text-sm font-black text-text">{activeContainer?.name}</div>
            </div>
            {activeContainerId !== 'cont_world_map' && (
              <button type="button" data-testid="add-world-item-btn" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => setSelectedEntity('world_item', `new_${Date.now()}`)}>
                <Plus size={16} />
              </button>
            )}
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar">
          {containerItems.map((item) => (
            <button
              type="button"
              key={item.id}
              data-testid={`world-item-${item.id}`}
              className={cn('w-full border-b border-divider px-4 py-4 text-left transition-colors', selectedEntity.id === item.id ? 'bg-selected' : 'hover:bg-hover')}
              onClick={() => setSelectedEntity('world_item', item.id)}
              onContextMenu={(event) => {
                event.preventDefault();
                openContextMenu({
                  x: event.clientX,
                  y: event.clientY,
                  items: [
                    { id: 'rename-item', label: 'Rename Item', action: () => setSelectedEntity('world_item', item.id) },
                    ...(item.type === 'location' ? [{ id: 'location-timeline', label: 'Open Timeline', action: () => openLocationTimeline(item.id) }] : []),
                  ],
                });
              }}
            >
              <div className="flex items-center justify-between">
                <div className="pr-3">
                  <div className="text-sm font-black text-text">{item.name}</div>
                  <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-3">{item.description}</div>
                </div>
                <ChevronRight size={14} />
              </div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 overflow-hidden bg-bg-elev-1" data-testid="world-detail-panel">
        {activeContainerId === 'cont_world_map' ? (
          <div className="h-full overflow-y-auto custom-scrollbar p-10">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.mapTitle')}</div>
            <div className="rounded-3xl border border-border bg-card p-4 shadow-1">
              {mapItem && (
                <div className="relative overflow-hidden rounded-2xl border border-border bg-bg">
                  <img src={mapItem.assetPath || ''} alt="World Map" className="h-[560px] w-full object-cover" data-testid="world-map-image" />
                  {mapItem.mapMarkers.map((marker) => (
                    <button key={marker.id} type="button" className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/20 bg-brand px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-white shadow-2" style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }} onClick={() => marker.linkedEntityId && openLocationTimeline(marker.linkedEntityId)} data-testid="world-map-marker">
                      {marker.label}
                    </button>
                  ))}
                </div>
              )}
              <div className="mt-4 text-sm text-text-2">{t('world.mapLegend')}</div>
            </div>
          </div>
        ) : editItem ? (
          <div className="h-full overflow-y-auto custom-scrollbar p-10">
            <div className="mx-auto max-w-4xl space-y-8">
              <div>
                <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.itemIdentity')}</div>
                <input data-testid="world-item-name-input" value={editItem.name} onChange={(event) => setEditItem({ ...editItem, name: event.target.value })} className="w-full bg-transparent text-5xl font-black tracking-tight outline-none" placeholder="Object or Concept Name" />
              </div>
              <div>
                <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.description')}</div>
                <textarea data-testid="world-item-description-input" value={editItem.description} onChange={(event) => setEditItem({ ...editItem, description: event.target.value })} className="h-40 w-full rounded-3xl border border-border bg-bg p-5 font-serif text-sm leading-relaxed text-text-2 outline-none" />
              </div>
              <div className="rounded-3xl border border-border bg-card p-6">
                <div className="mb-4 flex items-center justify-between">
                  <div className="text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.attributes')}</div>
                  <button type="button" data-testid="dynamic-field-add-row" className="rounded-xl border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-2 hover:border-brand" onClick={() => setEditItem({ ...editItem, attributes: [...editItem.attributes, { key: '', value: '' }] })}>
                    {t('world.addRow')}
                  </button>
                </div>
                <div className="space-y-3">
                  {editItem.attributes.map((attribute, index) => (
                    <div key={`${attribute.key}-${index}`} className="flex gap-3">
                      <input data-testid="dynamic-field-key-input" value={attribute.key} onChange={(event) => {
                        const next = [...editItem.attributes];
                        next[index] = { ...next[index], key: event.target.value };
                        setEditItem({ ...editItem, attributes: next });
                      }} className="flex-1 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder="Attribute" />
                      <input data-testid="dynamic-field-value-input" value={attribute.value} onChange={(event) => {
                        const next = [...editItem.attributes];
                        next[index] = { ...next[index], value: event.target.value };
                        setEditItem({ ...editItem, attributes: next });
                      }} className="flex-[1.4] rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder="Value" />
                      <button type="button" className="rounded-2xl border border-red/40 px-3 text-red" onClick={() => setEditItem({ ...editItem, attributes: editItem.attributes.filter((_, attrIndex) => attrIndex !== index) })}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-3xl border border-border bg-card p-6">
                  <div className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">Linked Timeline</div>
                  <div className="space-y-3">
                    {reverseReferences.events.map((event) => (
                      <button key={event.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={() => navigate(`/timeline/events?event=${event.id}`)}>
                        <span className="text-sm font-bold text-text">{event.title}</span>
                        <ExternalLink size={14} />
                      </button>
                    ))}
                  </div>
                </div>
                <div className="rounded-3xl border border-border bg-card p-6">
                  <div className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">Linked Scenes</div>
                  <div className="space-y-3">
                    {reverseReferences.scenes.map((scene) => (
                      <button key={scene.id} type="button" className="flex w-full items-center justify-between rounded-2xl border border-border bg-bg px-4 py-3 text-left hover:border-brand" onClick={() => navigate(`/writing/scenes?scene=${scene.id}`)}>
                        <span className="text-sm font-bold text-text">{scene.title}</span>
                        <ExternalLink size={14} />
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex justify-between gap-4 border-t border-divider pt-8">
                {editItem.type === 'location' ? (
                  <button type="button" data-testid="open-world-timeline-btn" className="rounded-xl border border-border px-5 py-3 text-sm text-text-2 hover:border-brand" onClick={() => openLocationTimeline(editItem.id)}>
                    <ExternalLink size={14} className="mr-2 inline" />{t('world.openTimeline')}
                  </button>
                ) : <div />}
                <button type="button" data-testid="inspector-save" className="rounded-xl bg-brand px-8 py-3 text-sm font-black text-white" onClick={() => {
                  if (!editItem.name.trim()) return;
                  if (worldItems.some((item) => item.id === editItem.id)) updateWorldItem(editItem);
                  else addWorldItem(editItem);
                  setSelectedEntity('world_item', editItem.id);
                  setLastActionStatus(t('shell.saved'));
                }}>
                  Save Item
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-text-3"><Globe size={120} className="opacity-10" /></div>
        )}
      </main>
    </div>
  );
};
