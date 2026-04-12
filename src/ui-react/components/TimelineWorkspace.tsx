import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { GitBranchPlus, Plus, Route, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import type { TimelineBranch, TimelineEvent } from '../models/project';
import { useI18n } from '../i18n';
import { TimelineCanvas } from './timeline/TimelineCanvas';

const MAIN_BRANCH_ID = 'branch_main';

export const TimelineWorkspace = () => {
  const {
    projectRoot,
    timelineEvents,
    timelineBranches,
    characters,
    worldItems,
    addTimelineEvent,
    createTimelineBranch,
    moveTimelineEvent,
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const [activeBranchId, setActiveBranchId] = useState<string>(timelineBranches[0]?.id || MAIN_BRANCH_ID);
  const [activeEventId, setActiveEventId] = useState<string | null>(timelineEvents[0]?.id || null);
  const [characterFilter, setCharacterFilter] = useState(searchParams.get('character') || '');
  const [locationFilter, setLocationFilter] = useState(searchParams.get('location') || '');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [drawModeBranchId, setDrawModeBranchId] = useState<string | null>(null);

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
    setLastActionStatus(t('timeline.branchForked', 'Branch forked from selected event'));
  };

  const addIndependentBranch = () => {
    const branchId = createTimelineBranch('independent', null);
    if (!branchId) return;
    setActiveBranchId(branchId);
    setLastActionStatus(t('timeline.independentBranch', 'Independent branch created'));
  };

  const handleSynchronizeAnalysis = () => {
    const scope = globalThis as typeof globalThis & { require?: NodeRequire };
    const loader = scope.require;
    if (!loader) {
      console.warn('[Timeline Synchronize] Node file access is unavailable in this environment.');
      setLastActionStatus(t('timeline.syncUnavailable', 'Synchronize analysis unavailable'));
      return;
    }

    try {
      const fs = loader('fs') as typeof import('fs');
      const path = loader('path') as typeof import('path');
      // projectRoot may be a virtual URI like "memory://starter-demo-project" for seed/demo
      // projects. Those are not real filesystem paths, so we must fall back to the on-disk
      // dev fixture instead of letting path.resolve() produce a garbled result.
      const isVirtualRoot = !projectRoot || /^[a-z][a-z0-9+\-.]*:\/\//i.test(projectRoot);
      const resolvedRoot = isVirtualRoot
        ? path.resolve('data/projects/starter-demo-project')
        : path.resolve(projectRoot);
      const projectJsonPath = path.join(resolvedRoot, 'project.json');
      const projectJson = JSON.parse(fs.readFileSync(projectJsonPath, 'utf8')) as Record<string, unknown>;
      const projectSchemaPath = path.join(resolvedRoot, 'system', 'schema', 'schema.json');
      const projectSchema = fs.existsSync(projectSchemaPath)
        ? (JSON.parse(fs.readFileSync(projectSchemaPath, 'utf8')) as Record<string, unknown>)
        : null;
      const timelineDir = path.join(resolvedRoot, 'entities', 'timeline');
      const branchesPath = path.join(timelineDir, 'branches.json');
      const backendBranches = fs.existsSync(branchesPath)
        ? (JSON.parse(fs.readFileSync(branchesPath, 'utf8')) as TimelineBranch[])
        : [];
      const backendEvents = fs.existsSync(timelineDir)
        ? fs
            .readdirSync(timelineDir)
            .filter((name: string) => name.endsWith('.json') && name !== 'branches.json')
            .map((name: string) =>
              JSON.parse(fs.readFileSync(path.join(timelineDir, name), 'utf8')) as TimelineEvent
            )
        : [];

      const projectJsonCounts = (projectJson.counts as Record<string, number> | undefined) || {};
      const schemaEntities = (projectSchema?.entities as Record<string, { required?: string[]; optional?: string[] }> | undefined) || {};
      const timelineBranchSchemaFields = new Set([
        ...(schemaEntities.timelineBranch?.required || []),
        ...(schemaEntities.timelineBranch?.optional || []),
      ]);
      const timelineEventSchemaFields = new Set([
        ...(schemaEntities.timelineEvent?.required || []),
        ...(schemaEntities.timelineEvent?.optional || []),
      ]);
      const missingProjectJsonFields = [
        ...(!('timelineBranches' in projectJsonCounts) ? ['counts.timelineBranches'] : []),
        ...(!('timelineEvents' in projectJsonCounts) ? ['counts.timelineEvents'] : []),
      ];
      const missingSchemaFields = [
        ...collectFields<TimelineBranch>(timelineBranches).filter((field) => timelineBranchSchemaFields.size > 0 && !timelineBranchSchemaFields.has(field)).map((field) => `schema.timelineBranch.${field}`),
        ...collectFields<TimelineEvent>(timelineEvents).filter((field) => timelineEventSchemaFields.size > 0 && !timelineEventSchemaFields.has(field)).map((field) => `schema.timelineEvent.${field}`),
      ];
      const entityFieldMismatches = [
        ...findMissingEntityFields(backendBranches, timelineBranches, 'timelineBranches[]'),
        ...findMissingEntityFields(backendEvents, timelineEvents, 'timelineEvents[]'),
      ];
      const entityValueMismatches = [
        ...findValueMismatches(backendBranches, timelineBranches, 'timelineBranches', BRANCH_RUNTIME_FIELDS),
        ...findValueMismatches(backendEvents, timelineEvents, 'timelineEvents', EVENT_RUNTIME_FIELDS),
      ];

      const projectJsonMatchesCanvas =
        missingProjectJsonFields.length === 0 &&
        projectJsonCounts.timelineEvents === timelineEvents.length &&
        projectJsonCounts.timelineBranches === timelineBranches.length;

      const report = {
        projectJsonPath,
        answers: {
          projectJsonMatchesCanvas,
          projectJsonStructureMatchesCanvasWriteNeeds: missingProjectJsonFields.length === 0,
          schemaMatchesCanvasWriteNeeds: missingSchemaFields.length === 0,
          entityTimelineFilesMatchCanvas:
            backendBranches.length === timelineBranches.length &&
            backendEvents.length === timelineEvents.length &&
            entityFieldMismatches.length === 0 &&
            entityValueMismatches.length === 0,
        },
        fieldMismatches: {
          projectJsonMissingFields: missingProjectJsonFields,
          schemaMissingFields: missingSchemaFields,
          entityTimelineFieldMismatches: entityFieldMismatches,
          entityTimelineValueMismatches: entityValueMismatches,
        },
        counts: {
          frontend: {
            timelineBranches: timelineBranches.length,
            timelineEvents: timelineEvents.length,
          },
          projectJson: {
            timelineBranches: projectJsonCounts.timelineBranches ?? null,
            timelineEvents: projectJsonCounts.timelineEvents ?? null,
          },
          entityTimelineFiles: {
            timelineBranches: backendBranches.length,
            timelineEvents: backendEvents.length,
          },
        },
        notes: [
          '`project.json` stores metadata and counts only; canonical timeline entities live under `entities/timeline/`.',
          'Timeline branches are persisted in `entities/timeline/branches.json`.',
          'Timeline events are persisted as one JSON file per event in `entities/timeline/`.',
          'Canvas snap propagation relies on semantic anchors (`startAnchor` / `endAnchor`) plus resolved positions (`anchorStartPos` / `anchorEndPos`).',
        ],
      };

      console.group('[Timeline Synchronize] Analysis Report');
      console.log('Report:', report);
      console.table(report.counts);
      if (report.fieldMismatches.projectJsonMissingFields.length > 0) {
        console.warn('Missing project.json fields:', report.fieldMismatches.projectJsonMissingFields);
      }
      if (report.fieldMismatches.schemaMissingFields.length > 0) {
        console.warn('Missing schema fields:', report.fieldMismatches.schemaMissingFields);
      }
      if (report.fieldMismatches.entityTimelineFieldMismatches.length > 0) {
        console.warn('Timeline entity field mismatches:', report.fieldMismatches.entityTimelineFieldMismatches);
      }
      if (report.fieldMismatches.entityTimelineValueMismatches.length > 0) {
        console.warn('Timeline entity value mismatches:', report.fieldMismatches.entityTimelineValueMismatches);
      }
      console.groupEnd();
      setLastActionStatus(t('timeline.syncWritten', 'Synchronize analysis written to console'));
    } catch (error) {
      console.error('[Timeline Synchronize] Analysis failed:', error);
      setLastActionStatus(t('timeline.syncFailed', 'Synchronize analysis failed'));
    }
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
          {t('timeline.addEvent', 'Add Event')}
        </button>
        <button
          type="button"
          data-testid="timeline-new-branch-btn"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2"
          onClick={addIndependentBranch}
        >
          <Route size={13} className="mr-2 inline" />
          {t('timeline.newBranch', 'New Branch')}
        </button>
        <button
          type="button"
          data-testid="timeline-fork-branch-btn"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2"
          onClick={addForkBranch}
          disabled={!activeEvent}
        >
          <GitBranchPlus size={13} className="mr-2 inline" />
          {t('timeline.forkFromEvent', 'Fork from Event')}
        </button>
        <button
          type="button"
          data-testid="timeline-synchronize-btn"
          className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2"
          onClick={handleSynchronizeAnalysis}
        >
          {t('timeline.synchronize', 'Synchronize')}
        </button>
        {drawModeBranchId && (
          <span className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-brand">
            {t('timeline.drawing', 'Drawing: {name}').replace('{name}', timelineBranches.find(b => b.id === drawModeBranchId)?.name || drawModeBranchId || '')}
            <button
              type="button"
              data-testid="timeline-draw-cancel-btn"
              className="ml-2 rounded px-2 py-0.5 text-[10px] text-text-3 hover:bg-hover"
              onClick={() => setDrawModeBranchId(null)}
            >
              {t('common.cancel', 'Cancel')}
            </button>
          </span>
        )}
        <select
          data-testid="timeline-branch-filter"
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={activeBranchId}
          onChange={(e) => setActiveBranchId(e.target.value)}
        >
          {sortedBranches.map((branch) => (
            <option key={branch.id} value={branch.id}>{branch.name}</option>
          ))}
        </select>
        <select
          data-testid="timeline-character-filter"
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={characterFilter}
          onChange={(e) => setCharacterFilter(e.target.value)}
        >
          <option value="">{t('timeline.allCharacters', 'All Characters')}</option>
          {characters.map((character) => (
            <option key={character.id} value={character.id}>{character.name}</option>
          ))}
        </select>
        <select
          data-testid="timeline-location-filter"
          className="rounded-xl border border-border bg-bg px-3 py-2 text-[11px] font-black text-text-2"
          value={locationFilter}
          onChange={(e) => setLocationFilter(e.target.value)}
        >
          <option value="">{t('timeline.allLocations', 'All Locations')}</option>
          {worldItems.filter((entry) => entry.type === 'location').map((location) => (
            <option key={location.id} value={location.id}>{location.name}</option>
          ))}
        </select>
      </div>

      <div className="min-h-0 flex-1">
        <TimelineCanvas
          events={filteredEvents}
          branches={sortedBranches}
          drawModeBranchId={drawModeBranchId}
          onDrawModeChange={(id) => setDrawModeBranchId(id)}
        />
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
            setLastActionStatus(t('timeline.eventCreated', 'Event created'));
          }}
          close={() => setCreateModalOpen(false)}
          t={t}
        />
      )}
    </div>
  );
};

