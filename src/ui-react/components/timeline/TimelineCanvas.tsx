import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import type { TimelineEvent, TimelineBranch } from '../../models/project';
import {
  buildBranchControlPoints,
  cubicBezierPoint,
  fanLaneOffset,
  nearestTOnCurve,
  type Point,
  tFromOrderIndex,
  screenToCanvas,
} from './bezierMath';
import { BranchEdge } from './BranchEdge';
import { TimelineEventNode } from './TimelineEventNode';
import { EventEditModal } from './EventEditModal';

type InteractionMode = 'idle' | 'panning' | 'event-drag' | 'event-drop' | 'branch-drag';

type SnapTargetKind = 'event' | 'branch-anchor-start' | 'branch-anchor-end' | 'branch-curve';

interface SnapTarget {
  kind: SnapTargetKind;
  branchId: string;
  point: Point;
  eventId?: string;
  orderIndex?: number;
  t?: number;
  distance?: number;
}

interface TimelineCanvasProps {
  events: TimelineEvent[];
  branches: TimelineBranch[];
  drawModeBranchId?: string | null;
  onDrawModeChange?: (branchId: string | null) => void;
}

interface DragState {
  eventId: string;
  pointerId: number;
  startPointerPos: Point;
  startEventPos: Point;
  currentCanvasPos: Point;
  hasMoved: boolean;
  snapTarget: SnapTarget | null;
  interaction: 'move' | 'drop';
}

interface EventPressState {
  eventId: string;
  pointerId: number;
  startPointerPos: Point;
  startEventPos: Point;
}

type BranchHandle = 'start' | 'end' | 'bend';

interface BranchDragState {
  branchId: string;
  handle: BranchHandle;
  // Original anchors/geometry at drag start
  origStartPos: Point;
  origEndPos: Point;
  origBend: number;
  origStartAnchor: TimelineBranch['startAnchor'];
  origEndAnchor: TimelineBranch['endAnchor'];
  snapTarget: SnapTarget | null;
}

interface BranchContextMenuState {
  branchId: string;
  x: number;
  y: number;
}

const MOVE_THRESHOLD_PX = 5;
const SNAP_THRESHOLD = 40;
const LONG_PRESS_MS = 500;
const BRANCH_LANE_SPACING = 120;

function resolveBranchEndAnchor(branch: TimelineBranch): TimelineBranch['endAnchor'] {
  return branch.endAnchor ?? (
    branch.mergeEventId && branch.mergeTargetBranchId
      ? { branchId: branch.mergeTargetBranchId, eventId: branch.mergeEventId }
      : null
  );
}

function getBranchParentId(branch: TimelineBranch, branchIds: Set<string>): string | null {
  const parentId = branch.parentBranchId ?? branch.startAnchor?.branchId ?? null;
  return parentId && branchIds.has(parentId) ? parentId : null;
}

