import React, { useState } from 'react';
import { useProjectStore } from '../store';
import { Plus, Maximize2, Minimize2, Filter, Layers, List } from 'lucide-react';

export const TimelineWorkspace = () => {
  const { 
    timelineEvents, timelineBranches, setSelectedEntity, selectedEntity,
    updateTimelineEvent 
  } = useProjectStore();

  const [zoom, setZoom] = useState(1);
  const [viewMode, setViewMode] = useState<'linear' | 'chapter'>('linear');

  const handleAddEvent = () => {
    setSelectedEntity('timeline_event', 'new');
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const onDrop = (e: React.DragEvent, branchId: string, targetOrderIndex: number) => {
    const eventId = e.dataTransfer.getData('eventId');
    const event = timelineEvents.find(ev => ev.id === eventId);
    if (event) {
        updateTimelineEvent({
            ...event,
            branchId,
            orderIndex: targetOrderIndex
        });
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#121212] overflow-hidden">
      {/* Timeline Toolbar */}
      <div className="h-12 border-b border-[#333333] flex items-center px-4 gap-6 bg-[#1e1e1e] z-10 shadow-md" data-testid="timeline-toolbar">
        <div className="flex items-center gap-2">
            <button 
                data-testid="add-event-btn"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[#007acc] hover:bg-[#005fa3] text-white text-[10px] font-bold rounded shadow-lg transition-all uppercase tracking-widest"
                onClick={handleAddEvent}
            >
                <Plus size={12} strokeWidth={3} /> Add Event
            </button>
        </div>

        <div className="h-4 w-px bg-[#333333]"></div>

        <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-[#252526] rounded px-2 py-1 border border-[#333333]">
                <Layers size={12} className="text-[#666666]" />
                <select 
                    className="bg-transparent text-[10px] font-bold text-[#cccccc] outline-none uppercase tracking-tighter cursor-pointer"
                    value={viewMode}
                    onChange={(e) => setViewMode(e.target.value as any)}
                >
                    <option value="linear">Linear View</option>
                    <option value="chapter">Chapter View</option>
                </select>
            </div>

            <div className="flex items-center gap-2">
                <Minimize2 size={12} className="text-[#666666] cursor-pointer hover:text-[#cccccc]" onClick={() => setZoom(Math.max(0.5, zoom - 0.1))} />
                <input 
                    type="range" 
                    min="0.5" 
                    max="2" 
                    step="0.1" 
                    value={zoom} 
                    onChange={(e) => setZoom(parseFloat(e.target.value))}
                    className="w-24 h-1 bg-[#333333] rounded-lg appearance-none cursor-pointer accent-[#007acc]"
                />
                <Maximize2 size={12} className="text-[#666666] cursor-pointer hover:text-[#cccccc]" onClick={() => setZoom(Math.min(2, zoom + 0.1))} />
            </div>
        </div>

        <div className="ml-auto flex items-center gap-2 text-[10px] font-bold text-[#444444] uppercase tracking-[0.2em]">
            <span>Tracks: {timelineBranches.length}</span>
            <div className="h-4 w-px bg-[#333333] mx-2"></div>
            <span>Events: {timelineEvents.length}</span>
        </div>
      </div>

      {/* Timeline Canvas */}
      <div className="flex-1 overflow-auto bg-[#121212] custom-scrollbar p-12" data-testid="timeline-canvas">
        <div 
            className="relative flex flex-col gap-4" 
            style={{ minWidth: `${2000 * zoom}px` }}
        >
          {timelineBranches.map((branch) => (
            <div 
                key={branch.id} 
                className="relative h-32 border border-[#222222] bg-[#181818] rounded-xl flex items-center px-6 group transition-all hover:bg-[#1a1a1a] hover:border-[#333333]" 
                data-testid={`timeline-branch-${branch.id}`}
                onDragOver={onDragOver}
                onDrop={(e) => onDrop(e, branch.id, timelineEvents.filter(ev => ev.branchId === branch.id).length)}
            >
              <div className="absolute left-4 top-4 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-[#007acc] shadow-[0_0_8px_rgba(0,122,204,0.5)]"></div>
                  <span className="text-[10px] font-bold text-[#444444] uppercase tracking-widest group-hover:text-[#888888] transition-colors">{branch.name}</span>
              </div>
              
              <div className="flex gap-12 items-center ml-24 h-full relative">
                {timelineEvents
                  .filter(e => e.branchId === branch.id)
                  .sort((a, b) => a.orderIndex - b.orderIndex)
                  .map((event, idx) => (
                    <div 
                      key={event.id}
                      draggable
                      onDragStart={(e) => {
                          e.dataTransfer.setData('eventId', event.id);
                      }}
                      data-testid={`timeline-node-${event.id}`}
                      className={cnLocal(
                        "w-64 p-4 rounded-lg border-2 cursor-pointer transition-all relative z-10 group/node",
                        selectedEntity.id === event.id 
                            ? "bg-[#252526] border-[#007acc] shadow-[0_0_20px_rgba(0,122,204,0.2)]" 
                            : "bg-[#1e1e1e] border-[#2a2a2a] hover:border-[#444444] hover:bg-[#222222]"
                      )}
                      style={{ transform: `scale(${0.9 + (zoom * 0.1)})` }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEntity('timeline_event', event.id);
                      }}
                    >
                      <div className="text-[10px] font-bold text-[#007acc] uppercase tracking-widest mb-2 opacity-60">{event.time || `Event ${idx + 1}`}</div>
                      <div className="text-sm font-bold text-[#cccccc] truncate mb-1">{event.title}</div>
                      <div className="text-[10px] text-[#666666] line-clamp-2 leading-relaxed">{event.summary}</div>
                      
                      {/* Connector Line */}
                      <div className="absolute right-[-48px] top-1/2 w-12 h-0.5 bg-[#222222] group-last/node:hidden"></div>
                    </div>
                  ))}
                  
                  {/* Empty state prompt */}
                  {timelineEvents.filter(ev => ev.branchId === branch.id).length === 0 && (
                      <div className="text-[10px] text-[#222222] font-bold uppercase tracking-widest italic ml-4">Drag events here or use Add Event</div>
                  )}
              </div>
            </div>
          ))}
          
          {/* Background Grid (Optional aesthetic) */}
          <div className="absolute inset-0 pointer-events-none opacity-5 overflow-hidden rounded-xl">
              <div className="w-full h-full" style={{ backgroundImage: 'radial-gradient(#ffffff 1px, transparent 1px)', backgroundSize: '40px 40px' }}></div>
          </div>
        </div>
      </div>
    </div>
  );
};

const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');