const collectFields = <T extends object>(records: T[]) =>
  Array.from(
    records.reduce((fields, record) => {
      Object.keys(record).forEach((field) => fields.add(field));
      return fields;
    }, new Set<string>()),
  ).sort();

const findMissingEntityFields = <T extends object>(
  backendRecords: T[],
  frontendRecords: T[],
  prefix: string,
) => {
  const backendFields = new Set(collectFields(backendRecords));
  return collectFields(frontendRecords)
    .filter((field) => !backendFields.has(field))
    .map((field) => `${prefix}.${field}`);
};

// Fields that are recomputed at runtime and intentionally diverge from disk state.
// Comparing these always produces false positives in the Synchronize report.
const BRANCH_RUNTIME_FIELDS = new Set([
  'anchorStartPos',    // recomputed from event positions by propagateTimelineAnchorDependencies()
  'anchorEndPos',      // same
  'endAnchor',         // normalized from anchor semantics on load
  'endMode',           // same
  'mergeEventId',      // same
  'mergeTargetBranchId', // same
]);

const EVENT_RUNTIME_FIELDS = new Set([
  'position',          // SVG canvas coord derived from tFromOrderIndex + Bézier; not persisted
  'sharedBranchIds',   // derived from cross-branch membership at render time
]);

const sortComparableObject = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map((entry) => sortComparableObject(entry));
  }

  if (!value || typeof value !== 'object') {
    return value ?? null;
  }

  return Object.keys(value as Record<string, unknown>)
    .sort()
    .reduce<Record<string, unknown>>((acc, key) => {
      acc[key] = sortComparableObject((value as Record<string, unknown>)[key]);
      return acc;
    }, {});
};

