// tests/e2e/p1/timeline_topology_import.spec.ts
import { expect, test } from '@playwright/test';

// ── Dense topology fixture ────────────────────────────────────────────────────

const DENSE_BRANCHES = [
  {
    id: 'branch_dense_main', name: 'Dense Main Arc', sortOrder: 10, mode: 'root',
    color: '#f59e0b', collapsed: false, parentBranchId: null, forkEventId: null,
    mergeEventId: null, mergeTargetBranchId: null, endMode: 'open',
    startAnchor: null, endAnchor: null,
    geometry: { laneOffset: 0, bend: 0.18, thickness: 1 },
    description: '',
  },
  {
    id: 'branch_dense_fork', name: 'Dense Fork Arc', sortOrder: 11, mode: 'forked',
    color: '#38bdf8', collapsed: false, parentBranchId: 'branch_dense_main',
    forkEventId: 'de_05', mergeEventId: 'de_13', mergeTargetBranchId: 'branch_dense_main',
    endMode: 'merge',
    startAnchor: { branchId: 'branch_dense_main', eventId: 'de_05' },
    endAnchor: { branchId: 'branch_dense_main', eventId: 'de_13' },
    geometry: { laneOffset: -120, bend: 0.3, thickness: 1 },
    description: '',
  },
];

const DENSE_EVENTS = [
  // 15 mainline events — every 3rd has a Chinese title (CJK truncation test)
  ...Array.from({ length: 15 }, (_, i) => ({
    id: `de_${String(i + 1).padStart(2, '0')}`,
    title: i % 3 === 0 ? `修炼突破第${i + 1}境界成功之战` : `Dense Main Event ${i + 1}`,
    summary: `Mainline dense event ${i + 1}`,
    time: `Arc ${Math.floor(i / 5) + 1}, Day ${(i % 5) + 1}`,
    branchId: 'branch_dense_main',
    orderIndex: i,
    importance: (i % 5 === 0 ? 'critical' : i % 3 === 0 ? 'high' : 'medium') as 'critical' | 'high' | 'medium',
    locationIds: [] as string[], participantCharacterIds: [] as string[],
    linkedSceneIds: [] as string[], linkedWorldItemIds: [] as string[],
    tags: [] as string[],
    sharedBranchIds: (i === 4 || i === 12) ? ['branch_dense_fork'] : [] as string[],
    colorToken: 'amber', layoutLock: false, modalStateHints: [] as string[],
  })),
  // 8 fork branch events — alternating English/Chinese titles
  ...Array.from({ length: 8 }, (_, i) => ({
    id: `df_${String(i + 1).padStart(2, '0')}`,
    title: i % 2 === 0 ? `支线势力扩张第${i + 1}阶段` : `Fork Side Event ${i + 1}`,
    summary: `Fork event ${i + 1}`,
    time: `Fork Day ${i + 1}`,
    branchId: 'branch_dense_fork',
    orderIndex: i,
    importance: 'medium' as 'medium',
    locationIds: [] as string[], participantCharacterIds: [] as string[],
    linkedSceneIds: [] as string[], linkedWorldItemIds: [] as string[],
    tags: [] as string[], sharedBranchIds: [] as string[],
    colorToken: 'sky', layoutLock: false, modalStateHints: [] as string[],
  })),
];

// ── Helpers ───────────────────────────────────────────────────────────────────

