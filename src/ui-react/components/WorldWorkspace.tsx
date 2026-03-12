import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import { Globe, Box, Plus, ChevronRight, Trash2, Save, Database, Layers, Map as MapIcon, Book, ExternalLink } from 'lucide-react';
import { useI18n } from '../i18n';

export const WorldWorkspace = () => {
  const {
    worldContainers,
    worldItems,
    selectedEntity,
    setSelectedEntity,
    addWorldContainer,
    addWorldItem,
    updateWorldItem,
  } = useProjectStore();
  const { setLastActionStatus, sidebarSection } = useUIStore();
  const navigate = useNavigate();
  const { t } = useI18n();

  const [activeContainerId, setActiveContainerId] = useState<string | null>(worldContainers[0]?.id || null);
  const [editItem, setEditItem] = useState<any>(null);

  useEffect(() => {
    const preferred = sidebarSection === 'maps'
      ? 'cont_world_map'
      : sidebarSection === 'organizations'
      ? 'cont_orgs'
      : sidebarSection === 'lore'
      ? 'cont_lore'
      : 'cont_locations';
    if (worldContainers.some((entry) => entry.id === preferred)) {
      setActiveContainerId(preferred);
    }
  }, [sidebarSection, worldContainers]);

  const activeContainer = worldContainers.find((container) => container.id === activeContainerId) || null;
  const containerItems = useMemo(() => worldItems.filter((item) => item.containerId === activeContainerId), [worldItems, activeContainerId]);
  const mapItem = worldItems.find((item) => item.containerId === 'cont_world_map');

  useEffect(() => {
    if (selectedEntity.type === 'world_item' && selectedEntity.id) {
      if (selectedEntity.id === 'new' || selectedEntity.id.startsWith('new_')) {
        setEditItem({
          id: `item_${Date.now()}`,
          containerId: activeContainerId,
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
      } else {
        const item = worldItems.find((entry) => entry.id === selectedEntity.id);
        if (item) {
          setEditItem({ ...item });
        }
      }
    } else {
      setEditItem(null);
    }
  }, [selectedEntity, worldItems, activeContainerId, activeContainer]);

  const handleSaveItem = () => {
    if (!editItem?.name) {
      return;
    }
    if (worldItems.some((entry) => entry.id === editItem.id)) {
      updateWorldItem(editItem);
    } else {
      addWorldItem(editItem);
      setSelectedEntity('world_item', editItem.id);
    }
    setLastActionStatus(t('shell.saved'));
  };

  const addAttribute = () => {
    setEditItem({ ...editItem, attributes: [...(editItem.attributes || []), { key: '', value: '' }] });
  };

  const openLocationTimeline = (locationId: string) => {
    navigate(`/timeline/events?location=${locationId}`);
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <div className="w-64 border-r border-border flex flex-col bg-bg-elev-1" data-testid="world-container-list">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
          <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('world.containers')}</h3>
          <button
            data-testid="create-container-btn"
            className="p-1 hover:bg-hover rounded-lg text-brand transition-colors"
            onClick={() => {
              const id = `cont_${Date.now()}`;
              addWorldContainer({ id, name: 'New Container', type: 'notebook' });
              setActiveContainerId(id);
            }}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
          {worldContainers.map((container) => (
            <div
              key={container.id}
              data-testid={`world-container-${container.id}`}
              className={`px-3 py-2.5 rounded-xl cursor-pointer flex items-center gap-3 transition-all group ${activeContainerId === container.id ? 'bg-active text-text' : 'text-text-3 hover:bg-hover'}`}
              onClick={() => setActiveContainerId(container.id)}
            >
              <div className={activeContainerId === container.id ? 'text-brand' : 'text-text-3 opacity-40'}>
                {container.type === 'notebook' && <Book size={14} />}
                {container.type === 'map' && <MapIcon size={14} />}
                {container.type === 'graph' && <Database size={14} />}
                {container.type === 'timeline' && <Layers size={14} />}
              </div>
              <span className="text-[11px] font-bold uppercase tracking-wider truncate">{container.name}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="w-80 border-r border-border flex flex-col bg-bg shadow-xl z-10" data-testid="world-item-list">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-1">
          <div className="flex flex-col">
            <span className="text-[9px] font-black uppercase tracking-[0.3em] text-brand">{activeContainer?.type}</span>
            <h3 className="text-sm font-black text-text truncate">{activeContainer?.name}</h3>
          </div>
          {activeContainerId !== 'cont_world_map' && (
            <button
              data-testid="add-world-item-btn"
              className="p-2 bg-brand/10 hover:bg-brand/20 text-brand rounded-xl transition-all active:scale-95"
              onClick={() => setSelectedEntity('world_item', `new_${Date.now()}`)}
            >
              <Plus size={18} />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {containerItems.map((item) => (
            <div
              key={item.id}
              data-testid={`world-item-${item.id}`}
              className={`p-4 border-b border-divider cursor-pointer transition-all group relative ${selectedEntity.id === item.id ? 'bg-selected' : 'hover:bg-hover'}`}
              onClick={() => setSelectedEntity('world_item', item.id)}
            >
              {selectedEntity.id === item.id && <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand"></div>}
              <div className="flex items-center justify-between mb-1">
                <div className="font-bold text-sm text-text truncate pr-4 group-hover:text-brand transition-colors">{item.name}</div>
                <ChevronRight size={14} className={`transition-opacity text-text-3 ${selectedEntity.id === item.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`} />
              </div>
              <div className="text-[11px] text-text-3 line-clamp-2 leading-relaxed">{item.description}</div>
            </div>
          ))}
          {containerItems.length === 0 && (
            <div className="p-12 text-center opacity-20">
              <Box size={40} className="mx-auto mb-4" />
              <p className="text-[10px] font-black uppercase tracking-widest">Container Empty</p>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-bg-elev-1 overflow-y-auto custom-scrollbar" data-testid="world-detail-panel">
        {activeContainerId === 'cont_world_map' ? (
          <div className="p-10">
            <div className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-text-3">{t('world.mapTitle')}</div>
            <div className="rounded-3xl border border-border bg-card p-4 shadow-1">
              {mapItem && (
                <div className="relative overflow-hidden rounded-2xl border border-border bg-bg">
                  <img src={mapItem.assetPath || ''} alt="World Map" className="w-full h-[520px] object-cover" data-testid="world-map-image" />
                  {mapItem.mapMarkers.map((marker) => (
                    <button
                      type="button"
                      key={marker.id}
                      className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/20 bg-brand px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-white shadow-2"
                      style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}
                      onClick={() => marker.linkedEntityId && openLocationTimeline(marker.linkedEntityId)}
                      data-testid="world-map-marker"
                    >
                      {marker.label}
                    </button>
                  ))}
                </div>
              )}
              <div className="mt-4 text-sm text-text-2">{t('world.mapLegend')}</div>
            </div>
          </div>
        ) : editItem ? (
          <div className="max-w-3xl mx-auto p-12 w-full">
            <div className="space-y-10">
              <div className="group">
                <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.3em] mb-4">{t('world.itemIdentity')}</label>
                <input data-testid="world-item-name-input" className="bg-transparent text-5xl font-black text-text outline-none placeholder:text-text-3/10 w-full tracking-tight focus:text-brand transition-colors" placeholder="Object or Concept Name" value={editItem.name} onChange={(event) => setEditItem({ ...editItem, name: event.target.value })} />
              </div>
              <div className="group">
                <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.3em] mb-4">{t('world.description')}</label>
                <textarea data-testid="world-item-description-input" className="w-full h-40 bg-bg border border-border rounded-2xl p-5 text-sm text-text-2 focus:border-brand outline-none transition-all font-serif leading-relaxed shadow-inner" placeholder="Describe how this item exists in the world..." value={editItem.description} onChange={(event) => setEditItem({ ...editItem, description: event.target.value })} />
              </div>
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.3em]">{t('world.attributes')}</label>
                  <button data-testid="dynamic-field-add-row" className="px-3 py-1 bg-bg border border-border hover:border-brand rounded-lg text-[9px] font-black uppercase tracking-widest text-text-3 hover:text-brand transition-all" onClick={addAttribute}>{t('world.addRow')}</button>
                </div>
                <div className="space-y-3">
                  {editItem.attributes?.map((attr: any, idx: number) => (
                    <div key={idx} className="flex gap-3">
                      <input data-testid="dynamic-field-key-input" className="flex-1 bg-bg border border-border rounded-xl px-4 py-2.5 text-[11px] font-bold text-text-2 outline-none focus:border-brand transition-all" placeholder="Attribute" value={attr.key} onChange={(event) => {
                        const attrs = [...editItem.attributes];
                        attrs[idx].key = event.target.value;
                        setEditItem({ ...editItem, attributes: attrs });
                      }} />
                      <input data-testid="dynamic-field-value-input" className="flex-[2] bg-bg border border-border rounded-xl px-4 py-2.5 text-[11px] text-text-2 outline-none focus:border-brand transition-all" placeholder="Value" value={attr.value} onChange={(event) => {
                        const attrs = [...editItem.attributes];
                        attrs[idx].value = event.target.value;
                        setEditItem({ ...editItem, attributes: attrs });
                      }} />
                      <button className="p-2.5 text-text-3 hover:text-red transition-colors" onClick={() => {
                        const attrs = editItem.attributes.filter((_: any, index: number) => index !== idx);
                        setEditItem({ ...editItem, attributes: attrs });
                      }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="pt-8 flex justify-between gap-4 border-t border-divider">
                {editItem.type === 'location' && (
                  <button type="button" className="px-5 py-3 border border-border hover:border-brand rounded-xl text-[11px] font-black uppercase tracking-widest text-text-2" onClick={() => openLocationTimeline(editItem.id)} data-testid="open-world-timeline-btn">
                    <ExternalLink size={14} className="inline mr-2" /> {t('world.openTimeline')}
                  </button>
                )}
                <button data-testid="inspector-save" className="ml-auto px-10 py-3 bg-brand hover:bg-brand-2 text-white font-black rounded-xl text-[11px] uppercase tracking-widest shadow-2" onClick={handleSaveItem}>{t('world.persist')}</button>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-3 select-none">
            <Globe size={140} className="opacity-5 mb-8" />
            <p className="text-[11px] font-black uppercase tracking-[0.5em] opacity-40 text-center">World Model</p>
          </div>
        )}
      </div>
    </div>
  );
};
