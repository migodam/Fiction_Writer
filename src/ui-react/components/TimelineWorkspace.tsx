import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { GitBranchPlus, GitMerge, Maximize2, Minimize2, Plus, Route, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import type { TimelineBranch, TimelineEvent } from '../models/project';
import { useI18n } from '../i18n';

const MIN_ZOOM = 0.6;
const MAX_ZOOM = 1.5;
const MAIN_BRANCH_ID = 'branch_main';

export const TimelineWorkspace = () => {
  const {
    timelineEvents,
    timelineBranches,
    characters,
    worldItems,
    scenes,
    addTimelineEvent,
    updateTimelineEvent,
    deleteTimelineEvent,
    updateTimelineBranch,
    createTimelineBranch,
    moveTimelineEvent,
    setTimelineBranchGeometry,
  } = useProjectStore();
  const { setLastActionStatus, openContextMenu } = useUIStore();
  const { locale, t } = useI18n();
  const zh = locale === 'zh-CN';
  const [searchParams] = useSearchParams();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hoveredEventId, setHoveredEventId] = useState<string | null>(null);
  const [activeBranchId, setActiveBranchId] = useState<string>(timelineBranches[0]?.id || MAIN_BRANCH_ID);
  const [activeEventId, setActiveEventId] = useState<string | null>(timelineEvents[0]?.id || null);
  const [characterFilter, setCharacterFilter] = useState(searchParams.get('character') || '');
  const [locationFilter, setLocationFilter] = useState(searchParams.get('location') || '');
  const [eventModalId, setEventModalId] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [dragEventId, setDragEventId] = useState<string | null>(null);
  const [dragPreview, setDragPreview] = useState<{ x: number; y: number } | null>(null);
  const [branchGeometryId, setBranchGeometryId] = useState<string | null>(null);

  const filteredEvents = useMemo(
    () =>
      timelineEvents.filter((event) => {
        if (characterFilter && !event.participantCharacterIds.includes(characterFilter)) return false;
        if (locationFilter && !event.locationIds.includes(locationFilter)) return false;
        return true;
      }),
    [characterFilter, locationFilter, timelineEvents],
  );

  const sortedBranches = useMemo(() => timelineBranches.slice().sort((a, b) => a.sortOrder - b.sortOrder), [timelineBranches]);

  const branchMap = useMemo(() => new Map(sortedBranches.map((branch) => [branch.id, branch])), [sortedBranches]);

  const branchEventsMap = useMemo(() => {
    const map = new Map<string, TimelineEvent[]>();
    filteredEvents.forEach((event) => {
      const bucket = map.get(event.branchId) || [];
      bucket.push(event);
      map.set(event.branchId, bucket);
    });
    map.forEach((items) => items.sort((a, b) => a.orderIndex - b.orderIndex));
    return map;
  }, [filteredEvents]);

  const mainBranchEvents = branchEventsMap.get(MAIN_BRANCH_ID) || [];
  const mainPositions = new Map<string, number>();
  mainBranchEvents.forEach((event, index) => mainPositions.set(event.id, 180 + index * 180));

  const branchY = (branch: TimelineBranch) => 220 + (branch.geometry?.laneOffset || 0);
  const slotX = (branchId: string, slot: number) => {
    const branch = branchMap.get(branchId);
    if (!branch || branch.id === MAIN_BRANCH_ID || branch.mode === 'independent') {
      return 180 + slot * 180;
    }
    const anchorX = mainPositions.get(branch.startAnchor?.eventId || branch.forkEventId || '') || 180;
    return anchorX + 140 + slot * 150;
  };

  const eventPositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    sortedBranches.forEach((branch) => {
      const events = branchEventsMap.get(branch.id) || [];
      const mergeX = branch.mergeEventId ? mainPositions.get(branch.mergeEventId) : undefined;
      events.forEach((event, index) => {
        let x = slotX(branch.id, index);
        if (mergeX && branch.id !== MAIN_BRANCH_ID && events.length > 0) {
          const anchorX = mainPositions.get(branch.startAnchor?.eventId || branch.forkEventId || '') || 180;
          const span = Math.max(mergeX - anchorX - 160, 180);
          x = anchorX + 100 + ((index + 1) * span) / (events.length + 1);
        }
        positions.set(event.id, { x, y: branchY(branch) });
      });
    });
    return positions;
  }, [branchEventsMap, mainPositions, sortedBranches]);

  const activeEvent = timelineEvents.find((entry) => entry.id === activeEventId) || null;
  const activeBranch = branchMap.get(activeBranchId) || sortedBranches[0] || null;
  const eventModal = timelineEvents.find((entry) => entry.id === eventModalId) || null;

  useEffect(() => {
    const eventId = searchParams.get('event');
    const characterId = searchParams.get('character');
    const locationId = searchParams.get('location');
    if (eventId) {
      setActiveEventId(eventId);
      setEventModalId(eventId);
    }
    if (characterId !== null) {
      setCharacterFilter(characterId);
    }
    if (locationId !== null) {
      setLocationFilter(locationId);
    }
  }, [searchParams]);

  const beginPan = (event: React.MouseEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('[data-event-dot="true"]') || (event.target as HTMLElement).closest('[data-branch-handle="true"]')) return;
    const start = { x: event.clientX, y: event.clientY };
    const initial = { ...pan };
    const onMove = (moveEvent: MouseEvent) => setPan({ x: initial.x + (moveEvent.clientX - start.x), y: initial.y + (moveEvent.clientY - start.y) });
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startEventDrag = (eventId: string, event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const target = timelineEvents.find((entry) => entry.id === eventId);
    if (!target) return;
    const initial = eventPositions.get(eventId);
    if (!initial) return;
    setDragEventId(eventId);
    setActiveEventId(eventId);
    setDragPreview(initial);
    const bounds = canvasRef.current?.getBoundingClientRect();

    const onMove = (moveEvent: MouseEvent) => {
      if (!bounds) return;
      const x = (moveEvent.clientX - bounds.left - pan.x) / zoom;
      const y = (moveEvent.clientY - bounds.top - pan.y) / zoom;
      setDragPreview({ x, y });
    };

    const onUp = (moveEvent: MouseEvent) => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      setDragEventId(null);
      const boundsNow = canvasRef.current?.getBoundingClientRect();
      if (!boundsNow) {
        setDragPreview(null);
        return;
      }
      const x = (moveEvent.clientX - boundsNow.left - pan.x) / zoom;
      const y = (moveEvent.clientY - boundsNow.top - pan.y) / zoom;
      const targetBranch = sortedBranches.reduce<{ branch: TimelineBranch | null; distance: number }>(
        (best, branch) => {
          const distance = Math.abs(y - branchY(branch));
          return distance < best.distance ? { branch, distance } : best;
        },
        { branch: null, distance: Number.POSITIVE_INFINITY },
      ).branch;
      if (targetBranch) {
        const targetEvents = (branchEventsMap.get(targetBranch.id) || []).filter((entry) => entry.id !== eventId);
        const targetSlot = targetEvents.filter((entry) => (eventPositions.get(entry.id)?.x || 0) < x).length;
        moveTimelineEvent(eventId, targetBranch.id, targetSlot);
        setActiveBranchId(targetBranch.id);
        setLastActionStatus(zh ? '事件已重新定位' : 'Event moved');
      }
      setDragPreview(null);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startBranchGeometryDrag = (branchId: string, event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setBranchGeometryId(branchId);
    const branch = branchMap.get(branchId);
    if (!branch) return;
    const initialLane = branch.geometry?.laneOffset || 0;
    const startY = event.clientY;
    const onMove = (moveEvent: MouseEvent) => {
      setTimelineBranchGeometry(branchId, {
        ...(branch.geometry || { laneOffset: 0, bend: 0.25, thickness: 1 }),
        laneOffset: initialLane + (moveEvent.clientY - startY) / zoom,
      });
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      setBranchGeometryId(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const addEventAfterSelection = () => {
    setCreateModalOpen(true);
  };

  const addIndependentBranch = () => {
    const branchId = createTimelineBranch('independent', null);
    if (!branchId) return;
    setActiveBranchId(branchId);
    setLastActionStatus(zh ? '已创建独立分支' : 'Independent branch created');
  };

  const addForkBranch = () => {
    if (!activeEvent) return;
    const branchId = createTimelineBranch('forked', { branchId: activeEvent.branchId, eventId: activeEvent.id });
    if (!branchId) return;
    setActiveBranchId(branchId);
    setLastActionStatus(zh ? '已从当前事件分叉' : 'Branch forked from selected event');
  };

  const setBranchEndMode = (endMode: 'open' | 'merge' | 'closed') => {
    if (!activeBranch) return;
    updateTimelineBranch({
      ...activeBranch,
      endMode,
      mergeTargetBranchId: endMode === 'merge' ? MAIN_BRANCH_ID : activeBranch.mergeTargetBranchId || null,
      mergeEventId: endMode === 'merge' ? mainBranchEvents[mainBranchEvents.length - 1]?.id || activeBranch.mergeEventId || null : activeBranch.mergeEventId || null,
    });
    setLastActionStatus(zh ? '分支结束方式已更新' : 'Branch end mode updated');
  };

  const canvasWidth = Math.max(1800, (mainBranchEvents.length + 4) * 180);
  const canvasHeight = 980;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg">
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-bg-elev-1 px-6 py-3" data-testid="timeline-toolbar">
        <button type="button" data-testid="add-event-btn" className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white" onClick={addEventAfterSelection}>
          <Plus size={13} className="mr-2 inline" />
          {zh ? '新增事件' : 'Add Event'}
        </button>
        <button type="button" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2" onClick={addIndependentBranch}>
          <Route size={13} className="mr-2 inline" />
          {zh ? '独立分支' : 'New Independent Branch'}
        </button>
        <button type="button" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2" onClick={addForkBranch} disabled={!activeEvent}>
          <GitBranchPlus size={13} className="mr-2 inline" />
          {zh ? '从当前事件分叉' : 'Fork from Event'}
        </button>
        <select className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2" value={activeBranchId} onChange={(event) => setActiveBranchId(event.target.value)}>
          {sortedBranches.map((branch) => (
            <option key={branch.id} value={branch.id}>
              {branch.name}
            </option>
          ))}
        </select>
        <select className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2" value={characterFilter} onChange={(event) => setCharacterFilter(event.target.value)}>
          <option value="">{zh ? '全部人物' : 'All Characters'}</option>
          {characters.map((character) => (
            <option key={character.id} value={character.id}>
              {character.name}
            </option>
          ))}
        </select>
        <select className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2" value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
          <option value="">{zh ? '全部地点' : 'All Locations'}</option>
          {worldItems.filter((entry) => entry.type === 'location').map((location) => (
            <option key={location.id} value={location.id}>
              {location.name}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-3 rounded-full border border-border bg-bg px-4 py-2">
          <button type="button" className="text-text-3 hover:text-brand" onClick={() => setZoom((current) => Math.max(MIN_ZOOM, current - 0.1))}>
            <Minimize2 size={14} />
          </button>
          <div className="min-w-[72px] text-center text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{Math.round(zoom * 100)}%</div>
          <button type="button" className="text-text-3 hover:text-brand" onClick={() => setZoom((current) => Math.min(MAX_ZOOM, current + 0.1))}>
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 border-b border-border bg-bg-elev-1/70 px-6 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">
        <span>{zh ? '分支结束方式' : 'Branch End Mode'}:</span>
        {(['open', 'closed', 'merge'] as const).map((mode) => (
          <button key={mode} type="button" className={cn('rounded-full border px-3 py-1', activeBranch?.endMode === mode ? 'border-brand bg-active text-text' : 'border-border text-text-3')} onClick={() => setBranchEndMode(mode)}>
            {mode === 'open' ? (zh ? '开放' : 'Open') : mode === 'closed' ? (zh ? '独立结束' : 'Closed') : (zh ? '合流' : 'Merge')}
          </button>
        ))}
      </div>

      <div ref={canvasRef} className="relative min-h-0 flex-1 overflow-hidden bg-bg" data-testid="timeline-canvas" onMouseDown={beginPan}>
        <div className="absolute inset-0 opacity-[0.04]" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.8) 1px, transparent 1px)', backgroundSize: `${48 * zoom}px ${48 * zoom}px` }} />
        <div className="absolute left-0 top-0" style={{ width: canvasWidth, height: canvasHeight, transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: '0 0' }}>
          <svg className="absolute inset-0 h-full w-full overflow-visible">
            {sortedBranches.map((branch) => {
              const y = branchY(branch);
              const mainY = branchY(branchMap.get(MAIN_BRANCH_ID) || branch);
              if (branch.id === MAIN_BRANCH_ID) {
                return <line key={branch.id} x1={120} y1={y} x2={canvasWidth - 120} y2={y} stroke="rgba(245,158,11,0.45)" strokeWidth={5} strokeLinecap="round" />;
              }
              const anchorX = mainPositions.get(branch.startAnchor?.eventId || branch.forkEventId || '') || 180;
              const endX = branch.endMode === 'merge' ? (mainPositions.get(branch.mergeEventId || '') || anchorX + 420) : anchorX + Math.max(((branchEventsMap.get(branch.id) || []).length + 1) * 150, 260);
              const bend = 70 + (branch.geometry?.bend || 0.25) * 120;
              return (
                <g key={branch.id}>
                  <path d={`M ${anchorX} ${mainY} C ${anchorX + bend} ${mainY}, ${anchorX + bend} ${y}, ${anchorX + 120} ${y}`} fill="none" stroke={branch.color || '#38bdf8'} strokeWidth={3} opacity={0.85} />
                  <line x1={anchorX + 120} y1={y} x2={endX - (branch.endMode === 'merge' ? 120 : 0)} y2={y} stroke={branch.color || '#38bdf8'} strokeWidth={3} opacity={0.75} />
                  {branch.endMode === 'merge' ? (
                    <path d={`M ${endX - 120} ${y} C ${endX - bend} ${y}, ${endX - bend} ${mainY}, ${endX} ${mainY}`} fill="none" stroke={branch.color || '#38bdf8'} strokeWidth={3} opacity={0.85} />
                  ) : null}
                </g>
              );
            })}
          </svg>

          {sortedBranches.map((branch) => {
            const y = branchY(branch);
            const branchEvents = branchEventsMap.get(branch.id) || [];
            return (
              <div key={branch.id} className="absolute left-0 right-0" style={{ top: y - 90, height: 180 }}>
                <div className="absolute left-8 top-4 flex items-center gap-3">
                  <button
                    type="button"
                    data-branch-handle="true"
                    className={cn('h-4 w-4 rounded-full border-2 shadow-[0_0_18px_rgba(242,200,121,0.5)]', branchGeometryId === branch.id && 'scale-125')}
                    style={{ background: branch.color || '#f59e0b', borderColor: '#fff3' }}
                    onMouseDown={(event) => startBranchGeometryDrag(branch.id, event)}
                  />
                  <div>
                    <div className="text-[11px] font-black uppercase tracking-[0.3em] text-text-2">{branch.name}</div>
                    <div className="mt-1 text-sm text-text-3">{branch.description}</div>
                  </div>
                  <span className="rounded-full border border-border bg-bg px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{branch.mode}</span>
                </div>

                {branchEvents.map((event) => {
                  const position = dragEventId === event.id && dragPreview ? dragPreview : eventPositions.get(event.id);
                  if (!position) return null;
                  const isActive = activeEventId === event.id;
                  return (
                    <div key={event.id} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: position.x, top: position.y }}>
                      <button
                        type="button"
                        data-event-dot="true"
                        data-testid={`timeline-node-${event.id}`}
                        className={cn('relative h-7 w-7 rounded-full border-2 transition-all', isActive ? 'scale-125 border-brand shadow-[0_0_28px_rgba(245,158,11,0.45)]' : 'border-white/20 hover:scale-110')}
                        style={{ background: colorForEvent(event), borderColor: isActive ? '#f59e0b' : 'rgba(255,255,255,0.2)' }}
                        onMouseDown={(mouseEvent) => startEventDrag(event.id, mouseEvent)}
                        onClick={() => {
                          setActiveEventId(event.id);
                          setEventModalId(event.id);
                        }}
                        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); openContextMenu({ x: e.clientX, y: e.clientY, items: [{ id: 'delete', label: t('common.delete'), action: () => { deleteTimelineEvent(event.id); if (activeEventId === event.id) setActiveEventId(null); if (eventModalId === event.id) setEventModalId(null); setLastActionStatus('Event deleted'); }, destructive: true }] }); }}
                        onMouseEnter={() => setHoveredEventId(event.id)}
                        onMouseLeave={() => setHoveredEventId((current) => (current === event.id ? null : current))}
                      />
                      {hoveredEventId === event.id && (
                        <div className="absolute left-1/2 top-[145%] z-20 w-72 -translate-x-1/2 rounded-2xl border border-border bg-slate-950/95 p-4 text-left shadow-[0_24px_50px_rgba(0,0,0,0.5)]">
                          <div className="text-sm font-black text-text">{event.title}</div>
                          <div className="mt-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{event.time}</div>
                          <div className="mt-2 text-xs leading-relaxed text-text-2">{event.summary}</div>
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

      {eventModal && (
        <EventModal
          event={eventModal}
          branch={branchMap.get(eventModal.branchId) || null}
          scenes={scenes.filter((scene) => eventModal.linkedSceneIds.includes(scene.id))}
          characters={characters.filter((character) => eventModal.participantCharacterIds.includes(character.id))}
          worldItems={worldItems.filter((item) => eventModal.locationIds.includes(item.id) || eventModal.linkedWorldItemIds.includes(item.id))}
          updateEvent={updateTimelineEvent}
          onSaved={() => setLastActionStatus(zh ? '已保存' : 'Saved')}
          close={() => setEventModalId(null)}
          zh={zh}
        />
      )}
      {createModalOpen && (
        <CreateEventModal
          defaultBranchId={activeEvent?.branchId || activeBranch?.id || MAIN_BRANCH_ID}
          defaultSlot={activeEvent ? (branchEventsMap.get(activeEvent.branchId) || []).slice().sort((a, b) => a.orderIndex - b.orderIndex).findIndex((entry) => entry.id === activeEvent.id) + 1 : (branchEventsMap.get(activeBranch?.id || MAIN_BRANCH_ID) || []).length}
          addEvent={addTimelineEvent}
          moveEvent={moveTimelineEvent}
          onCreated={(id) => { setActiveEventId(id); setEventModalId(id); setLastActionStatus(zh ? '事件已创建' : 'Event created'); }}
          close={() => setCreateModalOpen(false)}
          zh={zh}
        />
      )}
    </div>
  );
};

const EventModal = ({
  event,
  branch,
  scenes,
  characters,
  worldItems,
  updateEvent,
  onSaved,
  close,
  zh,
}: {
  event: TimelineEvent;
  branch: TimelineBranch | null;
  scenes: ReturnType<typeof useProjectStore.getState>['scenes'];
  characters: ReturnType<typeof useProjectStore.getState>['characters'];
  worldItems: ReturnType<typeof useProjectStore.getState>['worldItems'];
  updateEvent: (event: TimelineEvent) => void;
  onSaved: () => void;
  close: () => void;
  zh: boolean;
}) => {
  const [draft, setDraft] = useState(event);
  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/60 p-6">
      <div className="max-h-[88vh] w-full max-w-3xl overflow-hidden rounded-[32px] border border-border bg-bg-elev-1 shadow-2">
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '事件详情' : 'Event Detail'}</div>
            <div className="mt-1 text-lg font-black text-text">{draft.title}</div>
          </div>
          <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={close}>
            <X size={16} />
          </button>
        </div>
        <div className="max-h-[calc(88vh-72px)] overflow-y-auto custom-scrollbar p-6">
          <div className="grid gap-4">
            <input data-testid="event-title-input" className="rounded-2xl border border-border bg-bg px-4 py-3 text-lg font-black outline-none" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            <textarea data-testid="event-summary-input" className="h-32 rounded-3xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2 outline-none" value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} />
            <input className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" value={draft.time || ''} onChange={(e) => setDraft({ ...draft, time: e.target.value })} placeholder={zh ? '时间标签' : 'Time label'} />
            <div className="grid gap-4 md:grid-cols-3">
              <InfoBlock label={zh ? '分支' : 'Branch'} value={branch?.name || draft.branchId} />
              <InfoBlock label={zh ? '人物' : 'Characters'} value={characters.map((entry) => entry.name).join(', ') || (zh ? '无' : 'None')} />
              <InfoBlock label={zh ? '地点 / 世界' : 'World'} value={worldItems.map((entry) => entry.name).join(', ') || (zh ? '无' : 'None')} />
            </div>
            <div className="rounded-3xl border border-border bg-bg-elev-1 p-5">
              <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '关联场景' : 'Linked Scenes'}</div>
              <div className="space-y-2">
                {scenes.map((scene) => (
                  <div key={scene.id} className="rounded-2xl border border-border bg-bg px-4 py-3 text-sm text-text-2">
                    {scene.title}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button type="button" className="rounded-xl border border-border px-5 py-3 text-sm text-text-2" onClick={close}>{zh ? '取消' : 'Cancel'}</button>
              <button type="button" data-testid="inspector-save" className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white" onClick={() => { updateEvent(draft); onSaved(); close(); }}>
                {zh ? '保存事件' : 'Save Event'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const CreateEventModal = ({
  defaultBranchId,
  defaultSlot,
  addEvent,
  moveEvent,
  onCreated,
  close,
  zh,
}: {
  defaultBranchId: string;
  defaultSlot: number;
  addEvent: (event: TimelineEvent) => void;
  moveEvent: (eventId: string, branchId: string, slot: number) => void;
  onCreated: (id: string) => void;
  close: () => void;
  zh: boolean;
}) => {
  const [title, setTitle] = useState(zh ? '新事件' : 'New Event');
  const [summary, setSummary] = useState('');
  const [time, setTime] = useState(zh ? '待定' : 'TBD');
  const [importance, setImportance] = useState<TimelineEvent['importance']>('medium');

  const handleSave = () => {
    const newEvent: TimelineEvent = {
      id: `event_${Date.now()}`,
      title,
      summary,
      time,
      branchId: defaultBranchId,
      orderIndex: defaultSlot,
      locationIds: [],
      participantCharacterIds: [],
      linkedSceneIds: [],
      linkedWorldItemIds: [],
      tags: [],
      sharedBranchIds: [],
      importance,
      colorToken: 'sky',
      layoutLock: false,
      modalStateHints: [],
    };
    addEvent(newEvent);
    moveEvent(newEvent.id, defaultBranchId, defaultSlot);
    onCreated(newEvent.id);
    close();
  };

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/60 p-6">
      <div className="w-full max-w-lg overflow-hidden rounded-[32px] border border-border bg-bg-elev-1 shadow-2">
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '新增事件' : 'New Event'}</div>
            <div className="mt-1 text-lg font-black text-text">{zh ? '配置事件' : 'Configure Event'}</div>
          </div>
          <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={close}>
            <X size={16} />
          </button>
        </div>
        <div className="p-6">
          <div className="grid gap-4">
            <input
              data-testid="create-event-title-input"
              className="rounded-2xl border border-border bg-bg px-4 py-3 text-lg font-black outline-none"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={zh ? '事件标题' : 'Event title'}
            />
            <textarea
              data-testid="create-event-summary-input"
              className="h-28 rounded-3xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2 outline-none"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={zh ? '填写事件概览...' : 'Describe the event...'}
            />
            <input
              className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              placeholder={zh ? '时间标签' : 'Time label'}
            />
            <select
              className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none text-sm text-text"
              value={importance}
              onChange={(e) => setImportance(e.target.value as TimelineEvent['importance'])}
            >
              <option value="low">{zh ? '低' : 'Low'}</option>
              <option value="medium">{zh ? '中' : 'Medium'}</option>
              <option value="high">{zh ? '高' : 'High'}</option>
              <option value="critical">{zh ? '关键' : 'Critical'}</option>
            </select>
            <div className="flex justify-end gap-3">
              <button type="button" className="rounded-xl border border-border px-5 py-3 text-sm text-text-2" onClick={close}>{zh ? '取消' : 'Cancel'}</button>
              <button type="button" data-testid="create-event-save-btn" className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white" onClick={handleSave}>
                {zh ? '创建事件' : 'Create Event'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const InfoBlock = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-2xl border border-border bg-bg-elev-1 p-4">
    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <div className="mt-2 text-sm text-text-2">{value}</div>
  </div>
);

const colorForEvent = (event: TimelineEvent) => {
  if (event.importance === 'critical') return 'rgba(239, 68, 68, 0.95)';
  if (event.importance === 'high') return 'rgba(245, 158, 11, 0.95)';
  if (event.importance === 'low') return 'rgba(34, 197, 94, 0.9)';
  return 'rgba(59, 130, 246, 0.92)';
};