async function openTimeline(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

async function goToTimeline(page: import('@playwright/test').Page) {
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

async function injectDenseTopology(page: import('@playwright/test').Page) {
  await page.evaluate(
    ({ branches, events }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore not exposed — check store.ts DEV hook');
      store.setState((state: any) => ({
        timelineEvents: [...state.timelineEvents, ...events],
        timelineBranches: [...state.timelineBranches, ...branches],
      }));
    },
    { branches: DENSE_BRANCHES, events: DENSE_EVENTS },
  );
}

async function getAllNodePositions(page: import('@playwright/test').Page) {
  const nodeLocators = await page.locator('[data-testid^="timeline-event-node-"]').all();
  const positions: Array<{ id: string; x: number; y: number }> = [];
  for (const node of nodeLocators) {
    const id = (await node.getAttribute('data-testid')) ?? '';
    const x = Number(await node.getAttribute('data-position-x'));
    const y = Number(await node.getAttribute('data-position-y'));
    if (!isNaN(x) && !isNaN(y)) positions.push({ id, x, y });
  }
  return positions;
}

// ── Suite 1: Seed-project topology ───────────────────────────────────────────

test.describe('Timeline topology: seed project', () => {
  test.beforeEach(async ({ page }) => {
    await openTimeline(page);
  });

  test('canonical event nodes are visible', async ({ page }) => {
    await expect(page.getByTestId('timeline-event-node-event_arrival')).toBeVisible();
    await expect(page.getByTestId('timeline-event-node-event_bridge')).toBeVisible();
    await expect(page.getByTestId('timeline-event-node-event_shard')).toBeVisible();
  });

  test('seed event nodes do not overlap (pairwise distance > 20px)', async ({ page }) => {
    const positions = await getAllNodePositions(page);
    expect(positions.length).toBeGreaterThanOrEqual(3);
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[i].x - positions[j].x;
        const dy = positions[i].y - positions[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        expect(dist, `overlap: ${positions[i].id} vs ${positions[j].id}`).toBeGreaterThan(20);
      }
    }
  });

  test('multiple branch lane segments exist', async ({ page }) => {
    // Branch segments are transparent SVG hit-targets; check DOM presence, not visual visibility
    await expect(page.getByTestId('timeline-branch-segment-branch_main')).toBeAttached();
    await expect(page.getByTestId('timeline-branch-segment-branch_shadow')).toBeAttached();
    await expect(page.getByTestId('timeline-branch-segment-branch_public')).toBeAttached();
  });

  test('branch lanes are visually separated (y-gap > 50px)', async ({ page }) => {
    const mainHandle = page.getByTestId('timeline-branch-handle-middle-branch_main');
    const shadowHandle = page.getByTestId('timeline-branch-handle-middle-branch_shadow');
    await expect(mainHandle).toBeVisible();
    await expect(shadowHandle).toBeVisible();
    const mainY = Number(await mainHandle.getAttribute('data-position-y'));
    const shadowY = Number(await shadowHandle.getAttribute('data-position-y'));
    expect(Math.abs(mainY - shadowY)).toBeGreaterThan(50);
  });

  test('event label text is non-empty', async ({ page }) => {
    const node = page.getByTestId('timeline-event-node-event_arrival');
    await expect(node).toBeVisible();
    const labelText = await node.locator('text').textContent();
    expect((labelText ?? '').trim().length).toBeGreaterThan(0);
  });

  test('canvas has non-trivial dimensions', async ({ page }) => {
    const box = await page.getByTestId('timeline-canvas').boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(200);
    expect(box!.height).toBeGreaterThan(100);
  });
});

// ── Suite 2: Dense topology injection ────────────────────────────────────────

test.describe('Timeline topology: dense imported events', () => {
  test.beforeEach(async ({ page }) => {
    // goto first, inject into live store, then navigate to timeline (avoids reload wiping state)
    await page.goto('/');
    await injectDenseTopology(page);
    await goToTimeline(page);
  });

  test('at least 20 event nodes are visible after dense injection', async ({ page }) => {
    const positions = await getAllNodePositions(page);
    expect(positions.length).toBeGreaterThanOrEqual(20);
  });

  test('dense nodes do not overlap (pairwise distance > 15px)', async ({ page }) => {
    const positions = await getAllNodePositions(page);
    expect(positions.length).toBeGreaterThanOrEqual(20);
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[i].x - positions[j].x;
        const dy = positions[i].y - positions[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        expect(dist, `overlap: ${positions[i].id} vs ${positions[j].id}`).toBeGreaterThan(15);
      }
    }
  });

  test('dense branch lane segments are present', async ({ page }) => {
    // Branch segments are transparent SVG hit-targets; check DOM presence, not visual visibility
    await expect(page.getByTestId('timeline-branch-segment-branch_dense_main')).toBeAttached();
    await expect(page.getByTestId('timeline-branch-segment-branch_dense_fork')).toBeAttached();
  });

  test('dense branch lanes are visually separated (y-gap > 50px) if handles exposed', async ({ page }) => {
    const mainHandle = page.getByTestId('timeline-branch-handle-middle-branch_dense_main');
    const forkHandle = page.getByTestId('timeline-branch-handle-middle-branch_dense_fork');
    const mainVisible = await mainHandle.isVisible();
    const forkVisible = await forkHandle.isVisible();
    if (mainVisible && forkVisible) {
      const mainY = Number(await mainHandle.getAttribute('data-position-y'));
      const forkY = Number(await forkHandle.getAttribute('data-position-y'));
      expect(Math.abs(mainY - forkY)).toBeGreaterThan(50);
    }
  });

  test('CJK-titled dense events render with labels ≤ 11 chars', async ({ page }) => {
    // de_01 title '修炼突破第1境界成功之战' is 11 CJK chars (visual width 22 > limit 18)
    // After CJK-aware truncation, rendered label should be ≤ 10 chars + ellipsis
    const cjkNode = page.getByTestId('timeline-event-node-de_01');
    await expect(cjkNode).toBeVisible();
    const labelText = await cjkNode.locator('text').textContent();
    const label = (labelText ?? '').trim();
    expect(label.length).toBeGreaterThan(0);
    expect(label.length).toBeLessThanOrEqual(11);
  });

  test('canvas dimensions expand to accommodate dense events', async ({ page }) => {
    const box = await page.getByTestId('timeline-canvas').boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(300);
    expect(box!.height).toBeGreaterThan(100);
  });
});

// ── Suite 3: Responsive viewports ─────────────────────────────────────────────

test.describe('Timeline topology: responsive viewports', () => {
  const VIEWPORTS = [
    { label: '1280x800 MacBook', width: 1280, height: 800 },
    { label: '1440x900', width: 1440, height: 900 },
    { label: '1728x1117 large Mac', width: 1728, height: 1117 },
    { label: '1024x768 constrained', width: 1024, height: 768 },
  ];

  for (const vp of VIEWPORTS) {
    test(`canvas and primary nodes visible at ${vp.label}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await openTimeline(page);
      await expect(page.getByTestId('timeline-canvas')).toBeVisible();
      await expect(page.getByTestId('timeline-event-node-event_arrival')).toBeVisible();
    });
  }
});
