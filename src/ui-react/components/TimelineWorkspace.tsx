import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRightCircle, FilterX, GitBranchPlus, Maximize2, Minimize2, Plus } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

export const TimelineWorkspace = () => {
  const {
    timelineEvents,
    timelineBranches,
    setSelectedEntity,
    selectedEntity,
    updateTimelineEvent,
    addTimelineBranch,
    characters,
    worldItems,
  } = useProjectStore();
  const { openContextMenu, setLastActionStatus } = useUIStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [hoveredEventId, setHoveredEventId] = useState<string | null>(null);

  const characterFilter = searchParams.get('character') || '';
  const locationFilter = searchParams.get('location') || '';
  const branchFilter = searchParams.get('branch') || '';
  const eventFocus = searchParams.get('event') || '';

  useEffect(() => {
    if (eventFocus) setSelectedEntity('timeline_event', eventFocus);
  }, [eventFocus, setSelectedEntity]);

  useEffect(() => {
    const node = canvasRef.current;
    if (!node) return;
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      setZoom((current) => Math.min(1.8, Math.max(0.6, current - event.deltaY * 0.001)));
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, []);

  const locationOptions = useMemo(() => worldItems.filter((item) => item.type === 'location'), [worldItems]);
  const branchRows = branchFilter ? timelineBranches.filter((branch) => branch.id === branchFilter) : timelineBranches.slice().sort((a, b) => a.sortOrder - b.sortOrder);
  const visibleEvents = useMemo(() => timelineEvents.filter((event) => {
    if (characterFilter && !event.participantCharacterIds.includes(characterFilter)) return false;
    if (locationFilter && !event.locationIds.includes(locationFilter)) return false;
    if (branchFilter && event.branchId !== branchFilter && !event.sharedBranchIds?.includes(branchFilter)) return false;
    return true;
  }), [branchFilter, characterFilter, locationFilter, timelineEvents]);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg">
      <div className="flex items-center gap-4 border-b border-border bg-bg-elev-1 px-6 py-3" data-testid="timeline-toolbar">
        <button type="button" data-testid="add-event-btn" className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white" onClick={() => setSelectedEntity('timeline_event', 'new')}>
          <Plus size={13} className="mr-2 inline" />{t('timeline.addEvent')}
        </button>
        <button type="button" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" onClick={() => {
          const parent = branchRows[0]?.id || timelineBranches[0]?.id || 'branch_main';
          addTimelineBranch({ id: `branch_${Date.now()}`, name: 'New Branch', description: 'Branch from current narrative line.', parentBranchId: parent, forkEventId: visibleEvents[0]?.id || null, mergeEventId: null, color: '#38bdf8', sortOrder: timelineBranches.length, collapsed: false });
          setLastActionStatus('Branch created');
        }}>
          <GitBranchPlus size={13} className="mr-2 inline" />New Branch
        </button>
        <select className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2" value={branchFilter} onChange={(event) => updateParam(searchParams, setSearchParams, 'branch', event.target.value)} data-testid="timeline-branch-filter">
          <option value="">{t('timeline.branchFilter')}</option>
          {timelineBranches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
        </select>
        <select className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2" value={characterFilter} onChange={(event) => updateParam(searchParams, setSearchParams, 'character', event.target.value)} data-testid="timeline-character-filter">
          <option value="">{t('timeline.allCharacters')}</option>
          {characters.map((character) => <option key={character.id} value={character.id}>{character.name}</option>)}
        </select>
        <select className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2" value={locationFilter} onChange={(event) => updateParam(searchParams, setSearchParams, 'location', event.target.value)} data-testid="timeline-location-filter">
          <option value="">{t('timeline.allLocations')}</option>
          {locationOptions.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
        </select>
        <button type="button" data-testid="timeline-clear-filters" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" onClick={() => setSearchParams({})}>
          <FilterX size={13} className="mr-2 inline" />{t('timeline.clearFilters')}
        </button>
        <div className="ml-auto flex items-center gap-3 rounded-full border border-border bg-bg px-4 py-2">
          <button type="button" className="text-text-3 hover:text-brand" onClick={() => setZoom((current) => Math.max(0.6, current - 0.1))}><Minimize2 size={14} /></button>
          <input type="range" min="0.6" max="1.8" step="0.1" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} className="w-24 accent-brand" />
          <button type="button" className="text-text-3 hover:text-brand" onClick={() => setZoom((current) => Math.min(1.8, current + 0.1))}><Maximize2 size={14} /></button>
        </div>
      </div>

      <div className="border-b border-border bg-bg-elev-1/70 px-6 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3" data-testid="timeline-filter-state">
        {characterFilter && <span>{t('timeline.filteredByCharacter')}: {characters.find((entry) => entry.id === characterFilter)?.name} </span>}
        {locationFilter && <span>{t('timeline.filteredByLocation')}: {locationOptions.find((entry) => entry.id === locationFilter)?.name} </span>}
        {branchFilter && <span>{t('timeline.branchFilter')}: {timelineBranches.find((entry) => entry.id === branchFilter)?.name}</span>}
        {!characterFilter && !locationFilter && !branchFilter && <span>{t('timeline.title')}</span>}
      </div>

      <div ref={canvasRef} className="relative flex-1 overflow-hidden bg-bg" data-testid="timeline-canvas" onMouseDown={(event) => {
        if ((event.target as HTMLElement).dataset.timelineNode) return;
        const startX = event.clientX;
        const startY = event.clientY;
        const initialPanX = panX;
        const initialPanY = panY;
        const onMove = (moveEvent: MouseEvent) => {
          setPanX(initialPanX + (moveEvent.clientX - startX));
          setPanY(initialPanY + (moveEvent.clientY - startY));
        };
        const onUp = () => {
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      }}>
        <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)', backgroundSize: `${48 * zoom}px ${48 * zoom}px` }} />
        <div className="absolute inset-0 overflow-auto custom-scrollbar">
          <div className="min-h-full min-w-[1500px] p-10" style={{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})`, transformOrigin: 'top left' }}>
            {branchRows.map((branch) => {
              const events = visibleEvents
                .filter((event) => event.branchId === branch.id || event.sharedBranchIds?.includes(branch.id))
                .sort((a, b) => a.orderIndex - b.orderIndex);
              return (
                <div key={branch.id} className="mb-10 rounded-[30px] border border-border bg-bg-elev-1 px-8 py-7 shadow-1" data-testid={`timeline-branch-${branch.id}`} onContextMenu={(event) => {
                  event.preventDefault();
                  openContextMenu({
                    x: event.clientX,
                    y: event.clientY,
                    items: [{ id: 'focus-branch', label: 'Focus Branch', action: () => updateParam(searchParams, setSearchParams, 'branch', branch.id) }],
                  });
                }}>
                  <div className="mb-7 flex items-center gap-4">
                    <div className="h-3 w-3 rounded-full shadow-[0_0_18px_rgba(242,200,121,0.5)]" style={{ background: branch.color || '#f59e0b' }} />
                    <div>
                      <div className="text-[11px] font-black uppercase tracking-[0.3em] text-text-2">{branch.name}</div>
                      <div className="mt-1 text-sm text-text-3">{branch.description}</div>
                    </div>
                    {branch.parentBranchId && <div className="ml-auto rounded-full border border-border px-3 py-1 text-[10px] uppercase tracking-[0.25em] text-text-3">Fork from {timelineBranches.find((entry) => entry.id === branch.parentBranchId)?.name}</div>}
                  </div>
                  <div className="relative flex items-center gap-8 overflow-visible">
                    <div className="absolute left-0 right-0 top-1/2 h-px bg-white/10" />
                    {events.map((event) => {
                      const isSelected = selectedEntity.id === event.id;
                      const isShared = event.sharedBranchIds?.includes(branch.id);
                      return (
                        <div key={`${branch.id}-${event.id}`} className="relative z-10 flex flex-col items-center gap-3">
                          <button
                            type="button"
                            data-testid={event.branchId === branch.id ? `timeline-node-${event.id}` : `timeline-node-shared-${event.id}-${branch.id}`}
                            data-timeline-node="true"
                            draggable
                            onDragStart={(dragEvent) => dragEvent.dataTransfer.setData('eventId', event.id)}
                            onDragOver={(dragEvent) => dragEvent.preventDefault()}
                            onDrop={(dropEvent) => {
                              const draggedId = dropEvent.dataTransfer.getData('eventId');
                              const draggedEvent = timelineEvents.find((entry) => entry.id === draggedId);
                              if (draggedEvent) updateTimelineEvent({ ...draggedEvent, branchId: branch.id, orderIndex: event.orderIndex });
                            }}
                            className={cn('group relative h-16 w-16 rounded-full border-2 transition-all', isSelected ? 'border-brand bg-brand text-white shadow-[0_0_30px_rgba(201,131,40,0.45)]' : 'border-white/14 bg-slate-950/70 text-brand-2 hover:border-brand')}
                            onClick={() => setSelectedEntity('timeline_event', event.id)}
                            onMouseEnter={() => setHoveredEventId(event.id)}
                            onMouseLeave={() => setHoveredEventId((current) => current === event.id ? null : current)}
                            onContextMenu={(ctxEvent) => {
                              ctxEvent.preventDefault();
                              openContextMenu({
                                x: ctxEvent.clientX,
                                y: ctxEvent.clientY,
                                items: [
                                  { id: 'open-event', label: 'Open Event Inspector', action: () => setSelectedEntity('timeline_event', event.id) },
                                  { id: 'scene-jump', label: 'Open Linked Scene', action: () => event.linkedSceneIds[0] && navigate(`/writing/scenes?scene=${event.linkedSceneIds[0]}`) },
                                ],
                              });
                            }}
                          >
                            <span className="absolute inset-0 flex items-center justify-center text-[9px] font-black uppercase tracking-[0.2em]">{event.orderIndex + 1}</span>
                          </button>
                          <div className="text-center">
                            <div className="text-[11px] font-black text-text">{event.title}</div>
                            <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-text-3">{event.time}</div>
                            {isShared && <div className="mt-1 text-[9px] uppercase tracking-[0.2em] text-amber">shared</div>}
                          </div>
                          {hoveredEventId === event.id && (
                            <div className="absolute top-[88px] z-20 w-72 rounded-2xl border border-border bg-slate-950/95 p-4 text-left shadow-[0_24px_50px_rgba(0,0,0,0.5)]">
                              <div className="text-sm font-black text-text">{event.title}</div>
                              <div className="mt-2 text-xs leading-relaxed text-text-2">{event.summary}</div>
                            </div>
                          )}
                          {event.linkedSceneIds.length > 0 && (
                            <button type="button" data-testid="timeline-open-scene-btn" className="rounded-xl border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-2 hover:border-brand" onClick={() => {
                              setSelectedEntity('scene', event.linkedSceneIds[0]);
                              navigate(`/writing/scenes?scene=${event.linkedSceneIds[0]}`);
                            }}>
                              <ArrowRightCircle size={12} className="mr-2 inline" />{t('timeline.jumpToScene')}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

const updateParam = (
  current: URLSearchParams,
  setSearchParams: ReturnType<typeof useSearchParams>[1],
  key: string,
  value: string
) => {
  const next = new URLSearchParams(current);
  if (value) next.set(key, value);
  else next.delete(key);
  setSearchParams(next);
};
