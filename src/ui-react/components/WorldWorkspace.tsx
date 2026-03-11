import React, { useState, useEffect } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { 
    Globe, Box, Plus, Search, ChevronRight, 
    MoreVertical, Trash2, Save, Database, 
    Layers, Map as MapIcon, Book, Layout, Info
} from 'lucide-react';

export const WorldWorkspace = () => {
  const { 
      worldContainers, worldItems, selectedEntity, setSelectedEntity,
      addWorldContainer, updateWorldContainer, deleteWorldContainer,
      addWorldItem, updateWorldItem, deleteWorldItem
  } = useProjectStore();
  const { setLastActionStatus, sidebarSection } = useUIStore();
  
  const [activeContainerId, setActiveContainerId] = useState<string | null>(worldContainers[0]?.id || null);
  const activeContainer = worldContainers.find(c => c.id === activeContainerId);
  const containerItems = worldItems.filter(i => i.containerId === activeContainerId);

  const [editItem, setEditItem] = useState<any>(null);

  useEffect(() => {
    if (selectedEntity.type === 'world_item' && selectedEntity.id) {
        if (selectedEntity.id === 'new') {
            setEditItem({ 
                id: 'item_' + Date.now(), 
                containerId: activeContainerId, 
                name: '', 
                description: '', 
                attributes: [] 
            });
        } else {
            const item = worldItems.find(i => i.id === selectedEntity.id);
            if (item) setEditItem({ ...item });
        }
    } else {
        setEditItem(null);
    }
  }, [selectedEntity, worldItems, activeContainerId]);

  const handleSaveItem = () => {
    if (!editItem) return;
    if (!editItem.name) {
        alert("Name is required");
        return;
    }
    if (worldItems.find(i => i.id === editItem.id)) {
        updateWorldItem(editItem);
    } else {
        addWorldItem(editItem);
        setSelectedEntity('world_item', editItem.id);
    }
    setLastActionStatus('Saved');
  };

  const addAttribute = () => {
      setEditItem({
          ...editItem,
          attributes: [...(editItem.attributes || []), { key: '', value: '' }]
      });
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      {/* Left: Container List */}
      <div className="w-64 border-r border-border flex flex-col bg-bg-elev-1" data-testid="world-container-list">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-2">
            <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Containers</h3>
            <button 
                data-testid="create-container-btn"
                className="p-1 hover:bg-hover rounded-lg text-brand transition-colors"
                onClick={() => {
                    const id = 'cont_' + Date.now();
                    addWorldContainer({ id, name: 'New Container', type: 'notebook' });
                    setActiveContainerId(id);
                }}
            >
                <Plus size={16} />
            </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
            {worldContainers.map(cont => (
                <div 
                    key={cont.id}
                    data-testid={`world-container-${cont.id}`}
                    className={`px-3 py-2.5 rounded-xl cursor-pointer flex items-center gap-3 transition-all group ${
                        activeContainerId === cont.id ? 'bg-active text-text' : 'text-text-3 hover:bg-hover'
                    }`}
                    onClick={() => setActiveContainerId(cont.id)}
                >
                    <div className={activeContainerId === cont.id ? 'text-brand' : 'text-text-3 opacity-40'}>
                        {cont.type === 'notebook' && <Book size={14} />}
                        {cont.type === 'map' && <MapIcon size={14} />}
                        {cont.type === 'graph' && <Database size={14} />}
                        {cont.type === 'timeline' && <Layers size={14} />}
                    </div>
                    <span className="text-[11px] font-bold uppercase tracking-wider truncate">{cont.name}</span>
                </div>
            ))}
        </div>
      </div>

      {/* Center: Items List */}
      <div className="w-80 border-r border-border flex flex-col bg-bg shadow-xl z-10" data-testid="world-item-list">
        <div className="p-4 border-b border-border flex items-center justify-between bg-bg-elev-1">
            <div className="flex flex-col">
                <span className="text-[9px] font-black uppercase tracking-[0.3em] text-brand">{activeContainer?.type}</span>
                <h3 className="text-sm font-black text-text truncate">{activeContainer?.name}</h3>
            </div>
            <button 
                data-testid="add-world-item-btn"
                className="p-2 bg-brand/10 hover:bg-brand/20 text-brand rounded-xl transition-all active:scale-95"
                onClick={() => setSelectedEntity('world_item', 'new_' + Date.now())}
            >
                <Plus size={18} />
            </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
            {containerItems.map(item => (
                <div 
                    key={item.id}
                    data-testid={`world-item-${item.id}`}
                    className={`p-4 border-b border-divider cursor-pointer transition-all group relative ${
                        selectedEntity.id === item.id ? 'bg-selected' : 'hover:bg-hover'
                    }`}
                    onClick={() => setSelectedEntity('world_item', item.id)}
                >
                    {selectedEntity.id === item.id && (
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-brand"></div>
                    )}
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

      {/* Right: Item Editor */}
      <div className="flex-1 flex flex-col bg-bg-elev-1 overflow-y-auto custom-scrollbar">
        {editItem ? (
            <div className="max-w-3xl mx-auto p-12 w-full">
                <div className="flex items-center gap-3 mb-12 opacity-40">
                    <Box size={14} className="text-brand" />
                    <span className="text-[10px] font-black uppercase tracking-[0.4em]">Entity Definition</span>
                </div>

                <div className="space-y-10">
                    <div className="group">
                        <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.3em] mb-4 group-focus-within:text-brand transition-colors">Item Identity</label>
                        <input 
                            data-testid="world-item-name-input"
                            className="bg-transparent text-5xl font-black text-text outline-none placeholder:text-text-3/10 w-full tracking-tight focus:text-brand transition-colors opacity-100 block"
                            placeholder="Object or Concept Name"
                            value={editItem.name}
                            onChange={e => setEditItem({...editItem, name: e.target.value})}
                        />
                    </div>

                    <div className="group">
                        <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.3em] mb-4 group-focus-within:text-brand transition-colors">Physical/Conceptual Description</label>
                        <textarea 
                            data-testid="world-item-description-input"
                            className="w-full h-40 bg-bg border border-border rounded-2xl p-5 text-sm text-text-2 focus:border-brand focus:ring-1 focus:ring-brand/30 outline-none transition-all font-serif leading-relaxed shadow-inner"
                            placeholder="Describe how this item exists in the world..."
                            value={editItem.description}
                            onChange={e => setEditItem({...editItem, description: e.target.value})}
                        />
                    </div>

                    <div className="space-y-6">
                        <div className="flex items-center justify-between">
                            <label className="block text-[10px] font-black text-text-3 uppercase tracking-[0.3em]">Extended Attributes</label>
                            <button 
                                data-testid="dynamic-field-add-row"
                                className="px-3 py-1 bg-bg border border-border hover:border-brand rounded-lg text-[9px] font-black uppercase tracking-widest text-text-3 hover:text-brand transition-all"
                                onClick={addAttribute}
                            >
                                <Plus size={10} className="inline mr-1" /> Add Row
                            </button>
                        </div>
                        
                        <div className="space-y-3">
                            {editItem.attributes?.map((attr: any, idx: number) => (
                                <div key={idx} className="flex gap-3 animate-in fade-in slide-in-from-left-2 duration-200">
                                    <input 
                                        data-testid="dynamic-field-key-input"
                                        className="flex-1 bg-bg border border-border rounded-xl px-4 py-2.5 text-[11px] font-bold text-text-2 outline-none focus:border-brand transition-all"
                                        placeholder="Attribute"
                                        value={attr.key}
                                        onChange={e => {
                                            const attrs = [...editItem.attributes];
                                            attrs[idx].key = e.target.value;
                                            setEditItem({...editItem, attributes: attrs});
                                        }}
                                    />
                                    <input 
                                        data-testid="dynamic-field-value-input"
                                        className="flex-[2] bg-bg border border-border rounded-xl px-4 py-2.5 text-[11px] text-text-2 outline-none focus:border-brand transition-all"
                                        placeholder="Value"
                                        value={attr.value}
                                        onChange={e => {
                                            const attrs = [...editItem.attributes];
                                            attrs[idx].value = e.target.value;
                                            setEditItem({...editItem, attributes: attrs});
                                        }}
                                    />
                                    <button 
                                        className="p-2.5 text-text-3 hover:text-red transition-colors"
                                        onClick={() => {
                                            const attrs = editItem.attributes.filter((_: any, i: number) => i !== idx);
                                            setEditItem({...editItem, attributes: attrs});
                                        }}
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            ))}
                            {(!editItem.attributes || editItem.attributes.length === 0) && (
                                <div className="py-10 border border-dashed border-divider rounded-2xl flex flex-col items-center justify-center opacity-30">
                                    <Database size={24} className="mb-2" />
                                    <p className="text-[9px] font-black uppercase tracking-widest">No custom properties</p>
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="pt-16 flex justify-end gap-4 border-t border-divider">
                        <button 
                            data-testid="inspector-save"
                            className="px-10 py-3 bg-brand hover:bg-brand-2 text-white font-black rounded-xl text-[11px] uppercase tracking-widest shadow-2 active:scale-95 transition-all flex items-center gap-2.5 ring-1 ring-white/10"
                            onClick={handleSaveItem}
                        >
                            <Save size={16} /> Persist Entity
                        </button>
                    </div>
                </div>
            </div>
        ) : (
            <div className="h-full flex flex-col items-center justify-center text-text-3 select-none">
                <div className="relative mb-8">
                    <Globe size={140} className="opacity-5" />
                    <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-32 h-32 rounded-full border border-brand/10 animate-pulse opacity-20"></div>
                    </div>
                </div>
                <p className="text-[11px] font-black uppercase tracking-[0.5em] opacity-40 text-center">World Model Inspector<br/><span className="text-[9px] font-medium tracking-widest opacity-50 mt-4 block">Select an entity to review its properties</span></p>
            </div>
        )}
      </div>
    </div>
  );
};