export function TimelineCanvas({ events, branches, drawModeBranchId, onDrawModeChange }: TimelineCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const branchDragStateRef = useRef<BranchDragState | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const eventPressTimerRef = useRef<number | null>(null);
  const {
    selectedEntity,
    setSelectedEntity,
    updateTimelineEventPosition,
    addTimelineEvent,
    moveTimelineEvent,
    deleteTimelineBranch,
    setTimelineBranchAnchors,
    setTimelineBranchGeometry,
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();

  // Viewport
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [zoom, setZoom] = useState(1);

  // Interaction
  const [mode, setMode] = useState<InteractionMode>('idle');
  const [hoveredEventId, setHoveredEventId] = useState<string | null>(null);
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const [eventPressState, setEventPressState] = useState<EventPressState | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [branchDragState, setBranchDragState] = useState<BranchDragState | null>(null);
  const [branchContextMenu, setBranchContextMenu] = useState<BranchContextMenuState | null>(null);
  const [deleteConfirmBranchId, setDeleteConfirmBranchId] = useState<string | null>(null);
  const [cursorPos, setCursorPos] = useState<Point | null>(null);

  const selectedBranchId = selectedEntity.type === 'timeline_branch' ? selectedEntity.id : null;
  const branchEventCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      counts.set(event.branchId, (counts.get(event.branchId) || 0) + 1);
    }
    return counts;
  }, [events]);

  // Panning state
  const panStartRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  useEffect(() => {
    branchDragStateRef.current = branchDragState;
  }, [branchDragState]);

  useEffect(() => {
    dragStateRef.current = dragState;
  }, [dragState]);

  useEffect(() => () => {
    if (eventPressTimerRef.current !== null) {
      window.clearTimeout(eventPressTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (selectedBranchId && !branches.some((branch) => branch.id === selectedBranchId)) {
      setSelectedEntity(null, null);
      setBranchContextMenu(null);
    }
  }, [branches, selectedBranchId, setSelectedEntity]);

  // ── Derived data ──────────────────────────────────────────

  const svgWidth = 2000;
  const sortedBranches = useMemo(
    () => branches.slice().sort((left, right) => left.sortOrder - right.sortOrder || left.id.localeCompare(right.id)),
    [branches],
  );

  const branchLaneOffsets = useMemo(() => {
    const offsets = new Map<string, number>();
    const branchIds = new Set(sortedBranches.map((branch) => branch.id));
    const childrenByParent = new Map<string, TimelineBranch[]>();
    const roots: TimelineBranch[] = [];

    for (const branch of sortedBranches) {
      const parentId = getBranchParentId(branch, branchIds);
      if (!parentId) {
        roots.push(branch);
        continue;
      }

      const bucket = childrenByParent.get(parentId) || [];
      bucket.push(branch);
      childrenByParent.set(parentId, bucket);
    }

    const primaryRoot = roots.find((branch) => branch.mode === 'root' || branch.id === 'branch_main') ?? roots[0];
    if (primaryRoot) {
      offsets.set(primaryRoot.id, primaryRoot.geometry?.laneOffset ?? 0);
    }

    roots
      .filter((branch) => branch.id !== primaryRoot?.id)
      .forEach((branch, index) => {
        const baseLane = primaryRoot ? (offsets.get(primaryRoot.id) ?? 0) : 0;
        offsets.set(branch.id, baseLane + fanLaneOffset(index, BRANCH_LANE_SPACING));
      });

    const assignChildLanes = (parentId: string) => {
      const parentLane = offsets.get(parentId) ?? 0;
      const children = childrenByParent.get(parentId) || [];

      children.forEach((branch, index) => {
        offsets.set(branch.id, parentLane + fanLaneOffset(index, BRANCH_LANE_SPACING));
        assignChildLanes(branch.id);
      });
    };

    for (const root of roots) {
      assignChildLanes(root.id);
    }

    sortedBranches.forEach((branch, index) => {
      if (!offsets.has(branch.id)) {
        offsets.set(branch.id, branch.geometry?.laneOffset ?? fanLaneOffset(index, BRANCH_LANE_SPACING));
      }
    });

    return offsets;
  }, [sortedBranches]);

  const branchCPMap = useMemo(() => {
    const map = new Map<string, { p0: Point; p1: Point; p2: Point; p3: Point }>();
    sortedBranches.forEach((branch, idx) => {
      map.set(
        branch.id,
        buildBranchControlPoints(
          branch.anchorStartPos,
          branch.anchorEndPos,
          branchLaneOffsets.get(branch.id) ?? branch.geometry?.laneOffset ?? idx * BRANCH_LANE_SPACING,
          branch.geometry?.bend ?? 0.25,
          svgWidth,
        ),
      );
    });
    return map;
  }, [branchLaneOffsets, sortedBranches]);

  const branchEventsMap = useMemo(() => {
    const map = new Map<string, TimelineEvent[]>();
    for (const event of events) {
      const bucket = map.get(event.branchId) || [];
      bucket.push(event);
      map.set(event.branchId, bucket);
    }
    for (const [, evts] of map) {
      evts.sort((a, b) => a.orderIndex - b.orderIndex);
    }
    return map;
  }, [events]);

  const eventPositions = useMemo(() => {
    const map = new Map<string, Point>();
    for (const event of events) {
      const cp = branchCPMap.get(event.branchId);
      if (!cp) continue;
      if (event.position) {
        map.set(event.id, event.position);
      } else {
        const evtsOnBranch = branchEventsMap.get(event.branchId) || [];
        const tVal = tFromOrderIndex(evtsOnBranch.length, evtsOnBranch.indexOf(event));
        map.set(event.id, cubicBezierPoint(cp.p0, cp.p1, cp.p2, cp.p3, tVal));
      }
    }
    return map;
  }, [events, branchCPMap, branchEventsMap]);

  const eventCurveParams = useMemo(() => {
    const map = new Map<string, number>();

    for (const event of events) {
      const cp = branchCPMap.get(event.branchId);
      if (!cp) continue;

      if (event.position) {
        map.set(event.id, nearestTOnCurve(cp, event.position, 100).t);
      } else {
        const evtsOnBranch = branchEventsMap.get(event.branchId) || [];
        map.set(event.id, tFromOrderIndex(evtsOnBranch.length, evtsOnBranch.indexOf(event)));
      }
    }

    return map;
  }, [events, branchCPMap, branchEventsMap]);

  const branchRenderEntries = useMemo(() => {
    return sortedBranches
      .map((branch) => {
        const controlPoints = branchCPMap.get(branch.id);
        if (!controlPoints) return null;

        return {
          branch,
          controlPoints,
          memberBranchIds: [branch.id],
          renderMode: 'default' as const,
          showStartArrow: false,
          showEndArrow: true,
        };
      })
      .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));
  }, [branchCPMap, sortedBranches]);

  const renderedBranchIds = useMemo(
    () => new Set(branchRenderEntries.map((entry) => entry.branch.id)),
    [branchRenderEntries],
  );

  const snapTargets = useMemo(() => {
    const targets: SnapTarget[] = [];

    for (const event of events) {
      const point = eventPositions.get(event.id);
      if (!point) continue;
      targets.push({
        kind: 'event',
        branchId: event.branchId,
        point,
        eventId: event.id,
        orderIndex: event.orderIndex,
      });
    }

    for (const entry of branchRenderEntries) {
      targets.push({ kind: 'branch-anchor-start', branchId: entry.branch.id, point: entry.controlPoints.p0 });
      targets.push({ kind: 'branch-anchor-end', branchId: entry.branch.id, point: entry.controlPoints.p3 });
    }

    return targets;
  }, [branchRenderEntries, events, eventPositions]);

  // ── Coordinate helpers ──────────────────────────────────────

  const getCanvasPoint = useCallback(
    (e: React.PointerEvent): Point | null => {
      if (!svgRef.current) return null;
      const screen = { x: e.clientX, y: e.clientY };
      const svgPt = screenToCanvas(screen, svgRef.current);
      return { x: (svgPt.x - panX) / zoom, y: (svgPt.y - panY) / zoom };
    },
    [panX, panY, zoom]
  );

  const findNearestSnapTarget = useCallback(
    (canvasPt: Point, exclude?: (target: SnapTarget) => boolean): SnapTarget | null => {
      const adjustedThreshold = SNAP_THRESHOLD / zoom;
      let bestTarget: SnapTarget | null = null;
      let bestDistance = adjustedThreshold;

      for (const target of snapTargets) {
        if (exclude?.(target)) continue;
        const distance = Math.hypot(target.point.x - canvasPt.x, target.point.y - canvasPt.y);
        if (distance <= bestDistance) {
          bestDistance = distance;
          bestTarget = target;
        }
      }

      return bestTarget;
    },
    [snapTargets, zoom]
  );

  const findNearestBranchCurveTarget = useCallback(
    (canvasPt: Point): SnapTarget | null => {
      const adjustedThreshold = SNAP_THRESHOLD / zoom;
      let bestTarget: SnapTarget | null = null;
      let bestDistance = adjustedThreshold;

      for (const entry of branchRenderEntries) {
        const result = nearestTOnCurve(entry.controlPoints, canvasPt, 100);
        if (result.dist <= bestDistance) {
          bestDistance = result.dist;
          bestTarget = {
            kind: 'branch-curve',
            branchId: entry.branch.id,
            point: result.pt,
            t: result.t,
            distance: result.dist,
          };
        }
      }

      return bestTarget;
    },
    [branchRenderEntries, zoom]
  );

  const pickClosestSnapTarget = useCallback((canvasPt: Point, targets: Array<SnapTarget | null>) => {
    let bestTarget: SnapTarget | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;

    for (const target of targets) {
      if (!target) continue;
      const distance =
        typeof target.distance === 'number'
          ? target.distance
          : Math.hypot(target.point.x - canvasPt.x, target.point.y - canvasPt.y);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestTarget = target;
      }
    }

    return bestTarget;
  }, []);

  const clearBranchSelection = useCallback(() => {
    if (selectedBranchId) {
      setSelectedEntity(null, null);
    }
  }, [selectedBranchId, setSelectedEntity]);

  const clearPendingEventPress = useCallback(() => {
    if (eventPressTimerRef.current !== null) {
      window.clearTimeout(eventPressTimerRef.current);
      eventPressTimerRef.current = null;
    }
    setEventPressState(null);
  }, []);

  const startEventDrag = useCallback(
    (interaction: DragState['interaction'], pressState: EventPressState, currentCanvasPos?: Point) => {
      const nextDragState: DragState = {
        eventId: pressState.eventId,
        pointerId: pressState.pointerId,
        startPointerPos: pressState.startPointerPos,
        startEventPos: pressState.startEventPos,
        currentCanvasPos: currentCanvasPos ?? pressState.startEventPos,
        hasMoved: Boolean(currentCanvasPos),
        snapTarget: null,
        interaction,
      };

      dragStateRef.current = nextDragState;
      setDragState(nextDragState);
      setMode(interaction === 'drop' ? 'event-drop' : 'event-drag');
    },
    [],
  );

  const commitEventDrag = useCallback(
    (state: DragState) => {
      const finalPos = state.snapTarget?.point ?? state.currentCanvasPos;
      updateTimelineEventPosition(state.eventId, finalPos);
      const event = events.find((entry) => entry.id === state.eventId);
      if (event && state.snapTarget) {
        const targetEvents = branchEventsMap.get(state.snapTarget.branchId) || [];
        const slot = computeSlotFromSnapTarget(
          targetEvents,
          state.snapTarget,
          eventCurveParams,
          state.eventId,
        );
        if (event.branchId !== state.snapTarget.branchId || event.orderIndex !== slot) {
          moveTimelineEvent(state.eventId, state.snapTarget.branchId, slot);
        }
      }
    },
    [branchEventsMap, eventCurveParams, events, moveTimelineEvent, updateTimelineEventPosition],
  );

  const startBranchDrag = useCallback(
    (branchId: string, handle: BranchHandle) => {
      const branch = branches.find((entry) => entry.id === branchId);
      if (!branch) return false;
      const cp = branchCPMap.get(branchId);
      if (!cp) return false;

      const nextState = {
        branchId,
        handle,
        origStartPos: cp.p0,
        origEndPos: cp.p3,
        origBend: branch.geometry?.bend ?? 0.25,
        origStartAnchor: branch.startAnchor ?? null,
        origEndAnchor: resolveBranchEndAnchor(branch),
        snapTarget: null,
      };

      branchDragStateRef.current = nextState;
      setBranchDragState(nextState);
      setBranchContextMenu(null);
      setSelectedEntity('timeline_branch', branchId);
      setMode('branch-drag');
      return true;
    },
    [branches, branchCPMap, setSelectedEntity],
  );

  const findAttachedEndpoint = useCallback(
    (eventId: string) => {
      const attached = branches.flatMap((branch) => {
        const entries: Array<{ branchId: string; handle: BranchHandle }> = [];
        if (branch.startAnchor?.eventId === eventId) {
          entries.push({ branchId: branch.id, handle: 'start' });
        }
        if (resolveBranchEndAnchor(branch)?.eventId === eventId) {
          entries.push({ branchId: branch.id, handle: 'end' });
        }
        return entries;
      });

      if (attached.length === 0) return null;
      if (selectedBranchId) {
        const selectedAttachment = attached.find((entry) => entry.branchId === selectedBranchId);
        if (selectedAttachment) return selectedAttachment;
      }

      const visibleAttachment = attached.find((entry) => renderedBranchIds.has(entry.branchId));
      return visibleAttachment ?? attached[0];
    },
    [branches, renderedBranchIds, selectedBranchId],
  );

  const handleDeleteBranch = useCallback(
    (branchId: string) => {
      deleteTimelineBranch(branchId);
      setDeleteConfirmBranchId(null);
      setBranchContextMenu(null);
      if (selectedBranchId === branchId) {
        setSelectedEntity(null, null);
      }
      setLastActionStatus(t('timeline.deleted'));
    },
    [deleteTimelineBranch, selectedBranchId, setLastActionStatus, setSelectedEntity]
  );

  const handleRequestDeleteBranch = useCallback(
    (branchId: string) => {
      setBranchContextMenu(null);
      const branchEventCount = branchEventCounts.get(branchId) || 0;
      if (branchEventCount > 0) {
        window.alert(t('timeline.deleteBlocked'));
        setLastActionStatus(t('timeline.deleteBlockedStatus'));
        return;
      }
      setDeleteConfirmBranchId(branchId);
    },
    [branchEventCounts, setLastActionStatus]
  );

  // ── Global pointer move/up for dragging (window-level) ────────
  // This fixes: events can't be dragged because pointer leaves the small SVG circle

  useEffect(() => {
    const isDraggingEvent = (mode === 'event-drag' || mode === 'event-drop') && dragState;
    if (!eventPressState && !isDraggingEvent) return;

    const toCanvasPoint = (e: PointerEvent) => {
      if (!svgRef.current) return null;
      const svgPt = screenToCanvas({ x: e.clientX, y: e.clientY }, svgRef.current);
      return { x: (svgPt.x - panX) / zoom, y: (svgPt.y - panY) / zoom };
    };

    const computePreviewState = (state: DragState, canvasPt: Point) => {
      const nextPos = {
        x: state.startEventPos.x + (canvasPt.x - state.startPointerPos.x),
        y: state.startEventPos.y + (canvasPt.y - state.startPointerPos.y),
      };
      const pointSnapTarget = findNearestSnapTarget(
        nextPos,
        (target) => target.kind === 'event' && target.eventId === state.eventId,
      );
      const curveSnapTarget = findNearestBranchCurveTarget(nextPos);
      const snapTarget = pickClosestSnapTarget(nextPos, [pointSnapTarget, curveSnapTarget]);
      const hasMoved =
        state.hasMoved ||
        Math.hypot(nextPos.x - state.startEventPos.x, nextPos.y - state.startEventPos.y) > MOVE_THRESHOLD_PX / zoom;

      return {
        ...state,
        currentCanvasPos: nextPos,
        hasMoved,
        snapTarget,
      };
    };

    const onMove = (e: PointerEvent) => {
      const canvasPt = toCanvasPoint(e);
      if (!canvasPt) return;

      if (eventPressState && e.pointerId === eventPressState.pointerId && !dragStateRef.current) {
        const movement = Math.hypot(
          canvasPt.x - eventPressState.startPointerPos.x,
          canvasPt.y - eventPressState.startPointerPos.y,
        );
        if (movement > MOVE_THRESHOLD_PX / zoom) {
          clearPendingEventPress();
          const initialDragState = computePreviewState(
            {
              eventId: eventPressState.eventId,
              pointerId: eventPressState.pointerId,
              startPointerPos: eventPressState.startPointerPos,
              startEventPos: eventPressState.startEventPos,
              currentCanvasPos: eventPressState.startEventPos,
              hasMoved: false,
              snapTarget: null,
              interaction: 'move',
            },
            canvasPt,
          );
          dragStateRef.current = initialDragState;
          setDragState(initialDragState);
          setMode('event-drag');
        }
        return;
      }

      const activeDragState = dragStateRef.current;
      if (!activeDragState || e.pointerId !== activeDragState.pointerId) return;

      const nextDragState = computePreviewState(activeDragState, canvasPt);
      dragStateRef.current = nextDragState;
      setDragState(nextDragState);
    };

    const onUp = (e: PointerEvent) => {
      if (eventPressState && e.pointerId === eventPressState.pointerId && !dragStateRef.current) {
        clearPendingEventPress();
        setEditingEventId(eventPressState.eventId);
        setMode('idle');
        return;
      }

      const activeDragState = dragStateRef.current;
      if (!activeDragState || e.pointerId !== activeDragState.pointerId) return;

      dragStateRef.current = null;
      setDragState(null);
      setMode('idle');

      if (!activeDragState.hasMoved) {
        if (activeDragState.interaction === 'move') {
          setEditingEventId(activeDragState.eventId);
        }
        return;
      }

      commitEventDrag(activeDragState);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [
    clearPendingEventPress,
    commitEventDrag,
    dragState,
    eventPressState,
    findNearestBranchCurveTarget,
    findNearestSnapTarget,
    mode,
    panX,
    panY,
    pickClosestSnapTarget,
    zoom,
  ]);

  // ── Branch handle drag (window-level) ─────────────────────────
  useEffect(() => {
    if (mode !== 'branch-drag' || !branchDragState) return;

    const branch = branches.find(b => b.id === branchDragState.branchId);
    if (!branch) return;

    const onMove = (e: PointerEvent) => {
      if (!svgRef.current) return;
      const svgPt = screenToCanvas({ x: e.clientX, y: e.clientY }, svgRef.current);
      const canvasPt = { x: (svgPt.x - panX) / zoom, y: (svgPt.y - panY) / zoom };

      if (branchDragState.handle === 'start' || branchDragState.handle === 'end') {
        const snapTarget = findNearestSnapTarget(canvasPt, (target) => {
          if (branchDragState.handle === 'start') {
            return target.kind === 'branch-anchor-start' && target.branchId === branchDragState.branchId;
          }
          return target.kind === 'branch-anchor-end' && target.branchId === branchDragState.branchId;
        });
        const nextPos = snapTarget?.point ?? canvasPt;
        setBranchDragState((prev) => {
          const nextState = prev ? { ...prev, snapTarget } : null;
          branchDragStateRef.current = nextState;
          return nextState;
        });

        const nextStartAnchor =
          branchDragState.handle === 'start'
            ? getEventAnchorFromSnapTarget(snapTarget)
            : branchDragState.origStartAnchor ?? null;
        const nextEndAnchor =
          branchDragState.handle === 'end'
            ? getEventAnchorFromSnapTarget(snapTarget)
            : branchDragState.origEndAnchor ?? null;

        if (branchDragState.handle === 'start') {
          setTimelineBranchAnchors(branchDragState.branchId, nextPos, branchDragState.origEndPos, {
            startAnchor: nextStartAnchor,
            endAnchor: nextEndAnchor,
          });
        } else {
          setTimelineBranchAnchors(branchDragState.branchId, branchDragState.origStartPos, nextPos, {
            startAnchor: nextStartAnchor,
            endAnchor: nextEndAnchor,
          });
        }
      } else if (branchDragState.handle === 'bend') {
        setBranchDragState((prev) => {
          const nextState = prev ? { ...prev, snapTarget: null } : null;
          branchDragStateRef.current = nextState;
          return nextState;
        });
        // Map Y position to bend value (0.05 - 0.95)
        const cp = branchCPMap.get(branchDragState.branchId);
        if (!cp) return;
        const totalWidth = cp.p3.x - cp.p0.x;
        if (totalWidth <= 0) return;
        const relX = Math.max(0, Math.min(1, (canvasPt.x - cp.p0.x) / totalWidth));
        const newBend = Math.max(0.05, Math.min(0.95, relX));
        setTimelineBranchGeometry(branchDragState.branchId, {
          laneOffset: canvasPt.y,
          bend: newBend,
          thickness: branch.geometry?.thickness ?? 1,
        });
      }
    };

    const onUp = () => {
      // Propagate shared anchor positions to ALL attached branches
      if (branchDragState) {
        const anchorEventId = branchDragState.handle === 'start'
          ? branchDragState.origStartAnchor?.eventId
          : branchDragState.origEndAnchor?.eventId;
        if (anchorEventId) {
          const evt = events.find(e => e.id === anchorEventId);
          if (evt?.position) {
            updateTimelineEventPosition(evt.id, evt.position);
          }
        }
      }
      branchDragStateRef.current = null;
      setBranchDragState(null);
      setMode('idle');
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [mode, branchDragState, branches, branchCPMap, zoom, panX, panY, setTimelineBranchAnchors, setTimelineBranchGeometry, findNearestSnapTarget, events, updateTimelineEventPosition]);

  // Branch handle pointer-down
  const handleBranchHandlePointerDown = useCallback(
    (branchId: string, handle: BranchHandle, e: React.PointerEvent) => {
      e.stopPropagation();
      startBranchDrag(branchId, handle);
    },
    [startBranchDrag]
  );

  // ── Background pointer events (pan) ─────────────────────────

  const handleBgPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      setBranchContextMenu(null);
      clearBranchSelection();
      // If clicking on background in draw mode, place a point
      if (drawModeBranchId) {
        const canvasPt = getCanvasPoint(e);
        if (canvasPt) {
          const existingOnBranch = branchEventsMap.get(drawModeBranchId) || [];
          const newEvent: TimelineEvent = {
            id: `event_${Date.now()}`,
            title: t('timeline.newEvent'),
            summary: '',
            branchId: drawModeBranchId,
            orderIndex: existingOnBranch.length,
            locationIds: [],
            participantCharacterIds: [],
            linkedSceneIds: [],
            linkedWorldItemIds: [],
            tags: [],
            importance: 'medium',
            position: canvasPt,
          };
          addTimelineEvent(newEvent);
          setEditingEventId(newEvent.id);
        }
        return;
      }
      setMode('panning');
      panStartRef.current = { x: e.clientX, y: e.clientY, panX, panY };
    },
    [panX, panY, drawModeBranchId, getCanvasPoint, branchEventsMap, addTimelineEvent, clearBranchSelection]
  );

  const handleBgPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== 'panning' || !panStartRef.current) return;
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      setPanX(panStartRef.current.panX + dx);
      setPanY(panStartRef.current.panY + dy);
    },
    [mode]
  );

  const handleBgPointerUp = useCallback(() => {
    if (mode === 'panning') setMode('idle');
  }, [mode]);

  // Wheel zoom — must use native listener with { passive: false } to allow preventDefault
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      setZoom(prevZoom => {
        const delta = -e.deltaY * 0.001;
        const newZoom = Math.min(4, Math.max(0.1, prevZoom * (1 + delta)));
        const scale = newZoom / prevZoom;
        const rect = el.getBoundingClientRect();
        const svgX = e.clientX - rect.left;
        const svgY = e.clientY - rect.top;
        setPanX(prev => svgX - scale * (svgX - prev));
        setPanY(prev => svgY - scale * (svgY - prev));
        return newZoom;
      });
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, []);

  // ── Branch path interaction ──────────────────────────────

  const handleBranchPathClick = useCallback(
    (branchId: string, _t: number, svgPoint: Point) => {
      setBranchContextMenu(null);
      setSelectedEntity('timeline_branch', branchId);
      if (drawModeBranchId === branchId) {
        const existingOnBranch = branchEventsMap.get(branchId) || [];
        const newEvent: TimelineEvent = {
          id: `event_${Date.now()}`,
          title: 'New Event',
          summary: '',
          branchId,
          orderIndex: existingOnBranch.length,
          locationIds: [],
          participantCharacterIds: [],
          linkedSceneIds: [],
          linkedWorldItemIds: [],
          tags: [],
          importance: 'medium',
          position: svgPoint,
        };
        addTimelineEvent(newEvent);
        setEditingEventId(newEvent.id);
      }
    },
    [drawModeBranchId, branchEventsMap, addTimelineEvent, setSelectedEntity]
  );

  const handleBranchPathContextMenu = useCallback(
    (branchId: string, _svgPoint: Point, clientPoint: Point) => {
      setSelectedEntity('timeline_branch', branchId);
      setDeleteConfirmBranchId(null);
      setBranchContextMenu({
        branchId,
        x: clientPoint.x,
        y: clientPoint.y,
      });
    },
    [setSelectedEntity]
  );

  const handleBranchPointerMove = useCallback(
    (_branchId: string, _t: number) => {},
    []
  );

  const handleBranchPointerLeave = useCallback(() => {}, []);

  // ── Event node interaction ───────────────────────────────

  const handleEventPointerDown = useCallback(
    (eventId: string, e: React.PointerEvent<SVGCircleElement>) => {
      if (e.button === 2) {
        e.preventDefault();
        e.stopPropagation();
        clearPendingEventPress();
        const attachment = findAttachedEndpoint(eventId);
        if (attachment) {
          startBranchDrag(attachment.branchId, attachment.handle);
        }
        return;
      }

      if (e.button !== 0) return;
      e.stopPropagation();
      setBranchContextMenu(null);
      clearBranchSelection();
      const canvasPt = getCanvasPoint(e);
      if (!canvasPt) return;

      e.currentTarget.setPointerCapture(e.pointerId);

      const startEventPos = eventPositions.get(eventId) || canvasPt;
      const nextPressState = {
        eventId,
        pointerId: e.pointerId,
        startPointerPos: canvasPt,
        startEventPos,
      };
      clearPendingEventPress();
      setEventPressState(nextPressState);
      eventPressTimerRef.current = window.setTimeout(() => {
        startEventDrag('drop', nextPressState);
        setEventPressState(null);
        eventPressTimerRef.current = null;
      }, LONG_PRESS_MS);
    },
    [
      clearBranchSelection,
      clearPendingEventPress,
      eventPositions,
      findAttachedEndpoint,
      getCanvasPoint,
      startBranchDrag,
      startEventDrag,
    ]
  );

  const handleEventPointerMove = useCallback(
    (_eventId: string, e: React.PointerEvent<SVGCircleElement>) => {
      // Update cursor for draw mode
      if (!svgRef.current) return;
      const screen = { x: e.clientX, y: e.clientY };
      const svgPt = screenToCanvas(screen, svgRef.current);
      setCursorPos({ x: (svgPt.x - panX) / zoom, y: (svgPt.y - panY) / zoom });
    },
    [mode, getCanvasPoint, panX, panY, zoom]
  );

  const handleEventPointerUp = useCallback(
    (_eventId: string) => {
      if (mode === 'idle') {
        setMode('idle');
      }
    },
    [mode]
  );

  const handleEventContextMenu = useCallback(
    () => {
      clearPendingEventPress();
    },
    [clearPendingEventPress],
  );

  const handleEventHover = useCallback(
    (eventId: string | null) => setHoveredEventId(eventId),
    []
  );

  useEffect(() => {
    if (!branchContextMenu) return;

    const closeMenu = () => setBranchContextMenu(null);
    window.addEventListener('click', closeMenu);
    window.addEventListener('contextmenu', closeMenu);
    window.addEventListener('keydown', closeMenu);

    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('contextmenu', closeMenu);
      window.removeEventListener('keydown', closeMenu);
    };
  }, [branchContextMenu]);

  useEffect(() => {
    if (!selectedBranchId) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;

      const activeElement = document.activeElement as HTMLElement | null;
      if (
        activeElement?.isContentEditable ||
        activeElement?.tagName === 'INPUT' ||
        activeElement?.tagName === 'TEXTAREA' ||
        activeElement?.tagName === 'SELECT'
      ) {
        return;
      }

      e.preventDefault();
      handleRequestDeleteBranch(selectedBranchId);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleRequestDeleteBranch, selectedBranchId]);

  // ── Right-click to cancel draw mode ───────────────────────

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (e.button === 2 && drawModeBranchId) {
        e.preventDefault();
        onDrawModeChange?.(null);
      }
    };
    window.addEventListener('contextmenu', handler);
    return () => window.removeEventListener('contextmenu', handler);
  }, [drawModeBranchId, onDrawModeChange]);

  // ── Render ──────────────────────────────────────────────────

  const editingEvent = events.find(e => e.id === editingEventId) ?? null;

  return (
    <div ref={containerRef} className="relative h-full w-full" data-testid="timeline-canvas">
      <svg
        ref={svgRef}
        className="h-full w-full"
        style={{ background: 'var(--bg, #0f0f17)' }}
        onPointerDown={handleBgPointerDown}
        onPointerMove={handleBgPointerMove}
        onPointerUp={handleBgPointerUp}
        data-testid="timeline-svg"
      >
        <defs>
          <pattern id="dot-grid" x={panX % 20} y={panY % 20} width={20} height={20} patternUnits="userSpaceOnUse">
            <circle cx={10} cy={10} r={0.5} fill="rgba(255,255,255,0.08)" />
          </pattern>
          <filter id="drop-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.3" />
          </filter>
          {/* Arrow marker */}
          <marker id="branch-arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto-start-reverse" markerUnits="strokeWidth">
            <polygon points="0 0, 10 3.5, 0 7" fill="context-stroke" />
          </marker>
        </defs>

        {/* Background */}
        <rect x={0} y={0} width="100%" height="100%" fill="url(#dot-grid)" />

        <g transform={`translate(${panX},${panY}) scale(${zoom})`}>
          {/* Branches */}
          <g id="branches">
            {branchRenderEntries.map((entry) => (
              <BranchEdge
                key={entry.branch.id}
                branch={entry.branch}
                controlPoints={entry.controlPoints}
                isDrawMode={drawModeBranchId === entry.branch.id}
                isSelected={selectedBranchId === entry.branch.id}
                renderMode={entry.renderMode}
                overlapHostBranchId={null}
                collapsedBranchIds={entry.memberBranchIds}
                showStartArrow={entry.showStartArrow}
                showEndArrow={entry.showEndArrow}
                onPathClick={handleBranchPathClick}
                onPathContextMenu={handleBranchPathContextMenu}
                onPointerMove={handleBranchPointerMove}
                onPointerLeave={handleBranchPointerLeave}
              />
            ))}
          </g>

          {/* Branch reshape handles — always visible, shown as draggable dots */}
          <g id="branch-handles">
            {branchRenderEntries.map((entry) => {
              const cp = entry.controlPoints;
              const color = entry.branch.color || '#38bdf8';
              const midX = (cp.p0.x + cp.p3.x) / 2;
              const midY = (cp.p0.y + cp.p3.y) / 2;
              return (
                <g key={`handle-${entry.branch.id}`}>
                  {/* Start anchor */}
                  <circle
                    cx={cp.p0.x} cy={cp.p0.y} r={6}
                    fill={color} opacity={0.7} stroke="white" strokeWidth={1.5}
                    style={{ cursor: 'grab' }}
                    onPointerDown={(e) => handleBranchHandlePointerDown(entry.branch.id, 'start', e)}
                    data-testid={`timeline-branch-handle-start-${entry.branch.id}`}
                    data-position-x={cp.p0.x}
                    data-position-y={cp.p0.y}
                  />
                  {/* End anchor */}
                  <circle
                    cx={cp.p3.x} cy={cp.p3.y} r={6}
                    fill={color} opacity={0.7} stroke="white" strokeWidth={1.5}
                    style={{ cursor: 'grab' }}
                    onPointerDown={(e) => handleBranchHandlePointerDown(entry.branch.id, 'end', e)}
                    data-testid={`timeline-branch-handle-end-${entry.branch.id}`}
                    data-position-x={cp.p3.x}
                    data-position-y={cp.p3.y}
                  />
                  {/* Bend handle (mid of curve) */}
                  <circle
                    cx={midX} cy={midY} r={5}
                    fill="none" stroke={color} strokeWidth={2} opacity={0.6}
                    strokeDasharray="2 2"
                    style={{ cursor: 'ns-resize' }}
                    onPointerDown={(e) => handleBranchHandlePointerDown(entry.branch.id, 'bend', e)}
                    data-testid={`timeline-branch-handle-bend-${entry.branch.id}`}
                    data-position-x={midX}
                    data-position-y={midY}
                  />
                </g>
              );
            })}
          </g>

          {/* Events */}
          <g id="events">
            {events.map(event => {
              const pos = eventPositions.get(event.id);
              if (!pos) return null;
              return (
                <TimelineEventNode
                  key={event.id}
                  event={event}
                  position={pos}
                  isHovered={hoveredEventId === event.id}
                  dragMode={dragState?.eventId === event.id ? dragState.interaction : null}
                  onPointerDown={handleEventPointerDown}
                  onPointerUp={handleEventPointerUp}
                  onPointerMove={handleEventPointerMove}
                  onContextMenu={handleEventContextMenu}
                  onHover={handleEventHover}
                />
              );
            })}
          </g>

          {/* Drag preview */}
          {(mode === 'event-drag' || mode === 'event-drop') && dragState && (
            <g
              id="drag-preview"
              data-testid={mode === 'event-drop' ? 'timeline-event-drop-preview' : 'timeline-event-drag-preview'}
            >
              <circle
                cx={dragState.snapTarget?.point.x ?? dragState.currentCanvasPos.x}
                cy={dragState.snapTarget?.point.y ?? dragState.currentCanvasPos.y}
                r={8}
                fill="#38bdf8"
                opacity={0.4}
                stroke="#38bdf8"
                strokeWidth={2}
                strokeDasharray={dragState.interaction === 'drop' ? '2 2' : '3 2'}
              />
              {dragState.snapTarget && (
                <circle
                  cx={dragState.snapTarget.point.x}
                  cy={dragState.snapTarget.point.y}
                  r={12}
                  fill="none"
                  stroke="#22c55e"
                  strokeWidth={2}
                  opacity={0.6}
                />
              )}
            </g>
          )}

          {mode === 'branch-drag' && branchDragState?.snapTarget && (
            <g id="branch-drag-preview">
              <circle
                cx={branchDragState.snapTarget.point.x}
                cy={branchDragState.snapTarget.point.y}
                r={12}
                fill="none"
                stroke="#22c55e"
                strokeWidth={2}
                opacity={0.6}
              />
            </g>
          )}

          {/* Draw mode cursor preview */}
          {drawModeBranchId && cursorPos && (
            <g id="draw-preview" data-testid="timeline-draw-preview">
              <circle
                cx={cursorPos.x}
                cy={cursorPos.y}
                r={5}
                fill="#38bdf8"
                opacity={0.3}
              />
            </g>
          )}
        </g>
      </svg>

      {branchContextMenu && (
        <div
          className="absolute z-20 min-w-[160px] rounded-2xl border border-white/10 bg-slate-950/95 p-2 shadow-[0_24px_60px_rgba(0,0,0,0.5)] backdrop-blur"
          style={{ left: branchContextMenu.x, top: branchContextMenu.y }}
          onClick={(e) => e.stopPropagation()}
          data-testid="timeline-branch-context-menu"
        >
          <button
            type="button"
            className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-red transition-colors hover:bg-red/10"
            onClick={() => handleRequestDeleteBranch(branchContextMenu.branchId)}
            data-testid={`timeline-branch-context-delete-${branchContextMenu.branchId}`}
          >
            {t('timeline.delete')}
          </button>
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteConfirmBranchId && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60"
          onClick={() => setDeleteConfirmBranchId(null)}
          data-testid="timeline-delete-confirm-overlay"
        >
          <div
            className="w-full max-w-sm overflow-hidden rounded-[28px] border border-border bg-bg-elev-1 shadow-2"
            onClick={(e) => e.stopPropagation()}
            data-testid="timeline-delete-confirm-dialog"
          >
            <div className="border-b border-border bg-bg-elev-2 px-6 py-4">
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-red">{t('timeline.confirmDelete')}</div>
            <div className="mt-1 text-sm font-semibold text-text">
              {t('timeline.confirmDeleteTitle', `Delete timeline "${branches.find(b => b.id === deleteConfirmBranchId)?.name ?? deleteConfirmBranchId}"?`).replace('{name}', branches.find(b => b.id === deleteConfirmBranchId)?.name ?? deleteConfirmBranchId)}
            </div>
          </div>
          <div className="p-4 text-sm text-text-2">
              {t('timeline.confirmDeleteBody')}
          </div>
            <div className="flex items-center justify-end gap-2 border-t border-border p-4">
              <button
                type="button"
                className="rounded-xl border border-border px-4 py-2 text-xs font-semibold text-text-2 hover:bg-hover"
                onClick={() => setDeleteConfirmBranchId(null)}
                data-testid="timeline-delete-confirm-cancel"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="rounded-xl bg-red px-4 py-2 text-xs font-black text-text-invert hover:brightness-110"
                onClick={() => handleDeleteBranch(deleteConfirmBranchId)}
                data-testid="timeline-delete-confirm-ok"
              >
                {t('timeline.delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Event edit modal (centered popup, not side drawer) */}
      {editingEvent && (
        <EventEditModal
          event={editingEvent}
          onClose={() => setEditingEventId(null)}
        />
      )}
    </div>
  );
}

// ── Helper ────────────────────────────────────────────────────

function computeSlotFromSnapTarget(
  existingEvents: TimelineEvent[],
  target: SnapTarget,
  eventCurveParams: Map<string, number>,
  movingEventId?: string,
): number {
  if (target.kind === 'branch-anchor-start') return 0;
  if (target.kind === 'branch-anchor-end') return existingEvents.length;
  if (target.kind === 'branch-curve') {
    const targetT = target.t ?? 0.5;
    const orderedEvents = existingEvents
      .filter((event) => event.id !== movingEventId)
      .sort((a, b) => (eventCurveParams.get(a.id) ?? 0.5) - (eventCurveParams.get(b.id) ?? 0.5));
    const insertionIndex = orderedEvents.findIndex((event) => (eventCurveParams.get(event.id) ?? 0.5) >= targetT);
    return insertionIndex >= 0 ? insertionIndex : orderedEvents.length;
  }
  if (typeof target.orderIndex === 'number') {
    return Math.min(Math.max(target.orderIndex, 0), existingEvents.length);
  }
  return existingEvents.length;
}

function getEventAnchorFromSnapTarget(target: SnapTarget | null): TimelineBranch['startAnchor'] {
  if (!target || target.kind !== 'event' || !target.eventId) {
    return null;
  }

  return {
    branchId: target.branchId,
    eventId: target.eventId,
  };
}
