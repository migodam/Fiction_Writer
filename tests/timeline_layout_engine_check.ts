import assert from 'node:assert/strict';
import {
  boxesOverlap,
  layoutTimelineV2,
  type TimelineLayoutBranchInput,
  type TimelineLayoutEventInput,
} from '../src/ui-react/components/timeline/timelineLayoutEngine.js';

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

console.log(`timeline layout engine check passed: ${events.length} events, ${layout.clusters.length} clusters`);
