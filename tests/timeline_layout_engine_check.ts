import assert from 'node:assert/strict';
import {
  boxesOverlap,
  layoutTimelineV2,
  placeTimelineLabels,
  type TimelineLayoutBranchInput,
  type TimelineLayoutEventInput,
} from '../src/ui-react/components/timeline/timelineLayoutEngine.js';
import {
  collectTimelineSyncEntityFieldMismatches,
  collectTimelineSyncSchemaMissingFields,
} from '../src/ui-react/components/timeline/timelineSyncAnalysis.js';
import type { TimelineBranch, TimelineEvent } from '../src/ui-react/models/project.js';

const branches: TimelineLayoutBranchInput[] = [
  { id: 'branch-main', sortOrder: 0, laneId: 0 },
  { id: 'branch-shadow', sortOrder: 1, parentBranchId: 'branch-main', laneId: 1 },
  { id: 'branch-alt', sortOrder: 2, parentBranchId: 'branch-main', laneId: -1 },
  { id: 'branch-dense', sortOrder: 3, laneId: 2, eventCountHint: 120 },
];

const events: TimelineLayoutEventInput[] = [];
for (let index = 0; index < 105; index++) {
  const branchId = branches[index % 3].id;
  events.push({
    id: `event-${index.toString().padStart(3, '0')}`,
    branchId,
    orderIndex: Math.floor(index / 3),
    rank: Math.floor(index / 3),
    chapterIndex: Math.floor(index / 10),
  });
}

for (let index = 0; index < 16; index++) {
  events.push({
    id: `dense-same-rank-${index.toString().padStart(2, '0')}`,
    branchId: 'branch-dense',
    orderIndex: index,
    rank: 7,
    topologyHints: { clusterKey: 'dense-chapter-7' },
  });
}

const layout = layoutTimelineV2(events, branches);
const visible = [
  ...layout.nodes.filter((node) => node.renderMode === 'node'),
  ...layout.clusters,
];

for (let left = 0; left < visible.length; left++) {
  for (let right = left + 1; right < visible.length; right++) {
    assert.equal(
      boxesOverlap(visible[left], visible[right], 0),
      false,
      `${visible[left].id} overlaps ${visible[right].id}`,
    );
  }
}

const denseBranch = layout.branches.find((branch) => branch.branchId === 'branch-dense');
const mainBranch = layout.branches.find((branch) => branch.branchId === 'branch-main');
assert.ok(denseBranch && mainBranch, 'expected branch geometries');
assert.ok(
  denseBranch.virtualLength > mainBranch.virtualLength,
  `dense branch length ${denseBranch.virtualLength} should exceed main ${mainBranch.virtualLength}`,
);

for (const branch of layout.branches) {
  const branchNodes = layout.nodes
    .filter((node) => node.branchId === branch.branchId)
    .sort((left, right) => left.rank - right.rank || left.order - right.order || left.id.localeCompare(right.id));

  for (let index = 1; index < branchNodes.length; index++) {
    assert.ok(
      branchNodes[index].x + 0.0001 >= branchNodes[index - 1].x,
      `${branch.branchId} x should be monotonic at ${branchNodes[index - 1].id} -> ${branchNodes[index].id}`,
    );
  }
}

const denseCluster = layout.clusters.find((cluster) => cluster.branchId === 'branch-dense');
assert.ok(denseCluster, 'dense same-rank events should be represented as a cluster');
assert.equal(denseCluster.count, 16);
assert.equal(layout.nodes.filter((node) => node.renderMode === 'clustered' && node.clusterId === denseCluster.id).length, 16);

