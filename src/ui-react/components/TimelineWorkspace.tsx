import React from 'react';
import { useProjectStore } from '../store';
import { Plus } from 'lucide-react';

export const TimelineWorkspace = () => {
  const { timelineEvents, timelineBranches, setSelectedEntity, selectedEntity } = useProjectStore();

  const handleAddEvent = () => {
    setSelectedEntity('timeline_event', 'new');
  };

  return (
    <div className="flex flex-col h-full bg-[#121212]">
      {/* Timeline Toolbar */}
      <div className="h-12 border-b border-[#333333] flex items-center px-4 gap-4" data-testid="timeline-toolbar">
        <button 
          data-testid="add-event-btn"
          className="flex items-center gap-1.5 px-3 py-1 bg-[#007acc] hover:bg-[#005fa3] text-white text-xs font-bold rounded"
          onClick={handleAddEvent}
        >
          <Plus size={14} /> Add Event
        </button>
        <div className="h-4 w-px bg-[#333333]"></div>
        <span className="text-xs text-[#666666] uppercase font-bold tracking-widest">Branches: {timelineBranches.length}</span>
      </div>

      {/* Timeline Canvas */}
      <div className="flex-1 overflow-auto p-8" data-testid="timeline-canvas">
        <div className="relative min-w-[1000px]">
          {timelineBranches.map((branch, index) => (
            <div key={branch.id} className="relative h-24 border-b border-[#222222] flex items-center px-4 group" data-testid={`timeline-branch-${branch.id}`}>
              <div className="absolute left-0 top-0 text-[10px] font-bold text-[#444444] uppercase p-2 group-hover:text-[#888888] transition-colors">{branch.name}</div>
              
              <div className="flex gap-8 items-center ml-20">
                {timelineEvents
                  .filter(e => e.branchId === branch.id)
                  .sort((a, b) => a.orderIndex - b.orderIndex)
                  .map(event => (
                    <div 
                      key={event.id}
                      data-testid={`timeline-node-${event.id}`}
                      className={cnLocal(
                        "w-48 p-3 bg-[#1e1e1e] border rounded cursor-pointer transition-all",
                        selectedEntity.id === event.id ? "border-[#007acc] shadow-[0_0_10px_rgba(0,122,204,0.3)]" : "border-[#333333] hover:border-[#666666]"
                      )}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEntity('timeline_event', event.id);
                      }}
                    >
                      <div className="text-xs font-bold text-[#cccccc] truncate">{event.title}</div>
                      <div className="text-[10px] text-[#666666] truncate mt-1">{event.summary}</div>
                    </div>
                  ))}
              </div>
            </div>
          ))}
          {/* Horizontal Line for "Time" */}
          <div className="absolute left-20 top-0 bottom-0 w-px bg-[#333333]"></div>
        </div>
      </div>
    </div>
  );
};

// Utils copy since components are in separate files
const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');
