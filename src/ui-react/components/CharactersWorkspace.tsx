import React, { useEffect, useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { Plus, Check, X, User } from 'lucide-react';

export const CharactersWorkspace = () => {
  const { characters, candidates, selectedEntity, setSelectedEntity, addCharacter, updateCharacter, confirmCandidate, rejectCandidate } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  
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

  return (
    <div className="flex h-full overflow-hidden">
      {/* Character List Column */}
      <div className="w-64 border-r border-[#333333] flex flex-col bg-[#1e1e1e]" data-testid="character-list">
        <div className="p-4 border-b border-[#333333] flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-widest text-[#888888]">Confirmed</h3>
          <button 
            data-testid="new-character-btn"
            className="p-1 hover:bg-[#333333] rounded text-[#007acc]"
            onClick={() => setSelectedEntity('character', 'new')}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {characters.map(char => (
            <div 
              key={char.id}
              data-testid={`character-card-${char.id}`}
              className={`p-3 border-b border-[#333333] cursor-pointer hover:bg-[#252526] transition-colors ${selectedEntity.id === char.id ? 'bg-[#252526] border-l-2 border-l-[#007acc]' : ''}`}
              onClick={() => setSelectedEntity('character', char.id)}
            >
              <div className="font-medium text-[#cccccc]">{char.name}</div>
              <div className="text-xs text-[#666666] truncate">{char.background}</div>
            </div>
          ))}
          {characters.length === 0 && (
            <div className="p-8 text-center text-[#666666] text-sm">No characters yet.</div>
          )}
        </div>

        {/* Candidates Section */}
        <div className="p-4 border-t border-[#333333] bg-[#252526]">
           <h3 className="text-xs font-bold uppercase tracking-widest text-[#888888] mb-4">Candidates</h3>
           {candidates.map(cand => (
             <div 
              key={cand.id} 
              data-testid={`candidate-card-${cand.id}`}
              className="p-3 mb-2 bg-[#1e1e1e] border border-[#333333] rounded group"
            >
               <div className="font-medium text-sm mb-1">{cand.name}</div>
               <div className="flex gap-2">
                 <button 
                  data-testid="candidate-confirm-btn"
                  className="flex-1 py-1 bg-[#2e7d32] hover:bg-[#388e3c] text-white rounded text-[10px] flex items-center justify-center gap-1"
                  onClick={() => confirmCandidate(cand.id)}
                 >
                   <Check size={10} /> Confirm
                 </button>
                 <button 
                  data-testid="candidate-reject-btn"
                  className="p-1 bg-[#333333] hover:bg-red-900 rounded text-white"
                  onClick={() => rejectCandidate(cand.id)}
                 >
                   <X size={10} />
                 </button>
               </div>
             </div>
           ))}
        </div>
      </div>

      {/* Profile Editor */}
      <div className="flex-1 bg-[#121212] overflow-y-auto">
        {editChar ? (
          <div className="max-w-3xl mx-auto p-12">
            <div className="flex items-center gap-4 mb-8">
               <div className="w-16 h-16 bg-[#252526] rounded-full flex items-center justify-center border border-[#333333]">
                 <User size={32} className="text-[#666666]" />
               </div>
               <div>
                  <input 
                    data-testid="character-name-input"
                    className="bg-transparent text-4xl font-bold text-white outline-none placeholder-[#333333] w-full"
                    placeholder="Character Name"
                    value={editChar.name}
                    onChange={e => setEditChar({...editChar, name: e.target.value})}
                  />
                  <div className="text-[#007acc] text-sm font-medium mt-1 uppercase tracking-widest">Character Profile</div>
               </div>
            </div>

            <div className="space-y-6">
              <div>
                <label className="block text-xs font-bold text-[#888888] uppercase tracking-wider mb-2">Background Story</label>
                <textarea 
                  data-testid="character-background-input"
                  className="w-full h-32 bg-[#1e1e1e] border border-[#333333] rounded p-3 text-[#cccccc] focus:border-[#007acc] outline-none transition-colors"
                  placeholder="Describe where they come from and who they are..."
                  value={editChar.background}
                  onChange={e => setEditChar({...editChar, background: e.target.value})}
                />
              </div>

              <div className="grid grid-cols-2 gap-6">
                 <div>
                    <label className="block text-xs font-bold text-[#888888] uppercase tracking-wider mb-2">Aliases</label>
                    <input 
                      data-testid="character-alias-input"
                      className="w-full bg-[#1e1e1e] border border-[#333333] rounded p-2 text-[#cccccc] focus:border-[#007acc] outline-none"
                      value={editChar.aliases || ''}
                      onChange={e => setEditChar({...editChar, aliases: e.target.value})}
                    />
                 </div>
                 <div>
                    <label className="block text-xs font-bold text-[#888888] uppercase tracking-wider mb-2">Traits</label>
                    <input 
                      data-testid="character-traits-input"
                      className="w-full bg-[#1e1e1e] border border-[#333333] rounded p-2 text-[#cccccc] focus:border-[#007acc] outline-none"
                      value={editChar.traits || ''}
                      onChange={e => setEditChar({...editChar, traits: e.target.value})}
                    />
                 </div>
              </div>

              <div className="pt-8 flex justify-end gap-4 border-t border-[#333333]">
                  <button 
                    data-testid="inspector-save"
                    className="px-6 py-2 bg-[#007acc] hover:bg-[#005fa3] text-white font-bold rounded transition-colors"
                    onClick={handleSave}
                  >
                    Save Profile
                  </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-[#666666]">
            <User size={64} className="mb-4 opacity-20" />
            <p>Select a character from the list or create a new one.</p>
          </div>
        )}
      </div>
    </div>
  );
};
