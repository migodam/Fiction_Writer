import type { TimelineBranch, TimelineEvent } from '../../models/project';

export type Anchor = { branchId: string; eventId: string };
export type BranchGeometry = { laneOffset: number; bend: number; thickness: number };
export type LayoutHints = { position?: { x: number; y: number }; layoutLock?: boolean };
export type TimelineBranchDraft = { name: string; color?: string; mode: 'forked' | 'independent' };

export type TimelineOperation =
  | { type: 'move_event'; eventId: string; branchId: string; orderIndex: number; layoutHints?: LayoutHints }
  | { type: 'move_branch_anchor'; branchId: string; startAnchor?: Anchor | null; endAnchor?: Anchor | null }
  | { type: 'update_branch_geometry'; branchId: string; geometry: BranchGeometry }
  | { type: 'merge_branch'; branchId: string; mergeTargetBranchId: string; mergeEventId: string }
  | { type: 'split_branch'; parentBranchId: string; forkEventId: string; newBranch: TimelineBranchDraft };

export interface TimelineProjectSlice {
  timelineBranches: TimelineBranch[];
  timelineEvents: TimelineEvent[];
}

export interface ApplyOperationResult extends TimelineProjectSlice {
  warnings: string[];
}

/**
 * Pure reducer. Does NOT read Zustand. Does NOT write to disk.
 * Store calls this, then sets state via withDirtyState().
 * Existing App.tsx 2s debounce handles disk persistence.
 */
export function applyTimelineOperation(
  project: TimelineProjectSlice,
  op: TimelineOperation,
): ApplyOperationResult {
  const warnings: string[] = [];
  const { timelineBranches: branches, timelineEvents: events } = project;

  switch (op.type) {
    case 'move_event': {
      const event = events.find((e) => e.id === op.eventId);
      if (!event) {
        warnings.push(`Event ${op.eventId} not found`);
        return { ...project, warnings };
      }
      if (!branches.find((b) => b.id === op.branchId)) {
        warnings.push(`Branch ${op.branchId} not found`);
        return { ...project, warnings };
      }
      const others = events.filter((e) => e.id !== op.eventId);
      const targetEvents = others
        .filter((e) => e.branchId === op.branchId)
        .sort((a, b) => a.orderIndex - b.orderIndex);
      const insertAt = Math.min(Math.max(op.orderIndex, 0), targetEvents.length);
      const reordered = [
        ...targetEvents.slice(0, insertAt),
        { ...event, branchId: op.branchId },
        ...targetEvents.slice(insertAt),
      ].map((e, i) => ({ ...e, orderIndex: i }));
      const sourceRemainder =
        event.branchId !== op.branchId
          ? others
              .filter((e) => e.branchId === event.branchId)
              .sort((a, b) => a.orderIndex - b.orderIndex)
              .map((e, i) => ({ ...e, orderIndex: i }))
          : [];
      const untouched = others.filter(
        (e) => e.branchId !== op.branchId && e.branchId !== event.branchId,
      );
      return {
        timelineBranches: branches,
        timelineEvents: [...untouched, ...sourceRemainder, ...reordered],
        warnings,
      };
    }

    case 'update_branch_geometry': {
      return {
        timelineBranches: branches.map((b) =>
          b.id === op.branchId ? { ...b, geometry: op.geometry } : b,
        ),
        timelineEvents: events,
        warnings,
      };
    }

    case 'move_branch_anchor': {
      const branch = branches.find((b) => b.id === op.branchId);
      if (!branch) {
        warnings.push(`Branch ${op.branchId} not found`);
        return { ...project, warnings };
      }
      const updated: TimelineBranch = { ...branch };
      if (op.startAnchor !== undefined) updated.startAnchor = op.startAnchor;
      if (op.endAnchor !== undefined) {
        updated.endAnchor = op.endAnchor;
        updated.mergeTargetBranchId = op.endAnchor?.branchId ?? null;
        updated.mergeEventId = op.endAnchor?.eventId ?? null;
        updated.endMode = op.endAnchor ? 'merge' : 'open';
      }
      return {
        timelineBranches: branches.map((b) => (b.id === op.branchId ? updated : b)),
        timelineEvents: events,
        warnings,
      };
    }

    case 'merge_branch': {
      const branch = branches.find((b) => b.id === op.branchId);
      if (!branch) {
        warnings.push(`Branch ${op.branchId} not found`);
        return { ...project, warnings };
      }
      const updated: TimelineBranch = {
        ...branch,
        endAnchor: { branchId: op.mergeTargetBranchId, eventId: op.mergeEventId },
        mergeTargetBranchId: op.mergeTargetBranchId,
        mergeEventId: op.mergeEventId,
        endMode: 'merge',
      };
      return {
        timelineBranches: branches.map((b) => (b.id === op.branchId ? updated : b)),
        timelineEvents: events,
        warnings,
      };
    }

    case 'split_branch': {
      const forkEvent = events.find((e) => e.id === op.forkEventId);
      if (!forkEvent) {
        warnings.push(`Fork event ${op.forkEventId} not found`);
        return { ...project, warnings };
      }
      const newBranch: TimelineBranch = {
        id: `branch_fork_${op.forkEventId}_${Date.now()}`,
        name: op.newBranch.name,
        color: op.newBranch.color ?? '#38bdf8',
        sortOrder: branches.length * 10 + 1,
        mode: 'forked',
        parentBranchId: op.parentBranchId,
        forkEventId: op.forkEventId,
        startAnchor: { branchId: op.parentBranchId, eventId: op.forkEventId },
        endAnchor: null,
        mergeTargetBranchId: null,
        mergeEventId: null,
        endMode: 'open',
        collapsed: false,
      };
      return {
        timelineBranches: [...branches, newBranch],
        timelineEvents: events,
        warnings,
      };
    }

    default:
      return { ...project, warnings };
  }
}