const normalizeComparableFieldValue = (field: string, value: unknown) => {
  if (field === 'startAnchor' || field === 'endAnchor') {
    const anchor = value as Partial<{ branchId: unknown; eventId: unknown }> | null | undefined;
    if (!anchor?.branchId || !anchor?.eventId) {
      return null;
    }

    return {
      branchId: String(anchor.branchId),
      eventId: String(anchor.eventId),
    };
  }

  return sortComparableObject(value ?? null);
};

const findValueMismatches = <T extends { id?: string }>(
  backendRecords: T[],
  frontendRecords: T[],
  prefix: string,
  skipFields: Set<string> = new Set(),
) => {
  const backendById = new Map(backendRecords.map((record) => [record.id || JSON.stringify(record), record]));
  const frontendById = new Map(frontendRecords.map((record) => [record.id || JSON.stringify(record), record]));
  const mismatches: string[] = [];

  frontendById.forEach((frontendRecord, recordId) => {
    const backendRecord = backendById.get(recordId);
    if (!backendRecord) {
      mismatches.push(`${prefix}.${recordId}: missing backend record`);
      return;
    }

    collectFields([frontendRecord]).forEach((field) => {
      if (skipFields.has(field)) return;
      const frontendValue = JSON.stringify(
        normalizeComparableFieldValue(field, (frontendRecord as Record<string, unknown>)[field]),
      );
      const backendValue = JSON.stringify(
        normalizeComparableFieldValue(field, (backendRecord as Record<string, unknown>)[field]),
      );
      if (frontendValue !== backendValue) {
        mismatches.push(`${prefix}.${recordId}.${field}`);
      }
    });
  });

  backendById.forEach((_backendRecord, recordId) => {
    if (!frontendById.has(recordId)) {
      mismatches.push(`${prefix}.${recordId}: extra backend record`);
    }
  });

  return mismatches;
};

