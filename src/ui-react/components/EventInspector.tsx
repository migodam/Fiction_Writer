import React, { useEffect, useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { Save, Trash, Clock, MapPin, Users, BookOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const EventInspector = () => {
  const { 
    timelineEvents, timelineBranches, characters, selectedEntity, 
    addTimelineEvent, updateTimelineEvent, setSelectedEntity 
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const navigate = useNavigate();
  
  const [editEvent, setEditEvent] = useState<any>(null);

  useEffect(() => {
    if (selectedEntity.type === 'timeline_event' && selectedEntity.id) {
      if (selectedEntity.id === 'new') {
        setEditEvent({ 
          id: 'event_' + Date.now(), 
          title: '', 
          summary: '', 
          branchId: timelineBranches[0]?.id || 'branch_main',
          orderIndex: timelineEvents.length,
          participants: []
        });
      } else {
        const event = timelineEvents.find(e => e.id === selectedEntity.id);
        if (event) setEditEvent({ ...event });
      }
    } else {
      setEditEvent(null);
    }
  }, [selectedEntity, timelineEvents, timelineBranches]);

  const handleSave = () => {
    if (!editEvent) return;
    if (!editEvent.title || !editEvent.summary) {
        alert("Title and Summary are required.");
        return;
    }

    if (timelineEvents.find(e => e.id === editEvent.id)) {
      updateTimelineEvent(editEvent);
    } else {
      addTimelineEvent(editEvent);
      setSelectedEntity('timeline_event', editEvent.id);
    }
    setLastActionStatus('Saved');
  };

  const toggleParticipant = (charId: string) => {
      const current = editEvent.participants || [];
      if (current.includes(charId)) {
          setEditEvent({ ...editEvent, participants: current.filter((id: string) => id !== charId) });
      } else {
          setEditEvent({ ...editEvent, participants: [...current, charId] });
      }
  };

  if (!editEvent) return null;

  return (
    <div className="flex flex-col h-full bg-[#252526]">
      <div className="p-4 border-b border-[#333333] flex items-center justify-between bg-[#2d2d2d]">
         <div className="flex items-center gap-2">
           <div className="w-2 h-2 rounded-full bg-[#007acc] animate-pulse"></div>
           <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#cccccc]">Event Configuration</span>
         </div>
         <button 
            className="p-1.5 hover:bg-[#333333] rounded text-[#666666] hover:text-red-400 transition-colors"
            title="Delete Event"
         >
             <Trash size={14} />
         </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
        <div className="space-y-1">
          <label className="block text-[9px] font-bold text-[#555555] uppercase tracking-widest ml-1">Event Title</label>
          <input 
            data-testid="event-title-input"
            className="w-full bg-[#181818] border border-[#333333] rounded-lg p-3 text-sm text-[#cccccc] focus:border-[#007acc] outline-none transition-all shadow-inner"
            placeholder="What happens?"
            value={editEvent.title}
            onChange={e => setEditEvent({...editEvent, title: e.target.value})}
          />
        </div>

        <div className="space-y-1">
          <label className="block text-[9px] font-bold text-[#555555] uppercase tracking-widest ml-1">Summary</label>
          <textarea 
            data-testid="event-summary-input"
            className="w-full h-32 bg-[#181818] border border-[#333333] rounded-lg p-3 text-sm text-[#cccccc] focus:border-[#007acc] outline-none resize-none shadow-inner font-serif leading-relaxed"
            placeholder="Detailed description of the narrative beats..."
            value={editEvent.summary}
            onChange={e => setEditEvent({...editEvent, summary: e.target.value})}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
                <label className="block text-[9px] font-bold text-[#555555] uppercase tracking-widest ml-1">Chronology</label>
                <div className="flex items-center bg-[#181818] border border-[#333333] rounded-lg px-3 group focus-within:border-[#007acc] transition-all shadow-inner">
                    <Clock size={12} className="text-[#444444] group-focus-within:text-[#007acc]" />
                    <input 
                        data-testid="event-time-input"
                        className="w-full bg-transparent p-2.5 text-xs text-[#cccccc] outline-none"
                        placeholder="Day 1, AM"
                        value={editEvent.time || ''}
                        onChange={e => setEditEvent({...editEvent, time: e.target.value})}
                    />
                </div>
            </div>
            <div className="space-y-1">
                <label className="block text-[9px] font-bold text-[#555555] uppercase tracking-widest ml-1">Setting</label>
                <div className="flex items-center bg-[#181818] border border-[#333333] rounded-lg px-3 group focus-within:border-[#007acc] transition-all shadow-inner">
                    <MapPin size={12} className="text-[#444444] group-focus-within:text-[#007acc]" />
                    <input 
                        data-testid="event-location-input"
                        className="w-full bg-transparent p-2.5 text-xs text-[#cccccc] outline-none"
                        placeholder="Location"
                        value={editEvent.location || ''}
                        onChange={e => setEditEvent({...editEvent, location: e.target.value})}
                    />
                </div>
            </div>
        </div>

        <div className="space-y-3">
          <label className="block text-[9px] font-bold text-[#555555] uppercase tracking-widest flex items-center justify-between ml-1">
            <span>Participants</span>
            <Users size={10} className="opacity-40" />
          </label>
          <div className="bg-[#181818] border border-[#333333] rounded-lg p-3 min-h-[80px] shadow-inner">
             {characters.length === 0 ? (
                 <div className="text-[10px] text-[#333333] italic text-center py-4">No characters defined yet</div>
             ) : (
                 <div className="flex flex-wrap gap-2">
                    {characters.map(char => {
                        const isSelected = editEvent.participants?.includes(char.id);
                        return (
                            <div 
                                key={char.id}
                                className={`px-2 py-1 rounded border text-[10px] font-bold cursor-pointer transition-all ${
                                    isSelected 
                                    ? 'bg-[#007acc] border-[#007acc] text-white shadow-lg' 
                                    : 'bg-[#252526] border-[#333333] text-[#666666] hover:border-[#444444]'
                                }`}
                                onClick={() => toggleParticipant(char.id)}
                            >
                                {char.name}
                            </div>
                        );
                    })}
                 </div>
             )}
          </div>
        </div>
      </div>

      <div className="p-4 border-t border-[#333333] flex flex-col gap-2 bg-[#2d2d2d]">
         <button 
           data-testid="open-scene-btn"
           className="w-full py-2 border border-[#444444] hover:bg-[#333333] text-[#cccccc] text-[10px] font-bold uppercase tracking-widest rounded flex items-center justify-center gap-2 transition-all shadow-sm"
           onClick={() => navigate('/writing')}
         >
           <BookOpen size={14} /> Writing Studio
         </button>
         <button 
           data-testid="inspector-save"
           className="w-full py-2 bg-[#007acc] hover:bg-[#005fa3] text-white text-[10px] font-bold uppercase tracking-widest rounded flex items-center justify-center gap-2 transition-all shadow-lg active:scale-95"
           onClick={handleSave}
         >
           <Save size={14} /> Commit Event
         </button>
      </div>
    </div>
  );
};
