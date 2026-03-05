import React, { useEffect, useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { Plus, Check, X, User, Link as LinkIcon, Clock, Trash2, ChevronRight } from 'lucide-react';

export const CharactersWorkspace = () => {
  const { 
    characters, candidates, selectedEntity, setSelectedEntity, 
    addCharacter, updateCharacter, confirmCandidate, rejectCandidate,
    relationships, addRelationship, deleteRelationship,
    timelineEvents
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  
  const [activeTab, setActiveTab] = useState<'profile' | 'relationships' | 'timeline'>('profile');
  const [editChar, setEditChar] = useState<any>(null);

  // Sync edit state with selection
  useEffect(() => {
    if (selectedEntity.type === 'character' && selectedEntity.id) {
      if (selectedEntity.id === 'new') {
        setEditChar({ id: 'char_' + Date.now(), name: '', background: '' });
      } else {
        const char = characters.find(c => c.id === selectedEntity.id);
        if (char) setEditChar({ ...char });
      }
    } else {
      setEditChar(null);
    }
  }, [selectedEntity, characters]);

  const handleSave = () => {
    if (!editChar) return;
    if (!editChar.name || !editChar.background) {
        alert("Name and Background are required.");
        return;
    }

    if (characters.find(c => c.id === editChar.id)) {
      updateCharacter(editChar);
    } else {
      addCharacter(editChar);
      setSelectedEntity('character', editChar.id);
    }
    setLastActionStatus('Saved');
  };

  const charRelationships = relationships.filter(r => r.sourceId === selectedEntity.id || r.targetId === selectedEntity.id);
  const charEvents = timelineEvents.filter(e => e.participants?.includes(selectedEntity.id!));

  return (
    <div className="flex h-full overflow-hidden">
      {/* Character List Column */}
      <div className="w-64 border-r border-[#333333] flex flex-col bg-[#1e1e1e]" data-testid="character-list">
        <div className="p-4 border-b border-[#333333] flex items-center justify-between">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-[#888888]">Confirmed</h3>
          <button 
            data-testid="new-character-btn"
            className="p-1 hover:bg-[#333333] rounded text-[#007acc]"
            onClick={() => {
                setSelectedEntity('character', 'new');
                setActiveTab('profile');
            }}
          >
            <Plus size={14} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {characters.map(char => (
            <div 
              key={char.id}
              data-testid={`character-card-${char.id}`}
              className={`p-3 border-b border-[#333333] cursor-pointer hover:bg-[#252526] transition-colors group ${selectedEntity.id === char.id ? 'bg-[#252526] border-l-2 border-l-[#007acc]' : ''}`}
              onClick={() => setSelectedEntity('character', char.id)}
            >
              <div className="flex items-center justify-between">
                <div className="font-medium text-sm text-[#cccccc]">{char.name}</div>
                <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity text-[#444444]" />
              </div>
              <div className="text-[10px] text-[#666666] truncate mt-1">{char.background}</div>
            </div>
          ))}
          {characters.length === 0 && (
            <div className="p-8 text-center text-[#444444] text-xs uppercase font-bold tracking-tighter">Empty Roster</div>
          )}
        </div>

        {/* Candidates Section */}
        <div className="p-4 border-t border-[#333333] bg-[#252526]">
           <h3 className="text-[10px] font-bold uppercase tracking-widest text-[#888888] mb-4">Candidates</h3>
           {candidates.map(cand => (
             <div 
              key={cand.id} 
              data-testid={`candidate-card-${cand.id}`}
              className="p-3 mb-2 bg-[#1e1e1e] border border-[#333333] rounded group"
            >
               <div className="font-medium text-xs mb-2 text-[#999999]">{cand.name}</div>
               <div className="flex gap-1.5">
                 <button 
                  data-testid="candidate-confirm-btn"
                  className="flex-1 py-1 bg-[#2e7d32] hover:bg-[#388e3c] text-white rounded text-[9px] font-bold uppercase tracking-tighter flex items-center justify-center gap-1"
                  onClick={() => confirmCandidate(cand.id)}
                 >
                   Confirm
                 </button>
                 <button 
                  data-testid="candidate-reject-btn"
                  className="p-1 bg-[#333333] hover:bg-red-900 rounded text-white transition-colors"
                  onClick={() => rejectCandidate(cand.id)}
                 >
                   <X size={10} />
                 </button>
               </div>
             </div>
           ))}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col bg-[#121212]">
        {selectedEntity.id ? (
          <>
            {/* Sub-navigation Tabs */}
            <div className="h-10 border-b border-[#333333] flex items-center px-6 gap-8 bg-[#1e1e1e]">
                <TabButton active={activeTab === 'profile'} label="Profile" onClick={() => setActiveTab('profile')} testId="char-tab-profile" />
                <TabButton active={activeTab === 'relationships'} label="Relationships" onClick={() => setActiveTab('relationships')} testId="char-tab-relationships" />
                <TabButton active={activeTab === 'timeline'} label="Timeline" onClick={() => setActiveTab('timeline')} testId="char-tab-timeline" />
            </div>

            <div className="flex-1 overflow-y-auto">
                {activeTab === 'profile' && editChar && (
                    <div className="max-w-3xl mx-auto p-12">
                        <div className="flex items-center gap-6 mb-12">
                            <div className="w-20 h-20 bg-[#252526] rounded-xl flex items-center justify-center border border-[#333333] shadow-inner">
                                <User size={40} className="text-[#444444]" />
                            </div>
                            <div className="flex-1">
                                <input 
                                    data-testid="character-name-input"
                                    className="bg-transparent text-5xl font-bold text-white outline-none placeholder-[#222222] w-full tracking-tight"
                                    placeholder="Full Name"
                                    value={editChar.name}
                                    onChange={e => setEditChar({...editChar, name: e.target.value})}
                                />
                                <div className="flex items-center gap-2 mt-2">
                                    <span className="text-[#007acc] text-[10px] font-bold uppercase tracking-[0.2em]">Character Record</span>
                                    <div className="h-px flex-1 bg-[#333333]"></div>
                                </div>
                            </div>
                        </div>

                        <div className="space-y-8">
                            <Field label="Background Story" testId="character-background-input">
                                <textarea 
                                    data-testid="character-background-input"
                                    className="w-full h-40 bg-[#181818] border border-[#333333] rounded-lg p-4 text-sm text-[#cccccc] focus:border-[#007acc] outline-none transition-all font-serif leading-relaxed"
                                    placeholder="Describe their origins, past experiences, and defining moments..."
                                    value={editChar.background}
                                    onChange={e => setEditChar({...editChar, background: e.target.value})}
                                />
                            </Field>

                            <div className="grid grid-cols-2 gap-8">
                                <Field label="Aliases" testId="character-alias-input">
                                    <input 
                                        data-testid="character-alias-input"
                                        className="w-full bg-[#181818] border border-[#333333] rounded p-2.5 text-sm text-[#cccccc] focus:border-[#007acc] outline-none"
                                        value={editChar.aliases || ''}
                                        onChange={e => setEditChar({...editChar, aliases: e.target.value})}
                                    />
                                </Field>
                                <Field label="Traits" testId="character-traits-input">
                                    <input 
                                        data-testid="character-traits-input"
                                        className="w-full bg-[#181818] border border-[#333333] rounded p-2.5 text-sm text-[#cccccc] focus:border-[#007acc] outline-none"
                                        value={editChar.traits || ''}
                                        onChange={e => setEditChar({...editChar, traits: e.target.value})}
                                    />
                                </Field>
                            </div>

                            <div className="pt-12 flex justify-end gap-4 border-t border-[#222222]">
                                <button 
                                    data-testid="inspector-save"
                                    className="px-8 py-2.5 bg-[#007acc] hover:bg-[#005fa3] text-white font-bold rounded text-xs uppercase tracking-widest shadow-lg transition-all active:scale-95"
                                    onClick={handleSave}
                                >
                                    Commit Changes
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'relationships' && (
                    <div className="max-w-4xl mx-auto p-12">
                        <div className="flex items-center justify-between mb-8">
                            <h2 className="text-xl font-bold text-white flex items-center gap-2"><LinkIcon size={20} className="text-[#007acc]" /> Network Connections</h2>
                            <button 
                                className="px-4 py-1.5 border border-[#007acc] text-[#007acc] hover:bg-[#007acc] hover:text-white rounded text-[10px] font-bold uppercase transition-all"
                                onClick={() => {
                                    const other = characters.find(c => c.id !== selectedEntity.id);
                                    if (other) {
                                        addRelationship({
                                            id: 'rel_' + Date.now(),
                                            sourceId: selectedEntity.id!,
                                            targetId: other.id,
                                            type: 'Ally'
                                        });
                                    }
                                }}
                                data-testid="add-relationship-btn"
                            >
                                Add Connection
                            </button>
                        </div>
                        
                        <div className="grid grid-cols-1 gap-3">
                            {charRelationships.map(rel => {
                                const otherId = rel.sourceId === selectedEntity.id ? rel.targetId : rel.sourceId;
                                const otherChar = characters.find(c => c.id === otherId);
                                return (
                                    <div key={rel.id} className="bg-[#1e1e1e] border border-[#333333] rounded-lg p-4 flex items-center justify-between group" data-testid="relationship-card">
                                        <div className="flex items-center gap-4">
                                            <div className="w-10 h-10 bg-[#252526] rounded-full flex items-center justify-center border border-[#333333]">
                                                <User size={18} className="text-[#444444]" />
                                            </div>
                                            <div>
                                                <div className="text-sm font-bold text-[#cccccc]">{otherChar?.name || 'Unknown Character'}</div>
                                                <div className="text-[10px] text-[#007acc] uppercase font-bold tracking-widest mt-0.5">{rel.type}</div>
                                            </div>
                                        </div>
                                        <button 
                                            className="p-2 text-[#444444] hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all"
                                            onClick={() => deleteRelationship(rel.id)}
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                );
                            })}
                            {charRelationships.length === 0 && (
                                <div className="py-20 border-2 border-dashed border-[#222222] rounded-xl flex items-center justify-center text-[#444444] text-xs uppercase font-bold tracking-widest">
                                    No connections defined
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {activeTab === 'timeline' && (
                    <div className="max-w-4xl mx-auto p-12">
                        <h2 className="text-xl font-bold text-white mb-8 flex items-center gap-2"><Clock size={20} className="text-[#007acc]" /> Character Timeline</h2>
                        <div className="space-y-4">
                            {charEvents.map(event => (
                                <div key={event.id} className="relative pl-8 border-l-2 border-[#222222] pb-8 last:pb-0" data-testid="char-timeline-event">
                                    <div className="absolute left-[-9px] top-0 w-4 h-4 rounded-full bg-[#007acc] border-4 border-[#121212]"></div>
                                    <div className="bg-[#1e1e1e] border border-[#333333] rounded-lg p-4 hover:border-[#444444] transition-all cursor-pointer">
                                        <div className="text-[10px] text-[#666666] font-bold uppercase mb-1">{event.time || 'Time Unknown'}</div>
                                        <div className="font-bold text-[#cccccc]">{event.title}</div>
                                        <p className="text-xs text-[#666666] mt-2 line-clamp-2">{event.summary}</p>
                                    </div>
                                </div>
                            ))}
                            {charEvents.length === 0 && (
                                <div className="py-20 border-2 border-dashed border-[#222222] rounded-xl flex items-center justify-center text-[#444444] text-xs uppercase font-bold tracking-widest text-center px-12">
                                    This character has not participated in any timeline events
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-[#222222]">
            <User size={120} className="mb-6 opacity-5" />
            <p className="text-sm font-bold uppercase tracking-[0.3em]">No Selection</p>
          </div>
        )}
      </div>
    </div>
  );
};

const TabButton = ({ active, label, onClick, testId }: { active: boolean, label: string, onClick: () => void, testId: string }) => (
    <button 
        data-testid={testId}
        className={`h-full px-2 text-[10px] font-bold uppercase tracking-widest transition-all relative ${
            active ? 'text-[#007acc]' : 'text-[#666666] hover:text-[#999999]'
        }`}
        onClick={onClick}
    >
        {label}
        {active && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#007acc]"></div>}
    </button>
);

const Field = ({ label, children, testId }: { label: string, children: React.ReactNode, testId: string }) => (
    <div>
        <label className="block text-[10px] font-bold text-[#444444] uppercase tracking-[0.2em] mb-3">{label}</label>
        {children}
    </div>
);
