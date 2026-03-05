import React, { useEffect, useState } from 'react';
import { useProjectStore, useUIStore } from '../store';
import { Save, Trash, Clock, MapPin, Users } from 'lucide-react';

export const EventInspector = () => {
  const { timelineEvents, timelineBranches, characters, selectedEntity, addTimelineEvent, updateTimelineEvent, setSelectedEntity } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  
  const [editEvent, setEditEvent] = useState<any>(null);

  useEffect(() => {
    if (selectedEntity.type === 'timeline_event' && selectedEntity.id) {
      if (selectedEntity.id === 'new') {
        setEditEvent({ 
          id: 'event_' + Date.now(), 
          title: '', 
          summary: '', 
          branchId: timelineBranches[0]?.id || 'main',
          orderIndex: timelineEvents.length 
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

  if (!editEvent) return null;

  return (
    <div className="flex flex-col h-full bg-[#252526]">
      <div className="p-4 border-b border-[#333333] flex items-center justify-between">
         <div className="flex items-center gap-2">
           <Clock size={16} className="text-[#007acc]" />
           <span className="text-sm font-bold uppercase tracking-wider">Event Details</span>
         </div>
         <div className="flex gap-1">
            <button className="p-1 hover:bg-[#333333] rounded text-[#888888]"><Trash size={14} /></button>
         </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <label className="block text-[10px] font-bold text-[#888888] uppercase mb-1">Title</label>
          <input 
            data-testid="event-title-input"
            className="w-full bg-[#1e1e1e] border border-[#333333] rounded p-2 text-sm text-[#cccccc] focus:border-[#007acc] outline-none"
            placeholder="Event Title"
            value={editEvent.title}
            onChange={e => setEditEvent({...editEvent, title: e.target.value})}
          />
        </div>

        <div>
          <label className="block text-[10px] font-bold text-[#888888] uppercase mb-1">Summary</label>
          <textarea 
            data-testid="event-summary-input"
            className="w-full h-24 bg-[#1e1e1e] border border-[#333333] rounded p-2 text-sm text-[#cccccc] focus:border-[#007acc] outline-none resize-none"
            placeholder="Briefly describe what happens..."
            value={editEvent.summary}
            onChange={e => setEditEvent({...editEvent, summary: e.target.value})}
          />
        </div>

        <div>
          <label className="block text-[10px] font-bold text-[#888888] uppercase mb-1">Time (Display)</label>
          <div className="flex items-center bg-[#1e1e1e] border border-[#333333] rounded px-2">
            <Clock size={14} className="text-[#444444]" />
            <input 
              data-testid="event-time-input"
              className="w-full bg-transparent p-2 text-sm text-[#cccccc] outline-none"
              placeholder="e.g. Day 1, Night"
              value={editEvent.time || ''}
              onChange={e => setEditEvent({...editEvent, time: e.target.value})}
            />
          </div>
        </div>

        <div>
          <label className="block text-[10px] font-bold text-[#888888] uppercase mb-1">Location</label>
          <div className="flex items-center bg-[#1e1e1e] border border-[#333333] rounded px-2">
            <MapPin size={14} className="text-[#444444]" />
            <input 
              data-testid="event-location-input"
              className="w-full bg-transparent p-2 text-sm text-[#cccccc] outline-none"
              placeholder="Where it happens..."
              value={editEvent.location || ''}
              onChange={e => setEditEvent({...editEvent, location: e.target.value})}
            />
          </div>
        </div>

        <div>
          <label className="block text-[10px] font-bold text-[#888888] uppercase mb-1 flex items-center justify-between">
            <span>Participants</span>
            <Users size={12} />
          </label>
          <div className="bg-[#1e1e1e] border border-[#333333] rounded p-2 min-h-[40px]">
             {/* Simple participant list for now */}
             <div className="text-[10px] text-[#444444] italic">Select characters...</div>
          </div>
        </div>
      </div>

      <div className="p-4 border-t border-[#333333]">
         <button 
           data-testid="inspector-save"
           className="w-full py-2 bg-[#007acc] hover:bg-[#005fa3] text-white font-bold rounded flex items-center justify-center gap-2 transition-colors"
           onClick={handleSave}
         >
           <Save size={16} /> Save Event
         </button>
      </div>
    </div>
  );
};