const denseLabels = Array.from({ length: 36 }, (_, index) => ({
  id: `label-event-${index.toString().padStart(2, '0')}`,
  title: index % 3 === 0 ? `Dense Imported Event ${index} With Long Label` : `密集事件第${index}阶段关键节点`,
  x: 100 + index * 42,
  y: index % 2 === 0 ? 400 : 406,
  importance: index % 12 === 0 ? 'critical' : index % 9 === 0 ? 'high' : index % 3 === 0 ? 'medium' : 'low',
  nodeRadius: index % 12 === 0 ? 13 : index % 9 === 0 ? 10 : 8,
}));
const labelPlacements = placeTimelineLabels(denseLabels);
const visibleLabels = denseLabels
  .map((label) => ({ label, placement: labelPlacements.get(label.id) }))
  .filter((entry): entry is { label: (typeof denseLabels)[number]; placement: NonNullable<ReturnType<typeof labelPlacements.get>> } => Boolean(entry.placement?.visible));

assert.ok(visibleLabels.length >= 10, 'dense layout should keep high-value labels visible');
assert.ok(
  denseLabels
    .filter((label) => label.importance === 'critical' || label.importance === 'high')
    .every((label) => labelPlacements.get(label.id)?.visible),
  'critical/high dense labels should not be hidden',
);

for (let left = 0; left < visibleLabels.length; left++) {
  for (let right = left + 1; right < visibleLabels.length; right++) {
    assert.equal(
      labelBoxesOverlap(visibleLabels[left], visibleLabels[right]),
      false,
      `${visibleLabels[left].label.id} label overlaps ${visibleLabels[right].label.id}`,
    );
  }
}

const backendBranch: TimelineBranch = {
  id: 'branch_main',
  name: 'Main',
  sortOrder: 0,
};
const frontendBranch: TimelineBranch = {
  ...backendBranch,
  anchorStartPos: { x: 80, y: 0 },
  anchorEndPos: { x: 1200, y: 0 },
  endAnchor: null,
  endMode: 'open',
  mergeEventId: null,
  mergeTargetBranchId: null,
};
const backendEvent: TimelineEvent = {
  id: 'event_dense',
  title: 'Dense Event',
  summary: '',
  branchId: 'branch_main',
  orderIndex: 0,
  locationIds: [],
  participantCharacterIds: [],
  linkedSceneIds: [],
  linkedWorldItemIds: [],
  tags: [],
};
const frontendEvent: TimelineEvent = {
  ...backendEvent,
  position: { x: 160, y: 0 },
  sharedBranchIds: [],
  layoutLock: false,
  modalStateHints: [],
};

assert.deepEqual(
  collectTimelineSyncSchemaMissingFields(
    [frontendBranch],
    [frontendEvent],
    new Set(['id', 'name', 'sortOrder']),
    new Set([
      'id',
      'title',
      'summary',
      'branchId',
      'orderIndex',
      'locationIds',
      'participantCharacterIds',
      'linkedSceneIds',
      'linkedWorldItemIds',
      'tags',
    ]),
  ),
  [],
  'derived/runtime timeline fields should not be classified as missing schema fields',
);
assert.deepEqual(
  collectTimelineSyncEntityFieldMismatches([backendBranch], [frontendBranch], [backendEvent], [frontendEvent]),
  [],
  'derived/runtime timeline fields should not be classified as entity field mismatches',
);

console.log(
  `timeline layout engine check passed: ${events.length} events, ${layout.clusters.length} clusters, ${visibleLabels.length}/${denseLabels.length} labels visible`,
);

function labelBoxesOverlap(
  left: { label: { x: number; y: number }; placement: { dx: number; dy: number; width: number; height: number } },
  right: { label: { x: number; y: number }; placement: { dx: number; dy: number; width: number; height: number } },
) {
  const leftBox = labelBox(left);
  const rightBox = labelBox(right);
  return !(
    leftBox.right <= rightBox.left ||
    rightBox.right <= leftBox.left ||
    leftBox.bottom <= rightBox.top ||
    rightBox.bottom <= leftBox.top
  );
}

function labelBox(entry: {
  label: { x: number; y: number };
  placement: { dx: number; dy: number; width: number; height: number };
}) {
  const x = entry.label.x + entry.placement.dx;
  const baselineY = entry.label.y + entry.placement.dy;
  return {
    left: x - entry.placement.width / 2,
    right: x + entry.placement.width / 2,
    top: baselineY - entry.placement.height,
    bottom: baselineY,
  };
}
