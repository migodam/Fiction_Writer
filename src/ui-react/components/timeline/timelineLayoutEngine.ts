import { buildSegmentedSPath, fanLaneOffset, type Point, pointOnPolyline } from './bezierMath.js';

export interface TimelineLayoutEventInput {
  id: string;
  branchId: string;
  orderIndex?: number;
  rank?: number;
  chapterIndex?: number;
  laneId?: string | number | null;
  topologyHints?: {
    rank?: number;
    laneId?: string | number | null;
    chapterIndex?: number;
    clusterKey?: string | null;
  };
  bbox?: Partial<TimelineNodeBox>;
}

export interface TimelineLayoutBranchInput {
  id: string;
  sortOrder?: number;
  parentBranchId?: string | null;
  laneId?: string | number | null;
  eventCountHint?: number;
  topologyHints?: {
    laneId?: string | number | null;
    rankStart?: number;
    rankEnd?: number;
    expectedEventCount?: number;
  };
}

export interface TimelineNodeBox {
  width: number;
  height: number;
}

export interface TimelineLayoutOptions {
  baseWidth?: number;
  edgePadding?: number;
  minEventSpacing?: number;
  laneSpacing?: number;
  clusterThreshold?: number;
  clusterRankEpsilon?: number;
  eventBox?: TimelineNodeBox;
  clusterBox?: TimelineNodeBox;
}

export interface TimelineLayoutBranchGeometry {
  branchId: string;
  laneIndex: number;
  laneY: number;
  virtualLength: number;
  eventCount: number;
  rankStart: number;
  rankEnd: number;
  pathPoints: Point[];
  path: string;
}

export interface TimelineLayoutNodeGeometry {
  id: string;
  branchId: string;
  rank: number;
  order: number;
  x: number;
  y: number;
  bbox: TimelineNodeBox;
  renderMode: 'node' | 'clustered';
  clusterId?: string;
}

export interface TimelineLayoutClusterGeometry {
  id: string;
  branchId: string;
  eventIds: string[];
  rankStart: number;
  rankEnd: number;
  x: number;
  y: number;
  bbox: TimelineNodeBox;
  count: number;
}

export interface TimelineLayoutResult {
  width: number;
  height: number;
  branches: TimelineLayoutBranchGeometry[];
  nodes: TimelineLayoutNodeGeometry[];
  clusters: TimelineLayoutClusterGeometry[];
}

interface RankedEvent {
  input: TimelineLayoutEventInput;
  rank: number;
  order: number;
  branchOrder: number;
  clusterKey: string | null;
}

interface BranchContext {
  input: TimelineLayoutBranchInput;
  events: RankedEvent[];
  laneIndex: number;
  laneY: number;
  rankStart: number;
  rankEnd: number;
  virtualLength: number;
  pathPoints: Point[];
}

const DEFAULT_OPTIONS: Required<TimelineLayoutOptions> = {
  baseWidth: 2000,
  edgePadding: 240,
  minEventSpacing: 96,
  laneSpacing: 170,
  clusterThreshold: 4,
  clusterRankEpsilon: 0.0001,
  eventBox: { width: 88, height: 54 },
  clusterBox: { width: 104, height: 62 },
};

const SUBLANE_STEP_PX = 42;
const MAX_RELAXATION_PASSES = 6;

export function layoutTimelineV2(
  events: TimelineLayoutEventInput[],
  branches: TimelineLayoutBranchInput[],
  options: TimelineLayoutOptions = {},
): TimelineLayoutResult {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const sortedBranches = normalizeBranches(events, branches);
  const branchContexts = buildBranchContexts(events, sortedBranches, opts);
  const branchGeometries: TimelineLayoutBranchGeometry[] = [];
  const nodes: TimelineLayoutNodeGeometry[] = [];
  const clusters: TimelineLayoutClusterGeometry[] = [];

  for (const branch of branchContexts) {
    branchGeometries.push({
      branchId: branch.input.id,
      laneIndex: branch.laneIndex,
      laneY: branch.laneY,
      virtualLength: branch.virtualLength,
      eventCount: branch.events.length,
      rankStart: branch.rankStart,
      rankEnd: branch.rankEnd,
      pathPoints: branch.pathPoints,
      path: buildSegmentedSPath(branch.pathPoints),
    });

    const { nodeEntries, clusterEntries } = placeBranchEvents(branch, opts);
    nodes.push(...nodeEntries);
    clusters.push(...clusterEntries);
  }

  const visibleNodes = relaxCollisions([...nodes.filter((node) => node.renderMode === 'node'), ...clusters], opts);
  const relaxedById = new Map(visibleNodes.map((entry) => [entry.id, entry]));
  const relaxedNodes = nodes.map((node) => {
    if (node.renderMode !== 'node') return node;
    const relaxed = relaxedById.get(node.id);
    return relaxed ? { ...node, x: relaxed.x, y: relaxed.y } : node;
  });
  const relaxedClusters = clusters.map((cluster) => {
    const relaxed = relaxedById.get(cluster.id);
    return relaxed ? { ...cluster, x: relaxed.x, y: relaxed.y } : cluster;
  });

  const width = Math.max(opts.baseWidth, ...branchGeometries.map((branch) => branch.virtualLength + opts.edgePadding * 2));
  const minY = Math.min(0, ...branchContexts.map((branch) => branch.laneY));
  const maxY = Math.max(0, ...branchContexts.map((branch) => branch.laneY));
  const height = maxY - minY + opts.laneSpacing * 2;

  return {
    width,
    height,
    branches: branchGeometries,
    nodes: relaxedNodes,
    clusters: relaxedClusters,
  };
}

