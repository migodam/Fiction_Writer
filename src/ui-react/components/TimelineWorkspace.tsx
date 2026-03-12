import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useProjectStore } from '../store';
import { Plus, Maximize2, Minimize2, Layers, ChevronRight, Clock, MapPin, Users, FilterX, ArrowRightCircle } from 'lucide-react';
import { useI18n } from '../i18n';

export const TimelineWorkspace = () => {
  const {
    timelineEvents,
    timelineBranches,
    setSelectedEntity,
    selectedEntity,
    updateTimelineEvent,
    characters,
    worldItems,
  } = useProjectStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useI18n();

  const [zoom, setZoom] = useState(1);
  const [viewMode, setViewMode] = useState<'linear' | 'chapter'>('linear');

  const characterFilter = searchParams.get('character') || '';
  const locationFilter = searchParams.get('location') || '';
  const branchFilter = searchParams.get('branch') || '';
  const eventFocus = searchParams.get('event') || '';

  useEffect(() => {
    if (eventFocus) {
      setSelectedEntity('timeline_event', eventFocus);
    }
  }, [eventFocus, setSelectedEntity]);

  const locationOptions = useMemo(
    () => worldItems.filter((item) => item.type === 'location'),
    [worldItems]
  );

  const visibleEvents = useMemo(() => {
    return timelineEvents.filter((event) => {
      if (characterFilter && !event.participantCharacterIds.includes(characterFilter)) {
        return false;
      }
      if (locationFilter && !event.locationIds.includes(locationFilter)) {
        return false;
      }
      if (branchFilter && event.branchId !== branchFilter) {
        return false;
      }
      return true;
    });
  }, [branchFilter, characterFilter, locationFilter, timelineEvents]);

  const handleAddEvent = () => {
    setSelectedEntity('timeline_event', 'new');
  };

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next);
  };

  const clearFilters = () => {
    setSearchParams({});
  };

  const onDragOver = (event: React.DragEvent) => {
    event.preventDefault();
  };

  const onDrop = (event: React.DragEvent, branchId: string, targetOrderIndex: number) => {
    const eventId = event.dataTransfer.getData('eventId');
    const target = timelineEvents.find((entry) => entry.id === eventId);
    if (target) {
      updateTimelineEvent({ ...target, branchId, orderIndex: targetOrderIndex });
    }
  };

  const getLocationLabel = (event: (typeof timelineEvents)[number]) => {
    return event.locationIds
      .map((locationId) => locationOptions.find((item) => item.id === locationId)?.name || locationId)
      .join(', ');
  };

  const branchRows = branchFilter ? timelineBranches.filter((branch) => branch.id === branchFilter) : timelineBranches;

  return (
    <div className="flex flex-col h-full bg-bg overflow-hidden">
      <div className="h-12 border-b border-border flex items-center px-6 gap-6 bg-bg-elev-1 z-10 shadow-1" data-testid="timeline-toolbar">
        <div className="flex items-center gap-3">
          <button
            data-testid="add-event-btn"
            className="flex items-center gap-2 px-4 py-1.5 bg-brand hover:bg-brand-2 text-white text-[11px] font-bold rounded-lg shadow-2 transition-all uppercase tracking-widest active:scale-95"
            onClick={handleAddEvent}
          >
            <Plus size={14} strokeWidth={3} /> {t('timeline.addEvent')}
          </button>
        </div>

        <div className="h-5 w-px bg-divider"></div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5 bg-bg border border-border rounded-lg px-3 py-1.5">
            <Layers size={14} className="text-text-3" />
            <select className="bg-transparent text-[10px] font-bold text-text-2 outline-none uppercase tracking-wider" value={viewMode} onChange={(event) => setViewMode(event.target.value as any)}>
              <option value="linear">{t('timeline.linear')}</option>
              <option value="chapter">{t('timeline.chapterGrouping')}</option>
            </select>
          </div>
          <select className="rounded-lg border border-border bg-bg px-3 py-1.5 text-[10px] font-bold text-text-2" value={branchFilter} onChange={(event) => updateParam('branch', event.target.value)} data-testid="timeline-branch-filter">
            <option value="">{t('timeline.branchFilter')}</option>
            {timelineBranches.map((branch) => (
              <option key={branch.id} value={branch.id}>{branch.name}</option>
            ))}
          </select>
          <select className="rounded-lg border border-border bg-bg px-3 py-1.5 text-[10px] font-bold text-text-2" value={characterFilter} onChange={(event) => updateParam('character', event.target.value)} data-testid="timeline-character-filter">
            <option value="">{t('timeline.allCharacters')}</option>
            {characters.map((character) => (
              <option key={character.id} value={character.id}>{character.name}</option>
            ))}
          </select>
          <select className="rounded-lg border border-border bg-bg px-3 py-1.5 text-[10px] font-bold text-text-2" value={locationFilter} onChange={(event) => updateParam('location', event.target.value)} data-testid="timeline-location-filter">
            <option value="">{t('timeline.allLocations')}</option>
            {locationOptions.map((location) => (
              <option key={location.id} value={location.id}>{location.name}</option>
            ))}
          </select>
          <button type="button" className="rounded-lg border border-border px-3 py-1.5 text-[10px] font-bold text-text-2" onClick={clearFilters} data-testid="timeline-clear-filters">
            <FilterX size={12} className="inline mr-2" />{t('timeline.clearFilters')}
          </button>
        </div>

        <div className="ml-auto flex items-center gap-4 bg-bg border border-border rounded-lg px-4 py-1.5 shadow-inner">
          <button className="text-text-3 hover:text-brand" onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}><Minimize2 size={14} /></button>
          <input type="range" min="0.5" max="2" step="0.1" value={zoom} onChange={(event) => setZoom(parseFloat(event.target.value))} className="w-24 h-1 bg-divider rounded-lg appearance-none cursor-pointer accent-brand" />
          <button className="text-text-3 hover:text-brand" onClick={() => setZoom(Math.min(2, zoom + 0.1))}><Maximize2 size={14} /></button>
        </div>
      </div>

      <div className="px-6 py-3 border-b border-border bg-bg-elev-1/60 flex flex-wrap gap-4 text-[10px] font-black uppercase tracking-[0.2em] text-text-3" data-testid="timeline-filter-state">
        {characterFilter && <span>{t('timeline.filteredByCharacter')}: {characters.find((entry) => entry.id === characterFilter)?.name}</span>}
        {locationFilter && <span>{t('timeline.filteredByLocation')}: {locationOptions.find((entry) => entry.id === locationFilter)?.name}</span>}
        {branchFilter && <span>{t('timeline.branchFilter')}: {timelineBranches.find((entry) => entry.id === branchFilter)?.name}</span>}
        {!characterFilter && !locationFilter && !branchFilter && <span>{t('timeline.title')}</span>}
      </div>

      <div className="flex-1 overflow-auto bg-bg custom-scrollbar relative p-10" data-testid="timeline-canvas">
        <div className="absolute inset-0 pointer-events-none opacity-[0.03] select-none" style={{ backgroundImage: `linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)`, backgroundSize: `${40 * zoom}px ${40 * zoom}px` }}></div>

        <div className="relative flex flex-col gap-8 min-h-full" style={{ minWidth: `${1600 * zoom}px` }}>
          {branchRows.map((branch) => {
            const events = visibleEvents.filter((event) => event.branchId === branch.id).sort((a, b) => a.orderIndex - b.orderIndex);
            return (
              <div key={branch.id} className="relative h-52 border border-border bg-bg-elev-1 rounded-2xl flex items-center px-10 group transition-all hover:bg-bg-elev-2 hover:border-border-2 shadow-1" data-testid={`timeline-branch-${branch.id}`} onDragOver={onDragOver} onDrop={(event) => onDrop(event, branch.id, events.length)}>
                <div className="absolute left-6 top-6 flex items-center gap-3 z-20">
                  <div className="w-2.5 h-2.5 rounded-full bg-brand shadow-[0_0_12px_rgba(124,58,237,0.6)]"></div>
                  <div>
                    <span className="text-[11px] font-black text-text-3 uppercase tracking-[0.25em] group-hover:text-brand transition-colors duration-300">{branch.name}</span>
                    {branch.description && <div className="text-[10px] mt-1 text-text-3 normal-case tracking-normal">{branch.description}</div>}
                  </div>
                </div>

                <div className="flex gap-10 items-center ml-24 h-full relative z-10">
                  {events.map((event) => {
                    const isSelected = selectedEntity.id === event.id;
                    return (
                      <div
                        key={event.id}
                        draggable
                        onDragStart={(dragEvent) => dragEvent.dataTransfer.setData('eventId', event.id)}
                        data-testid={`timeline-node-${event.id}`}
                        className={cnLocal('w-72 p-5 rounded-xl border-2 cursor-pointer transition-all relative group/node animate-in zoom-in-95 duration-200', isSelected ? 'bg-bg-elev-2 border-brand shadow-2 ring-1 ring-brand/30' : 'bg-bg border-border hover:border-border-2 hover:bg-bg-elev-2 shadow-1')}
                        style={{ transform: `scale(${0.95 + zoom * 0.05})` }}
                        onClick={() => setSelectedEntity('timeline_event', event.id)}
                      >
                        <div className="flex items-center justify-between mb-3 relative z-10">
                          <div className="flex items-center gap-1.5 text-brand-2"><Clock size={10} /><span className="text-[10px] font-extrabold uppercase tracking-[0.15em]">{event.time || 'T+0'}</span></div>
                          <ChevronRight size={12} className="text-text-3 opacity-0 group-hover/node:opacity-100 transition-opacity" />
                        </div>
                        <div className="text-sm font-bold text-text truncate mb-2 relative z-10 group-hover/node:text-brand transition-colors">{event.title}</div>
                        <p className="text-[11px] text-text-2 line-clamp-2 leading-relaxed opacity-70 relative z-10">{event.summary}</p>
                        <div className="mt-4 pt-3 border-t border-divider flex items-center gap-3 relative z-10 flex-wrap">
                          {getLocationLabel(event) && <div className="flex items-center gap-1 text-[9px] text-text-3 font-bold uppercase tracking-widest truncate"><MapPin size={8} /> {getLocationLabel(event)}</div>}
                          {event.participantCharacterIds.length > 0 && <div className="flex items-center gap-1 text-[9px] text-text-3 font-bold uppercase tracking-widest"><Users size={8} /> {event.participantCharacterIds.length}</div>}
                        </div>
                        {event.linkedSceneIds.length > 0 && (
                          <button
                            type="button"
                            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-[10px] font-black uppercase tracking-widest text-text-2 hover:border-brand"
                            onClick={(clickEvent) => {
                              clickEvent.stopPropagation();
                              setSelectedEntity('scene', event.linkedSceneIds[0]);
                              navigate('/writing/scenes');
                            }}
                            data-testid="timeline-open-scene-btn"
                          >
                            <ArrowRightCircle size={12} /> {t('timeline.jumpToScene')}
                          </button>
                        )}
                      </div>
                    );
                  })}

                  {events.length === 0 && (
                    <div className="flex flex-col items-center justify-center opacity-20 ml-20">
                      <Plus size={32} className="mb-2 text-text-3" />
                      <p className="text-[10px] text-text-3 font-black uppercase tracking-[0.3em] italic">{t('timeline.emptyTrack')}</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');
