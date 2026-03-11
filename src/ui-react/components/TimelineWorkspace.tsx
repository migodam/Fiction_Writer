import React, { useState } from 'react';
import { useProjectStore } from '../store';
import { Plus, Maximize2, Minimize2, Filter, Layers, List, ChevronRight, Clock, MapPin, Users } from 'lucide-react';

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
    <div className="flex flex-col h-full bg-bg overflow-hidden">
      {/* Timeline Toolbar */}
      <div className="h-12 border-b border-border flex items-center px-6 gap-8 bg-bg-elev-1 z-10 shadow-1" data-testid="timeline-toolbar">
        <div className="flex items-center gap-3">
            <button 
                data-testid="add-event-btn"
                className="flex items-center gap-2 px-4 py-1.5 bg-brand hover:bg-brand-2 text-white text-[11px] font-bold rounded-lg shadow-2 transition-all uppercase tracking-widest active:scale-95"
                onClick={handleAddEvent}
            >
                <Plus size={14} strokeWidth={3} /> Add Event
            </button>
        </div>

        <div className="h-5 w-px bg-divider"></div>

        <div className="flex items-center gap-6">
            <div className="flex items-center gap-2.5 bg-bg border border-border rounded-lg px-3 py-1.5 hover:border-border-2 transition-all cursor-pointer group">
                <Layers size={14} className="text-text-3 group-hover:text-brand transition-colors" />
                <select 
                    className="bg-transparent text-[10px] font-bold text-text-2 outline-none uppercase tracking-wider cursor-pointer focus:text-text transition-colors"
                    value={viewMode}
                    onChange={(e) => setViewMode(e.target.value as any)}
                >
                    <option value="linear">Linear Timeline</option>
                    <option value="chapter">Chapter Grouping</option>
                </select>
            </div>

            <div className="flex items-center gap-4 bg-bg border border-border rounded-lg px-4 py-1.5 shadow-inner">
                <button 
                    className="text-text-3 hover:text-brand transition-colors active:scale-90"
                    onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}
                    title="Zoom Out"
                >
                    <Minimize2 size={14} />
                </button>
                <input 
                    type="range" 
                    min="0.5" 
                    max="2" 
                    step="0.1" 
                    value={zoom} 
                    onChange={(e) => setZoom(parseFloat(e.target.value))}
                    className="w-32 h-1 bg-divider rounded-lg appearance-none cursor-pointer accent-brand"
                />
                <button 
                    className="text-text-3 hover:text-brand transition-colors active:scale-90"
                    onClick={() => setZoom(Math.min(2, zoom + 0.1))}
                    title="Zoom In"
                >
                    <Maximize2 size={14} />
                </button>
            </div>
        </div>

        <div className="ml-auto flex items-center gap-4">
            <div className="flex items-center gap-1.5 px-3 py-1 bg-bg-elev-2 border border-border rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-brand"></span>
                <span className="text-[10px] font-bold text-text-2 uppercase tracking-widest">Tracks: {timelineBranches.length}</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1 bg-bg-elev-2 border border-border rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-amber"></span>
                <span className="text-[10px] font-bold text-text-2 uppercase tracking-widest">Events: {timelineEvents.length}</span>
            </div>
        </div>
      </div>

      {/* Timeline Canvas */}
      <div className="flex-1 overflow-auto bg-bg custom-scrollbar relative p-16" data-testid="timeline-canvas">
        {/* Background Grid */}
        <div className="absolute inset-0 pointer-events-none opacity-[0.03] select-none" style={{ 
            backgroundImage: `linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)`,
            backgroundSize: `${40 * zoom}px ${40 * zoom}px`
        }}></div>

        <div 
            className="relative flex flex-col gap-8 min-h-full" 
            style={{ minWidth: `${2000 * zoom}px` }}
        >
          {timelineBranches.map((branch) => (
            <div 
                key={branch.id} 
                className="relative h-44 border border-border bg-bg-elev-1 rounded-2xl flex items-center px-10 group transition-all hover:bg-bg-elev-2 hover:border-border-2 shadow-1" 
                data-testid={`timeline-branch-${branch.id}`}
                onDragOver={onDragOver}
                onDrop={(e) => onDrop(e, branch.id, timelineEvents.filter(ev => ev.branchId === branch.id).length)}
            >
              {/* Branch Header Overlay */}
              <div className="absolute left-6 top-6 flex items-center gap-3 z-20">
                  <div className="w-2.5 h-2.5 rounded-full bg-brand shadow-[0_0_12px_rgba(124,58,237,0.6)]"></div>
                  <span className="text-[11px] font-black text-text-3 uppercase tracking-[0.25em] group-hover:text-brand transition-colors duration-300">{branch.name}</span>
              </div>
              
              {/* Event Lane */}
              <div className="flex gap-16 items-center ml-24 h-full relative z-10">
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
                        "w-72 p-5 rounded-xl border-2 cursor-pointer transition-all relative group/node animate-in zoom-in-95 duration-200",
                        selectedEntity.id === event.id 
                            ? "bg-bg-elev-2 border-brand shadow-2 ring-1 ring-brand/30" 
                            : "bg-bg border-border hover:border-border-2 hover:bg-bg-elev-2 shadow-1"
                      )}
                      style={{ transform: `scale(${0.95 + (zoom * 0.05)})` }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEntity('timeline_event', event.id);
                      }}
                    >
                      {/* Selection Glow */}
                      {selectedEntity.id === event.id && (
                          <div className="absolute inset-0 bg-brand/5 rounded-xl animate-pulse"></div>
                      )}

                      <div className="flex items-center justify-between mb-3 relative z-10">
                        <div className="flex items-center gap-1.5 text-brand-2">
                            <Clock size={10} />
                            <span className="text-[10px] font-extrabold uppercase tracking-[0.15em]">{event.time || `T+${idx}`}</span>
                        </div>
                        <ChevronRight size={12} className="text-text-3 opacity-0 group-hover/node:opacity-100 transition-opacity" />
                      </div>

                      <div className="text-sm font-bold text-text truncate mb-2 relative z-10 group-hover/node:text-brand transition-colors">{event.title}</div>
                      <p className="text-[11px] text-text-2 line-clamp-2 leading-relaxed opacity-70 relative z-10">{event.summary}</p>
                      
                      {/* Metadata row */}
                      <div className="mt-4 pt-3 border-t border-divider flex items-center gap-3 relative z-10">
                        {event.location && (
                            <div className="flex items-center gap-1 text-[9px] text-text-3 font-bold uppercase tracking-widest truncate">
                                <MapPin size={8} /> {event.location}
                            </div>
                        )}
                        {event.participants && event.participants.length > 0 && (
                            <div className="flex items-center gap-1 text-[9px] text-text-3 font-bold uppercase tracking-widest">
                                <Users size={8} /> {event.participants.length}
                            </div>
                        )}
                      </div>

                      {/* Connector Line (Internal) */}
                      <div className="absolute right-[-64px] top-1/2 w-16 h-0.5 bg-divider group-last/node:hidden z-0 overflow-hidden">
                          <div className="w-full h-full bg-brand/20 animate-pulse"></div>
                      </div>
                    </div>
                  ))}
                  
                  {/* Empty state prompt */}
                  {timelineEvents.filter(ev => ev.branchId === branch.id).length === 0 && (
                      <div className="flex flex-col items-center justify-center opacity-20 ml-20">
                          <Plus size={32} className="mb-2 text-text-3" />
                          <p className="text-[10px] text-text-3 font-black uppercase tracking-[0.3em] italic">Empty Track</p>
                      </div>
                  )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');