const CreateEventModal = ({
  defaultBranchId,
  defaultSlot,
  addEvent,
  moveEvent,
  onCreated,
  close,
  t,
}: {
  defaultBranchId: string;
  defaultSlot: number;
  addEvent: (event: TimelineEvent) => void;
  moveEvent: (eventId: string, branchId: string, slot: number) => void;
  onCreated: (id: string) => void;
  close: () => void;
  t: (key: string, fallback?: string) => string;
}) => {
  const [title, setTitle] = useState(t('timeline.newEvent', 'New Event'));
  const [summary, setSummary] = useState('');
  const [time, setTime] = useState(t('timeline.timeTbd', 'TBD'));
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
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('timeline.addEvent', 'New Event')}</div>
            <div className="mt-1 text-lg font-black text-text">{t('timeline.configureEvent', 'Configure Event')}</div>
          </div>
          <button
            type="button"
            data-testid="create-event-close-btn"
            className="rounded p-2 text-text-3 hover:bg-hover hover:text-text"
            onClick={close}
          >
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
              placeholder={t('timeline.eventTitlePlaceholder', 'Event title')}
            />
            <textarea
              data-testid="create-event-summary-input"
              className="h-28 rounded-3xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2 outline-none"
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder={t('timeline.describeEventPlaceholder', 'Describe the event...')}
            />
            <input
              data-testid="create-event-time-input"
              className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              placeholder={t('timeline.timeLabelPlaceholder', 'Time label')}
            />
            <select
              data-testid="create-event-importance-select"
              className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none text-sm text-text"
              value={importance}
              onChange={(e) => setImportance(e.target.value as TimelineEvent['importance'])}
            >
              <option value="low">{t('timeline.importanceLow', 'Low')}</option>
              <option value="medium">{t('timeline.importanceMedium', 'Medium')}</option>
              <option value="high">{t('timeline.importanceHigh', 'High')}</option>
              <option value="critical">{t('timeline.importanceCritical', 'Critical')}</option>
            </select>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                data-testid="create-event-cancel-btn"
                className="rounded-xl border border-border px-5 py-3 text-sm text-text-2"
                onClick={close}
              >
                {t('common.cancel', 'Cancel')}
              </button>
              <button
                type="button"
                data-testid="create-event-save-btn"
                className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white"
                onClick={handleSave}
              >
                {t('timeline.createEventBtn', 'Create Event')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
