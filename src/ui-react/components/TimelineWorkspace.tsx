import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { GitBranchPlus, Plus, Route, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import type { TimelineEvent } from '../models/project';
import { useI18n } from '../i18n';
import { TimelineCanvas } from './timeline/TimelineCanvas';

const MAIN_BRANCH_ID = 'branch_main';

export const TimelineWorkspace = () => {
  const {
    timelineEvents,
    timelineBranches,
    characters,
    worldItems,
    addTimelineEvent,
    updateTimelineEvent,
    deleteTimelineEvent,
    createTimelineBranch,
    moveTimelineEvent,
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { locale, t } = useI18n();
  const zh = locale === 'zh-CN';
  const [searchParams] = useSearchParams();
  const [activeBranchId, setActiveBranchId] = useState<string>(timelineBranches[0]?.id || MAIN_BRANCH_ID);
  const [activeEventId, setActiveEventId] = useState<string | null>(timelineEvents[0]?.id || null);
  const [characterFilter, setCharacterFilter] = useState(searchParams.get('character') || '');
  const [locationFilter, setLocationFilter] = useState(searchParams.get('location') || '');
  const [createModalOpen, setCreateModalOpen] = useState(false);

  const sortedBranches = useMemo(() => timelineBranches.slice().sort((a, b) => a.sortOrder - b.sortOrder), [timelineBranches]);

  const filteredEvents = useMemo(
    () =>
      timelineEvents.filter((event) => {
        if (characterFilter && !event.participantCharacterIds.includes(characterFilter)) return false;
        if (locationFilter && !event.locationIds.includes(locationFilter)) return false;
        return true;
      }),
    [characterFilter, locationFilter, timelineEvents],
  );

  const branchEventsMap = useMemo(() => {
    const map = new Map<string, TimelineEvent[]>();
    filteredEvents.forEach((event) => {
      const bucket = map.get(event.branchId) || [];
      bucket.push(event);
      map.set(event.branchId, bucket);
    });
    return map;
  }, [filteredEvents]);

  const activeEvent = timelineEvents.find((entry) => entry.id === activeEventId) || null;
  const activeBranch = sortedBranches.find((b) => b.id === activeBranchId) || sortedBranches[0] || null;

  useEffect(() => {
    const eventId = searchParams.get('event');
    const characterId = searchParams.get('character');
    const locationId = searchParams.get('location');
    if (eventId) setActiveEventId(eventId);
    if (characterId !== null) setCharacterFilter(characterId);
    if (locationId !== null) setLocationFilter(locationId);
  }, [searchParams]);

  const addForkBranch = () => {
    if (!activeEvent) return;
    const branchId = createTimelineBranch('forked', { branchId: activeEvent.branchId, eventId: activeEvent.id });
    if (!branchId) return;
    setActiveBranchId(branchId);
    setLastActionStatus(zh ? '已从当前事件分叉' : 'Branch forked from selected event');
  };

  const addIndependentBranch = () => {
    const branchId = createTimelineBranch('independent', null);
    if (!branchId) return;
    setActiveBranchId(branchId);
    setLastActionStatus(zh ? '已创建独立分支' : 'Independent branch created');
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg">
      <div className="flex flex-wrap items-center gap-3 border-b border-border bg-bg-elev-1 px-6 py-3" data-testid="timeline-toolbar">
        <button
          type="button"
          data-testid="add-event-btn"
          className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white"
          onClick={() => setCreateModalOpen(true)}
        >
          <Plus size={13} className="mr-2 inline" />
          {zh ? '新增事件' : 'Add Event'}
        </button>
        <button
          type="button"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2"
          onClick={addIndependentBranch}
        >
          <Route size={13} className="mr-2 inline" />
          {zh ? '独立分支' : 'New Independent Branch'}
        </button>
        <button
          type="button"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2"
          onClick={addForkBranch}
          disabled={!activeEvent}
        >
          <GitBranchPlus size={13} className="mr-2 inline" />
          {zh ? '从当前事件分叉' : 'Fork from Event'}
        </button>
        <select
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={activeBranchId}
          onChange={(e) => setActiveBranchId(e.target.value)}
        >
          {sortedBranches.map((branch) => (
            <option key={branch.id} value={branch.id}>{branch.name}</option>
          ))}
        </select>
        <select
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={characterFilter}
          onChange={(e) => setCharacterFilter(e.target.value)}
        >
          <option value="">{zh ? '全部人物' : 'All Characters'}</option>
          {characters.map((character) => (
            <option key={character.id} value={character.id}>{character.name}</option>
          ))}
        </select>
        <select
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={locationFilter}
          onChange={(e) => setLocationFilter(e.target.value)}
        >
          <option value="">{zh ? '全部地点' : 'All Locations'}</option>
          {worldItems.filter((entry) => entry.type === 'location').map((location) => (
            <option key={location.id} value={location.id}>{location.name}</option>
          ))}
        </select>
      </div>

      <div className="min-h-0 flex-1">
        <TimelineCanvas events={filteredEvents} branches={sortedBranches} />
      </div>

      {createModalOpen && (
        <CreateEventModal
          defaultBranchId={activeEvent?.branchId || activeBranch?.id || MAIN_BRANCH_ID}
          defaultSlot={
            activeEvent
              ? (branchEventsMap.get(activeEvent.branchId) || [])
                  .slice()
                  .sort((a, b) => a.orderIndex - b.orderIndex)
                  .findIndex((entry) => entry.id === activeEvent.id) + 1
              : (branchEventsMap.get(activeBranch?.id || MAIN_BRANCH_ID) || []).length
          }
          addEvent={addTimelineEvent}
          moveEvent={moveTimelineEvent}
          onCreated={(id) => {
            setActiveEventId(id);
            setLastActionStatus(zh ? '事件已创建' : 'Event created');
          }}
          close={() => setCreateModalOpen(false)}
          zh={zh}
        />
      )}
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
              <button type="button" className="rounded-xl border border-border px-5 py-3 text-sm text-text-2" onClick={close}>
                {zh ? '取消' : 'Cancel'}
              </button>
              <button
                type="button"
                data-testid="create-event-save-btn"
                className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white"
                onClick={handleSave}
              >
                {zh ? '创建事件' : 'Create Event'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