export function bboxForNode(node: Pick<TimelineLayoutNodeGeometry | TimelineLayoutClusterGeometry, 'x' | 'y' | 'bbox'>) {
  return {
    left: node.x - node.bbox.width / 2,
    right: node.x + node.bbox.width / 2,
    top: node.y - node.bbox.height / 2,
    bottom: node.y + node.bbox.height / 2,
  };
}

export function boxesOverlap(
  left: Pick<TimelineLayoutNodeGeometry | TimelineLayoutClusterGeometry, 'x' | 'y' | 'bbox'>,
  right: Pick<TimelineLayoutNodeGeometry | TimelineLayoutClusterGeometry, 'x' | 'y' | 'bbox'>,
  padding = 0,
): boolean {
  const a = bboxForNode(left);
  const b = bboxForNode(right);
  return !(
    a.right + padding <= b.left ||
    b.right + padding <= a.left ||
    a.bottom + padding <= b.top ||
    b.bottom + padding <= a.top
  );
}

function normalizeBranches(
  events: TimelineLayoutEventInput[],
  branches: TimelineLayoutBranchInput[],
): TimelineLayoutBranchInput[] {
  const byId = new Map(branches.map((branch) => [branch.id, branch]));
  for (const event of events) {
    if (!byId.has(event.branchId)) {
      byId.set(event.branchId, { id: event.branchId });
    }
  }

  return [...byId.values()].sort((left, right) => {
    const orderDelta = (left.sortOrder ?? Number.MAX_SAFE_INTEGER) - (right.sortOrder ?? Number.MAX_SAFE_INTEGER);
    return orderDelta || left.id.localeCompare(right.id);
  });
}

function buildBranchContexts(
  events: TimelineLayoutEventInput[],
  branches: TimelineLayoutBranchInput[],
  opts: Required<TimelineLayoutOptions>,
): BranchContext[] {
  const eventBuckets = new Map<string, TimelineLayoutEventInput[]>();
  events.forEach((event) => {
    const bucket = eventBuckets.get(event.branchId) ?? [];
    bucket.push(event);
    eventBuckets.set(event.branchId, bucket);
  });

  const laneByKey = new Map<string, number>();
  return branches.map((branch, branchOrder) => {
    const laneKey = String(branch.topologyHints?.laneId ?? branch.laneId ?? branch.id);
    const laneIndex = resolveLaneIndex(laneKey, branchOrder, laneByKey);
    const rawEvents = eventBuckets.get(branch.id) ?? [];
    const rankedEvents = rankEvents(rawEvents, branchOrder);
    const eventCount = Math.max(
      rawEvents.length,
      branch.eventCountHint ?? 0,
      branch.topologyHints?.expectedEventCount ?? 0,
      1,
    );
    const ranks = rankedEvents.map((event) => event.rank);
    const rankStart = branch.topologyHints?.rankStart ?? Math.min(0, ...ranks);
    const rankEnd = Math.max(branch.topologyHints?.rankEnd ?? 0, rankStart + 1, ...ranks);
    const virtualLength = Math.max(opts.baseWidth, eventCount * opts.minEventSpacing + opts.edgePadding);
    const laneY = laneIndex * opts.laneSpacing;

    return {
      input: branch,
      events: rankedEvents,
      laneIndex,
      laneY,
      rankStart,
      rankEnd,
      virtualLength,
      pathPoints: buildBranchPathPoints(virtualLength, laneY, eventCount, opts),
    };
  });
}

function resolveLaneIndex(laneKey: string, branchOrder: number, laneByKey: Map<string, number>): number {
  const numericLane = Number(laneKey);
  if (Number.isFinite(numericLane) && laneKey.trim() !== '') return numericLane;

  const existing = laneByKey.get(laneKey);
  if (existing !== undefined) return existing;

  const laneIndex = branchOrder === 0 ? 0 : fanLaneOffset(branchOrder - 1, 1);
  laneByKey.set(laneKey, laneIndex);
  return laneIndex;
}

function rankEvents(events: TimelineLayoutEventInput[], branchOrder: number): RankedEvent[] {
  return events
    .map((event, fallbackOrder) => {
      const order = event.orderIndex ?? fallbackOrder;
      return {
        input: event,
        rank: event.topologyHints?.rank ?? event.rank ?? event.chapterIndex ?? event.topologyHints?.chapterIndex ?? order,
        order,
        branchOrder,
        clusterKey: event.topologyHints?.clusterKey ?? null,
      };
    })
    .sort((left, right) => left.rank - right.rank || left.order - right.order || left.input.id.localeCompare(right.input.id));
}

