import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FilterX,
  GitBranchPlus,
  GitMerge,
  Maximize2,
  Minimize2,
  Plus,
  SplitSquareVertical,
} from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';
import type { TimelineBranch, TimelineEvent } from '../models/project';

const MIN_ZOOM = 0.55;
const MAX_ZOOM = 1.6;
const MAIN_BRANCH_COLOR = '#f59e0b';

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
      setZoom((current) => clamp(current - event.deltaY * 0.0012, MIN_ZOOM, MAX_ZOOM));
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, []);

  const locationOptions = useMemo(() => worldItems.filter((item) => item.type === 'location'), [worldItems]);
  const sortedBranches = useMemo(
    () => timelineBranches.slice().sort((a, b) => a.sortOrder - b.sortOrder),
    [timelineBranches],
  );
  const mainBranch = sortedBranches.find((branch) => !branch.parentBranchId) || sortedBranches[0] || null;

  const visibleBranches = useMemo(() => {
    if (!branchFilter || !mainBranch) return sortedBranches;
    const allowed = new Set<string>([mainBranch.id, branchFilter]);
    sortedBranches.forEach((branch) => {
      if (branch.parentBranchId === branchFilter || branch.id === branchFilter || branch.parentBranchId === mainBranch.id) {
        allowed.add(branch.id);
      }
    });
    return sortedBranches.filter((branch) => allowed.has(branch.id));
  }, [branchFilter, mainBranch, sortedBranches]);

  const visibleBranchIds = new Set(visibleBranches.map((branch) => branch.id));

  const visibleEvents = useMemo(
    () =>
      timelineEvents.filter((event) => {
        if (characterFilter && !event.participantCharacterIds.includes(characterFilter)) return false;
        if (locationFilter && !event.locationIds.includes(locationFilter)) return false;
        if (!branchFilter) return true;
        if (visibleBranchIds.has(event.branchId)) return true;
        if (event.sharedBranchIds?.some((id) => visibleBranchIds.has(id))) return true;
        return visibleBranches.some((branch) => branch.forkEventId === event.id || branch.mergeEventId === event.id);
      }),
    [branchFilter, characterFilter, locationFilter, timelineEvents, visibleBranches, visibleBranchIds],
  );

  const branchRows = useMemo(
    () =>
      visibleBranches.map((branch, index) => ({
        branch,
        y: 160 + index * 200,
      })),
    [visibleBranches],
  );

  const branchYMap = useMemo(() => new Map(branchRows.map((row) => [row.branch.id, row.y])), [branchRows]);
  const eventsByBranch = useMemo(() => {
    const grouped = new Map<string, TimelineEvent[]>();
    visibleEvents.forEach((event) => {
      const bucket = grouped.get(event.branchId) || [];
      bucket.push(event);
      grouped.set(event.branchId, bucket);
    });
    grouped.forEach((bucket) => bucket.sort((a, b) => a.orderIndex - b.orderIndex));
    return grouped;
  }, [visibleEvents]);

  const mainEvents = (mainBranch ? eventsByBranch.get(mainBranch.id) : []) || [];
  const mainEventX = useMemo(() => {
    const map = new Map<string, number>();
    mainEvents.forEach((event, index) => {
      map.set(event.id, 220 + index * 320);
    });
    return map;
  }, [mainEvents]);

  const eventPositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    branchRows.forEach(({ branch, y }) => {
      const branchEvents = eventsByBranch.get(branch.id) || [];
      if (branch.id === mainBranch?.id) {
        branchEvents.forEach((event) => {
          positions.set(event.id, { x: mainEventX.get(event.id) || 220, y });
        });
        return;
      }

      const forkX = mainEventX.get(branch.forkEventId || '') || 220;
      const mergeX = mainEventX.get(branch.mergeEventId || '') || forkX + Math.max(360, branchEvents.length * 240);
      const spread = Math.max(mergeX - forkX - 120, 240);
      branchEvents.forEach((event, index) => {
        const step = spread / (branchEvents.length + 1);
        positions.set(event.id, { x: forkX + step * (index + 1), y });
      });
    });
    return positions;
  }, [branchRows, eventsByBranch, mainBranch?.id, mainEventX]);

  const canvasWidth = Math.max(1800, mainEvents.length * 320 + 540);
  const canvasHeight = Math.max(720, branchRows.length * 220 + 220);

  const handleDropToBranch = (branch: TimelineBranch, draggedEventId: string) => {
    const draggedEvent = timelineEvents.find((entry) => entry.id === draggedEventId);
    if (!draggedEvent) return;
    const isAnchored = timelineBranches.some(
      (entry) => entry.forkEventId === draggedEvent.id || entry.mergeEventId === draggedEvent.id,
    );
    if (isAnchored) {
      setLastActionStatus(t('timeline.dragGuard'));
      return;
    }
    const nextOrderIndex = timelineEvents.filter((entry) => entry.branchId === branch.id).length;
    updateTimelineEvent({
      ...draggedEvent,
      branchId: branch.id,
      orderIndex: draggedEvent.branchId === branch.id ? draggedEvent.orderIndex : nextOrderIndex,
    });
    setLastActionStatus(`${t('timeline.branchMoved')}: ${branch.name}`);
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg">
      <div className="flex items-center gap-4 border-b border-border bg-bg-elev-1 px-6 py-3" data-testid="timeline-toolbar">
        <button
          type="button"
          data-testid="add-event-btn"
          className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white"
          onClick={() => setSelectedEntity('timeline_event', 'new')}
        >
          <Plus size={13} className="mr-2 inline" />
          {t('timeline.addEvent')}
        </button>
        <button
          type="button"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
          onClick={() => {
            const parent = mainBranch?.id || 'branch_main';
            addTimelineBranch({
              id: `branch_${Date.now()}`,
              name: 'New Branch',
              description: 'Branch from current narrative line.',
              parentBranchId: parent,
              forkEventId: mainEvents[0]?.id || null,
              mergeEventId: mainEvents[mainEvents.length - 1]?.id || null,
              color: '#38bdf8',
              sortOrder: timelineBranches.length,
              collapsed: false,
            });
            setLastActionStatus('Branch created');
          }}
        >
          <GitBranchPlus size={13} className="mr-2 inline" />
          New Branch
        </button>
        <select
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={branchFilter}
          onChange={(event) => updateParam(searchParams, setSearchParams, 'branch', event.target.value)}
          data-testid="timeline-branch-filter"
        >
          <option value="">{t('timeline.branchFilter')}</option>
          {timelineBranches.map((branch) => (
            <option key={branch.id} value={branch.id}>
              {branch.name}
            </option>
          ))}
        </select>
        <select
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={characterFilter}
          onChange={(event) => updateParam(searchParams, setSearchParams, 'character', event.target.value)}
          data-testid="timeline-character-filter"
        >
          <option value="">{t('timeline.allCharacters')}</option>
          {characters.map((character) => (
            <option key={character.id} value={character.id}>
              {character.name}
            </option>
          ))}
        </select>
        <select
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={locationFilter}
          onChange={(event) => updateParam(searchParams, setSearchParams, 'location', event.target.value)}
          data-testid="timeline-location-filter"
        >
          <option value="">{t('timeline.allLocations')}</option>
          {locationOptions.map((location) => (
            <option key={location.id} value={location.id}>
              {location.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="timeline-clear-filters"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
          onClick={() => setSearchParams({})}
        >
          <FilterX size={13} className="mr-2 inline" />
          {t('timeline.clearFilters')}
        </button>
        <div className="ml-auto flex items-center gap-3 rounded-full border border-border bg-bg px-4 py-2">
          <button type="button" className="text-text-3 hover:text-brand" onClick={() => setZoom((current) => clamp(current - 0.1, MIN_ZOOM, MAX_ZOOM))}>
            <Minimize2 size={14} />
          </button>
          <input type="range" min={MIN_ZOOM} max={MAX_ZOOM} step="0.05" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} className="w-24 accent-brand" />
          <div className="min-w-[72px] text-center text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{Math.round(zoom * 100)}%</div>
          <button type="button" className="text-text-3 hover:text-brand" onClick={() => setZoom((current) => clamp(current + 0.1, MIN_ZOOM, MAX_ZOOM))}>
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      <div className="border-b border-border bg-bg-elev-1/70 px-6 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3" data-testid="timeline-filter-state">
        {characterFilter && <span>{t('timeline.filteredByCharacter')}: {characters.find((entry) => entry.id === characterFilter)?.name} </span>}
        {locationFilter && <span>{t('timeline.filteredByLocation')}: {locationOptions.find((entry) => entry.id === locationFilter)?.name} </span>}
        {branchFilter && <span>{t('timeline.branchFilter')}: {timelineBranches.find((entry) => entry.id === branchFilter)?.name}</span>}
        {!characterFilter && !locationFilter && !branchFilter && <span>{t('timeline.title')}</span>}
      </div>

      <div className="min-h-0 flex flex-1">
        <div
          ref={canvasRef}
          className="relative flex-1 overflow-hidden bg-bg"
          data-testid="timeline-canvas"
          onMouseDown={(event) => {
            if ((event.target as HTMLElement).closest('[data-timeline-node="true"]')) return;
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
          }}
        >
          <div
            className="absolute inset-0 opacity-[0.04]"
            style={{
              backgroundImage:
                'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)',
              backgroundSize: `${48 * zoom}px ${48 * zoom}px`,
            }}
          />
          <div
            className="absolute left-0 top-0"
            style={{
              width: canvasWidth,
              height: canvasHeight,
              transform: `translate(${panX}px, ${panY}px) scale(${zoom})`,
              transformOrigin: '0 0',
            }}
          >
            <svg className="absolute inset-0 h-full w-full overflow-visible">
              {mainBranch && (
                <line
                  x1={140}
                  y1={branchYMap.get(mainBranch.id) || 0}
                  x2={canvasWidth - 120}
                  y2={branchYMap.get(mainBranch.id) || 0}
                  stroke="rgba(245, 158, 11, 0.35)"
                  strokeWidth={4}
                  strokeLinecap="round"
                  data-testid="timeline-mainline"
                />
              )}
              {branchRows
                .filter(({ branch }) => branch.id !== mainBranch?.id)
                .map(({ branch, y }) => {
                  const parentY = branchYMap.get(branch.parentBranchId || '') || branchYMap.get(mainBranch?.id || '') || y;
                  const forkX = mainEventX.get(branch.forkEventId || '') || 220;
                  const mergeX = mainEventX.get(branch.mergeEventId || '') || forkX + 360;
                  const color = branch.color || MAIN_BRANCH_COLOR;
                  return (
                    <g key={branch.id}>
                      <path
                        d={`M ${forkX} ${parentY} C ${forkX + 60} ${parentY}, ${forkX + 40} ${y}, ${forkX + 120} ${y}`}
                        fill="none"
                        stroke={hexToRgba(color, 0.75)}
                        strokeWidth={3}
                        strokeLinecap="round"
                      />
                      <line
                        x1={forkX + 120}
                        y1={y}
                        x2={mergeX - 120}
                        y2={y}
                        stroke={hexToRgba(color, 0.65)}
                        strokeWidth={3}
                        strokeLinecap="round"
                      />
                      <path
                        d={`M ${mergeX - 120} ${y} C ${mergeX - 50} ${y}, ${mergeX - 60} ${parentY}, ${mergeX} ${parentY}`}
                        fill="none"
                        stroke={hexToRgba(color, 0.75)}
                        strokeWidth={3}
                        strokeLinecap="round"
                      />
                    </g>
                  );
                })}
            </svg>

            {branchRows.map(({ branch, y }) => {
              const isMain = branch.id === mainBranch?.id;
              const branchEvents = eventsByBranch.get(branch.id) || [];
              const forkX = mainEventX.get(branch.forkEventId || '') || 220;
              const mergeX = mainEventX.get(branch.mergeEventId || '') || forkX + 360;
              return (
                <div
                  key={branch.id}
                  className="absolute left-0 right-0"
                  style={{ top: y - 78, height: 156 }}
                  data-testid={`timeline-branch-${branch.id}`}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    openContextMenu({
                      x: event.clientX,
                      y: event.clientY,
                      items: [{ id: 'focus-branch', label: 'Focus Branch', action: () => updateParam(searchParams, setSearchParams, 'branch', branch.id) }],
                    });
                  }}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => {
                    const draggedId = event.dataTransfer.getData('eventId');
                    handleDropToBranch(branch, draggedId);
                  }}
                >
                  <div className="absolute left-10 top-4 flex items-center gap-3">
                    <div className="h-3 w-3 rounded-full shadow-[0_0_18px_rgba(242,200,121,0.5)]" style={{ background: branch.color || MAIN_BRANCH_COLOR }} />
                    <div>
                      <div className="text-[11px] font-black uppercase tracking-[0.3em] text-text-2">{branch.name}</div>
                      <div className="mt-1 text-sm text-text-3">{branch.description}</div>
                    </div>
                    {isMain && (
                      <span className="rounded-full border border-amber/30 bg-amber/10 px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-amber">
                        {t('timeline.mainline')}
                      </span>
                    )}
                  </div>

                  {!isMain && (
                    <>
                      <div
                        className="absolute -translate-x-1/2 rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-sky-300"
                        style={{ left: forkX, top: 20 }}
                        data-testid={`timeline-fork-${branch.id}`}
                      >
                        <SplitSquareVertical size={12} className="mr-2 inline" />
                        {t('timeline.fork')}
                      </div>
                      <div
                        className="absolute -translate-x-1/2 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-emerald-300"
                        style={{ left: mergeX, top: 20 }}
                        data-testid={`timeline-merge-${branch.id}`}
                      >
                        <GitMerge size={12} className="mr-2 inline" />
                        {t('timeline.merge')}
                      </div>
                    </>
                  )}

                  {branchEvents.map((event) => {
                    const position = eventPositions.get(event.id);
                    if (!position) return null;
                    const isSelected = selectedEntity.id === event.id;
                    const isShared = event.sharedBranchIds?.length;
                    const eventTone = getEventTone(event);
                    return (
                      <div
                        key={`${branch.id}-${event.id}`}
                        className="absolute -translate-x-1/2 -translate-y-1/2"
                        style={{ left: position.x, top: y }}
                      >
                        <button
                          type="button"
                          data-testid={`timeline-node-${event.id}`}
                          data-timeline-node="true"
                          draggable
                          onDragStart={(dragEvent) => dragEvent.dataTransfer.setData('eventId', event.id)}
                          className={cn(
                            'group relative flex h-7 w-7 items-center justify-center rounded-full border-2 shadow-xl transition-all',
                            isSelected
                              ? 'scale-125 border-brand shadow-[0_0_30px_rgba(201,131,40,0.45)]'
                              : 'border-white/20 hover:scale-110',
                          )}
                          style={{
                            background: eventTone.fill,
                            borderColor: isSelected ? MAIN_BRANCH_COLOR : eventTone.border,
                          }}
                          onClick={() => setSelectedEntity('timeline_event', event.id)}
                          onMouseEnter={() => setHoveredEventId(event.id)}
                          onMouseLeave={() => setHoveredEventId((current) => (current === event.id ? null : current))}
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
                          role="button"
                          tabIndex={0}
                          onKeyDown={(keyboardEvent) => {
                            if (keyboardEvent.key === 'Enter' || keyboardEvent.key === ' ') {
                              keyboardEvent.preventDefault();
                              setSelectedEntity('timeline_event', event.id);
                            }
                          }}
                        >
                          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-950">{event.orderIndex + 1}</span>
                        </button>
                        <div className="pointer-events-none absolute left-1/2 top-[130%] min-w-max -translate-x-1/2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                          {event.time}
                        </div>
                        {hoveredEventId === event.id && (
                          <div className="absolute left-1/2 top-[160%] z-20 w-80 -translate-x-1/2 rounded-2xl border border-border bg-slate-950/95 p-4 text-left shadow-[0_24px_50px_rgba(0,0,0,0.5)]">
                            <div className="flex items-center justify-between gap-3">
                              <div className="text-sm font-black text-text">{event.title}</div>
                              <div className="rounded-full border border-border px-2 py-1 text-[9px] font-black uppercase tracking-[0.18em] text-text-3">
                                {branch.name}
                              </div>
                            </div>
                            <div className="mt-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{event.time}</div>
                            <div className="mt-2 text-xs leading-relaxed text-text-2">{event.summary}</div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {isShared ? (
                                <span className="rounded-full border border-amber/30 bg-amber/10 px-2 py-1 text-[9px] font-black uppercase tracking-[0.18em] text-amber">
                                  shared
                                </span>
                              ) : null}
                              {event.linkedSceneIds.length > 0 && (
                                <span className="rounded-full border border-border bg-bg px-2 py-1 text-[9px] font-black uppercase tracking-[0.18em] text-text-3">
                                  {t('timeline.jumpToScene')}
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        <aside className="w-[340px] border-l border-border bg-bg-elev-1" data-testid="timeline-linear-inspector">
          <div className="border-b border-border bg-bg-elev-2 px-5 py-4">
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('timeline.linearInspector')}</div>
            <div className="mt-2 text-sm font-black text-text">Fork / merge aware event list</div>
          </div>
          <div className="h-full overflow-y-auto custom-scrollbar p-4">
            <div className="space-y-3">
              {visibleEvents
                .slice()
                .sort((a, b) => {
                  const ax = eventPositions.get(a.id)?.x || 0;
                  const bx = eventPositions.get(b.id)?.x || 0;
                  return ax - bx;
                })
                .map((event) => {
                  const branch = timelineBranches.find((entry) => entry.id === event.branchId);
                  const isSelected = selectedEntity.id === event.id;
                  return (
                    <button
                      key={event.id}
                      type="button"
                      className={cn(
                        'w-full rounded-2xl border p-4 text-left',
                        isSelected ? 'border-brand bg-selected' : 'border-border bg-bg hover:border-brand',
                      )}
                      onClick={() => setSelectedEntity('timeline_event', event.id)}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-black text-text">{event.title}</div>
                        <div className="rounded-full border border-border px-2 py-0.5 text-[9px] uppercase tracking-[0.2em] text-text-3">
                          {branch?.name || event.branchId}
                        </div>
                      </div>
                      <div className="mt-2 text-xs leading-relaxed text-text-2">{event.summary}</div>
                      <div className="mt-2 text-[10px] uppercase tracking-[0.2em] text-text-3">{event.time}</div>
                    </button>
                  );
                })}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
};

const updateParam = (
  current: URLSearchParams,
  setSearchParams: ReturnType<typeof useSearchParams>[1],
  key: string,
  value: string,
) => {
  const next = new URLSearchParams(current);
  if (value) next.set(key, value);
  else next.delete(key);
  setSearchParams(next);
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const hexToRgba = (hex: string, alpha: number) => {
  const normalized = hex.replace('#', '');
  const digits = normalized.length === 3
    ? normalized.split('').map((value) => `${value}${value}`).join('')
    : normalized;
  const int = Number.parseInt(digits, 16);
  const r = (int >> 16) & 255;
  const g = (int >> 8) & 255;
  const b = int & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

const getEventTone = (event: TimelineEvent) => {
  if (event.tags.includes('climax') || event.tags.includes('merge')) {
    return { fill: 'rgba(239, 68, 68, 0.92)', border: 'rgba(248, 113, 113, 0.8)' };
  }
  if (event.tags.includes('artifact') || event.tags.includes('intel')) {
    return { fill: 'rgba(245, 158, 11, 0.92)', border: 'rgba(251, 191, 36, 0.8)' };
  }
  if (event.tags.includes('politics')) {
    return { fill: 'rgba(34, 197, 94, 0.92)', border: 'rgba(74, 222, 128, 0.8)' };
  }
  return { fill: 'rgba(59, 130, 246, 0.92)', border: 'rgba(96, 165, 250, 0.8)' };
};
