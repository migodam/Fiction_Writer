import type { TimelineBranch, TimelineEvent } from '../../models/project.js';
import { BRANCH_RUNTIME_FIELDS, EVENT_RUNTIME_FIELDS } from './TimelineCanonicalAdapter';
export { BRANCH_RUNTIME_FIELDS, EVENT_RUNTIME_FIELDS } from './TimelineCanonicalAdapter';

const collectFields = <T extends object>(records: T[]) =>
  Array.from(
    records.reduce((fields, record) => {
      Object.keys(record).forEach((field) => fields.add(field));
      return fields;
    }, new Set<string>()),
  ).sort();

const collectPersistedFields = <T extends object>(records: T[], skipFields: Set<string>) =>
  collectFields(records).filter((field) => !skipFields.has(field));

const findMissingEntityFields = <T extends object>(
  backendRecords: T[],
  frontendRecords: T[],
  prefix: string,
  skipFields: Set<string> = new Set(),
) => {
  const backendFields = new Set(collectFields(backendRecords));
  return collectPersistedFields(frontendRecords, skipFields)
    .filter((field) => !backendFields.has(field))
    .map((field) => `${prefix}.${field}`);
};

export const collectTimelineSyncSchemaMissingFields = (
  timelineBranches: TimelineBranch[],
  timelineEvents: TimelineEvent[],
  timelineBranchSchemaFields: Set<string>,
  timelineEventSchemaFields: Set<string>,
) => [
  ...collectPersistedFields<TimelineBranch>(timelineBranches, BRANCH_RUNTIME_FIELDS)
    .filter((field) => timelineBranchSchemaFields.size > 0 && !timelineBranchSchemaFields.has(field))
    .map((field) => `schema.timelineBranch.${field}`),
  ...collectPersistedFields<TimelineEvent>(timelineEvents, EVENT_RUNTIME_FIELDS)
    .filter((field) => timelineEventSchemaFields.size > 0 && !timelineEventSchemaFields.has(field))
    .map((field) => `schema.timelineEvent.${field}`),
];

export const collectTimelineSyncEntityFieldMismatches = (
  backendBranches: TimelineBranch[],
  timelineBranches: TimelineBranch[],
  backendEvents: TimelineEvent[],
  timelineEvents: TimelineEvent[],
) => [
  ...findMissingEntityFields(backendBranches, timelineBranches, 'timelineBranches[]', BRANCH_RUNTIME_FIELDS),
  ...findMissingEntityFields(backendEvents, timelineEvents, 'timelineEvents[]', EVENT_RUNTIME_FIELDS),
];

export const findTimelineSyncValueMismatches = <T extends { id?: string }>(
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