function buildBranchPathPoints(
  virtualLength: number,
  laneY: number,
  eventCount: number,
  opts: Required<TimelineLayoutOptions>,
): Point[] {
  const startX = opts.edgePadding / 2;
  const endX = virtualLength + opts.edgePadding / 2;
  if (eventCount < 48) {
    return [
      { x: startX, y: laneY },
      { x: endX, y: laneY },
    ];
  }

  // Dense branches get deterministic S-curve segments so 100+ events can keep
  // readable x spacing while avoiding one visually endless straight rail.
  const segmentCount = Math.min(5, Math.max(3, Math.ceil(eventCount / 36)));
  const amplitude = Math.min(opts.laneSpacing * 0.28, 56);
  const points: Point[] = [];
  for (let index = 0; index <= segmentCount; index++) {
    const t = index / segmentCount;
    const wave = index === 0 || index === segmentCount ? 0 : (index % 2 === 0 ? -1 : 1);
    points.push({
      x: startX + (endX - startX) * t,
      y: laneY + wave * amplitude,
    });
  }
  return points;
}

function placeBranchEvents(branch: BranchContext, opts: Required<TimelineLayoutOptions>) {
  const nodeEntries: TimelineLayoutNodeGeometry[] = [];
  const clusterEntries: TimelineLayoutClusterGeometry[] = [];
  const denseGroups = findDenseGroups(branch.events, opts);
  const clusteredEventIds = new Set<string>();

  denseGroups.forEach((group, index) => {
    const eventIds = group.map((event) => event.input.id);
    eventIds.forEach((id) => clusteredEventIds.add(id));
    const rankStart = group[0].rank;
    const rankEnd = group[group.length - 1].rank;
    const centerRank = (rankStart + rankEnd) / 2;
    const point = pointOnPolyline(branch.pathPoints, rankToT(centerRank, branch.rankStart, branch.rankEnd));
    const clusterId = `${branch.input.id}:cluster:${index}:${rankStart}`;
    clusterEntries.push({
      id: clusterId,
      branchId: branch.input.id,
      eventIds,
      rankStart,
      rankEnd,
      x: point.x,
      y: point.y,
      bbox: opts.clusterBox,
      count: eventIds.length,
    });
  });

  branch.events.forEach((event) => {
    const point = pointOnPolyline(branch.pathPoints, rankToT(event.rank, branch.rankStart, branch.rankEnd));
    const clusterId = clusterEntries.find((cluster) => cluster.eventIds.includes(event.input.id))?.id;
    nodeEntries.push({
      id: event.input.id,
      branchId: branch.input.id,
      rank: event.rank,
      order: event.order,
      x: point.x,
      y: point.y,
      bbox: { ...opts.eventBox, ...event.input.bbox },
      renderMode: clusteredEventIds.has(event.input.id) ? 'clustered' : 'node',
      clusterId,
    });
  });

  return { nodeEntries, clusterEntries };
}

function findDenseGroups(events: RankedEvent[], opts: Required<TimelineLayoutOptions>): RankedEvent[][] {
  const groups: RankedEvent[][] = [];
  let current: RankedEvent[] = [];

  for (const event of events) {
    const previous = current[current.length - 1];
    const sameExplicitCluster = previous?.clusterKey && previous.clusterKey === event.clusterKey;
    const sameRank = previous && Math.abs(previous.rank - event.rank) <= opts.clusterRankEpsilon;

    if (!previous || sameExplicitCluster || sameRank) {
      current.push(event);
    } else {
      if (current.length >= opts.clusterThreshold) groups.push(current);
      current = [event];
    }
  }

  if (current.length >= opts.clusterThreshold) groups.push(current);
  return groups;
}

function rankToT(rank: number, rankStart: number, rankEnd: number): number {
  const span = rankEnd - rankStart || 1;
  const pad = 0.04;
  return pad + ((rank - rankStart) / span) * (1 - pad * 2);
}

function relaxCollisions<T extends TimelineLayoutNodeGeometry | TimelineLayoutClusterGeometry>(
  entries: T[],
  opts: Required<TimelineLayoutOptions>,
): T[] {
  const relaxed = entries
    .map((entry) => ({ ...entry }))
    .sort((left, right) => left.x - right.x || left.y - right.y || left.id.localeCompare(right.id));

  for (let pass = 0; pass < MAX_RELAXATION_PASSES; pass++) {
    let changed = false;
    for (let index = 1; index < relaxed.length; index++) {
      const current = relaxed[index];
      for (let prevIndex = index - 1; prevIndex >= 0; prevIndex--) {
        const previous = relaxed[prevIndex];
        if (current.x - previous.x > opts.eventBox.width + opts.minEventSpacing) break;
        if (!boxesOverlap(current, previous, 8)) continue;

        const direction = (index + pass) % 2 === 0 ? 1 : -1;
        current.y += direction * SUBLANE_STEP_PX;
        changed = true;
      }
    }
    if (!changed) break;
  }

  return relaxed;
}
