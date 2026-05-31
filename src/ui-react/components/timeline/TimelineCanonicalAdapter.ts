import type { TimelineBranch, TimelineEvent } from '../../models/project';

/**
 * ONLY the two computed bezier position fields are runtime-only.
 * All topology fields (endAnchor, endMode, mergeTargetBranchId, mergeEventId,
 * startAnchor, parentBranchId, forkEventId, geometry) are CANONICAL — they
 * persist to disk and must participate in sync comparison.
 */
export const BRANCH_RUNTIME_FIELDS = new Set<string>([
  'anchorStartPos', // computed bezier P0 pixel position
  'anchorEndPos',   // computed bezier P3 pixel position
]);

export const EVENT_RUNTIME_FIELDS = new Set<string>([
  'position',        // recomputed by layout engine
  'sharedBranchIds', // view-only display
  'layoutLock',      // editor state
  'modalStateHints', // editor state
]);

/** Strip runtime fields before disk write */
export function toCanonical(branches: TimelineBranch[], events: TimelineEvent[]) {
  const strip = <T extends object>(obj: T, fields: Set<string>): T => {
    const copy = { ...obj };
    for (const f of fields) delete (copy as Record<string, unknown>)[f];
    return copy;
  };
  return {
    branches: branches.map((b) => strip(b, BRANCH_RUNTIME_FIELDS)),
    events: events.map((e) => strip(e, EVENT_RUNTIME_FIELDS)),
  };
}
