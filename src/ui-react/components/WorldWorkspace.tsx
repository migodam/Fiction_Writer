import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ExternalLink, Globe, Map as MapIcon, Plus, Trash2 } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { useI18n } from '../i18n';

export const WorldWorkspace = () => {
  const navigate = useNavigate();
  const { sidebarSection, openContextMenu, setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const {
    worldContainers,
    worldItems,
    worldSettings,
    worldMaps,
    timelineEvents,
    scenes,
    addWorldContainer,
    addWorldItem,
    updateWorldItem,
    deleteWorldItem,
    updateWorldSettings,
    createWorldMap,
    updateWorldMap,
    updateWorldContainer,
    deleteWorldContainer,
  } = useProjectStore();
  const [activeContainerId, setActiveContainerId] = useState(worldContainers[0]?.id || null);
  const [activeItemId, setActiveItemId] = useState(worldItems[0]?.id || null);
  const [activeMapId, setActiveMapId] = useState(worldMaps[0]?.id || null);
  const [renamingContainerId, setRenamingContainerId] = useState<string | null>(null);

  const activeContainer = worldContainers.find((container) => container.id === activeContainerId) || worldContainers[0] || null;
  const activeItem = worldItems.find((item) => item.id === activeItemId) || null;
  const activeMap = worldMaps.find((map) => map.id === activeMapId) || worldMaps[0] || null;
  const containerItems = useMemo(() => worldItems.filter((item) => item.containerId === activeContainer?.id), [worldItems, activeContainer]);
  const activeMapMarkers = useMemo(() => {
    if (!activeMap) return [];
    return worldItems.flatMap((item) => item.mapMarkers).filter((marker) => activeMap.markerIds.includes(marker.id));
  }, [activeMap, worldItems]);

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
            <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => addWorldContainer({ id: `cont_${Date.now()}`, name: t('world.newContainer', 'New Container'), type: 'notebook', sortOrder: worldContainers.length, isCollapsed: false })}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {worldContainers.map((container) => (
            <button
              key={container.id}
              type="button"
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
            <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={() => {
              if (!activeContainer) return;
              const itemId = `item_${Date.now()}`;
              addWorldItem({ id: itemId, containerId: activeContainer.id, type: activeContainer.id.includes('location') ? 'location' : 'note', name: t('world.newEntry', 'New Entry'), description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], assetPath: null, tagIds: [] });
              setActiveItemId(itemId);
            }}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar">
          {containerItems.map((item) => (
            <button key={item.id} type="button" className={cn('w-full border-b border-divider px-4 py-4 text-left transition-colors', activeItemId === item.id ? 'bg-selected' : 'hover:bg-hover')} onClick={() => setActiveItemId(item.id)} onContextMenu={(e) => { e.preventDefault(); openContextMenu({ x: e.clientX, y: e.clientY, items: [{ id: 'delete', label: t('common.delete'), action: () => { deleteWorldItem(item.id); if (activeItemId === item.id) setActiveItemId(null); setLastActionStatus(t('world.itemDeleted', 'World item deleted')); }, destructive: true }] }); }}>
              <div className="text-sm font-black text-text">{item.name}</div>
              <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-text-3">{item.description}</div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
        {activeItem ? (
          <div className="mx-auto max-w-5xl space-y-8">
            <div>
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.entryName', 'Entry Name')}</div>
              <input value={activeItem.name} onChange={(event) => updateWorldItem({ ...activeItem, name: event.target.value })} className="w-full bg-transparent text-5xl font-black tracking-tight outline-none" />
            </div>
            <div>
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.descriptionLabel', 'Description')}</div>
              <textarea value={activeItem.description} onChange={(event) => updateWorldItem({ ...activeItem, description: event.target.value })} className="h-40 w-full rounded-3xl border border-border bg-bg p-5 font-serif text-sm leading-relaxed text-text-2 outline-none" />
            </div>
            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.attributes', 'Attributes')}</div>
                <button type="button" className="rounded-xl border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-2 hover:border-brand" onClick={() => updateWorldItem({ ...activeItem, attributes: [...activeItem.attributes, { key: '', value: '' }] })}>
                  {t('world.addRow', 'Add Row')}
                </button>
              </div>
              <div className="space-y-3">
                {activeItem.attributes.map((attribute, index) => (
                  <div key={`${attribute.key}-${index}`} className="flex gap-3">
                    <input value={attribute.key} onChange={(event) => updateWorldItem({ ...activeItem, attributes: activeItem.attributes.map((entry, entryIndex) => entryIndex === index ? { ...entry, key: event.target.value } : entry) })} className="flex-1 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('world.attribute', 'Attribute')} />
                    <input value={attribute.value} onChange={(event) => updateWorldItem({ ...activeItem, attributes: activeItem.attributes.map((entry, entryIndex) => entryIndex === index ? { ...entry, value: event.target.value } : entry) })} className="flex-[1.4] rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('world.value', 'Value')} />
                    <button type="button" className="rounded-2xl border border-red/40 px-3 text-red" onClick={() => updateWorldItem({ ...activeItem, attributes: activeItem.attributes.filter((_, entryIndex) => entryIndex !== index) })}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
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
