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
  // 32 mainline events — every 3rd has a Chinese title (CJK truncation test)
  ...Array.from({ length: 32 }, (_, i) => ({
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
    sharedBranchIds: (i === 4 || i === 12 || i === 24) ? ['branch_dense_fork'] : [] as string[],
    colorToken: 'amber', layoutLock: false, modalStateHints: [] as string[],
  })),
  // 10 fork branch events — alternating English/Chinese titles
  ...Array.from({ length: 10 }, (_, i) => ({
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

async function getVisibleLabelBoxes(page: import('@playwright/test').Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll<SVGTextElement>('[data-testid^="timeline-event-label-"]'))
      .map((label) => {
        const rect = label.getBoundingClientRect();
        return {
          id: label.getAttribute('data-testid') || '',
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
      })
      .filter((r) => r.width > 0 && r.height > 0),
  );
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

  test('at least 30 event nodes are visible after dense injection', async ({ page }) => {
    const positions = await getAllNodePositions(page);
    expect(positions.length).toBeGreaterThanOrEqual(30);
  });

  test('dense nodes do not overlap (pairwise distance > 15px)', async ({ page }) => {
    const positions = await getAllNodePositions(page);
    expect(positions.length).toBeGreaterThanOrEqual(30);
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[i].x - positions[j].x;
        const dy = positions[i].y - positions[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        expect(dist, `overlap: ${positions[i].id} vs ${positions[j].id}`).toBeGreaterThan(15);
      }
    }
  });

  test('dense event labels do not overlap and hidden labels still expose tooltip', async ({ page }) => {
    // Wait for at least one label to be visible before reading all bounding boxes
    await expect(page.locator('[data-testid^="timeline-event-label-"]').first()).toBeVisible({ timeout: 5000 });
    const labelBoxes = await getVisibleLabelBoxes(page);
    // With 42 injected events the layout engine must place at least 20 visible labels
    expect(labelBoxes.length).toBeGreaterThan(20);

    for (let i = 0; i < labelBoxes.length; i++) {
      for (let j = i + 1; j < labelBoxes.length; j++) {
        const overlap = !(
          labelBoxes[i].right <= labelBoxes[j].left ||
          labelBoxes[j].right <= labelBoxes[i].left ||
          labelBoxes[i].bottom <= labelBoxes[j].top ||
          labelBoxes[j].bottom <= labelBoxes[i].top
        );
        expect(overlap, `label overlap: ${labelBoxes[i].id} vs ${labelBoxes[j].id}`).toBe(false);
      }
    }

    const hiddenNodes = page.locator('[data-testid^="timeline-event-node-"][data-label-visible="false"]');
    if ((await hiddenNodes.count()) > 0) {
      const firstHidden = hiddenNodes.first();
      const testId = (await firstHidden.getAttribute('data-testid')) || '';
      const eventId = testId.replace('timeline-event-node-', '');
      await page.getByTestId(`timeline-event-hitarea-${eventId}`).dispatchEvent('pointerover', { bubbles: true });
      await expect(page.getByTestId(`timeline-event-tooltip-${eventId}`)).toBeVisible();
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

// ── Suite 4: Proposal acceptance topology ─────────────────────────────────────

test.describe('Timeline topology: proposal acceptance path', () => {
  test('4-branch import: proposal acceptance path preserves all 4 branches after reload', async ({ page }) => {
    await openTimeline(page);

    const now = new Date().toISOString();
    const fourBranchProposals = [
      // Branches (priority 2 in applyImportPackageBatches)
      {
        id: 'prop_w3_branch_main', source: 'import', status: 'pending',
        targetEntityType: 'timeline_branch', entityType: 'timeline_branch',
        kind: 'import_review', title: 'Create branch: 主线', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'branch_w3_main', name: '主线', mode: 'root', sortOrder: 200, endMode: 'open' },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_branch_sect', source: 'import', status: 'pending',
        targetEntityType: 'timeline_branch', entityType: 'timeline_branch',
        kind: 'import_review', title: 'Create branch: 宗门入学弧', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'branch_w3_sect', name: '宗门入学弧', mode: 'forked', sortOrder: 201,
                parentBranchId: 'branch_w3_main', forkEventId: 'ev_w3_main2', endMode: 'open' },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_branch_mentor', source: 'import', status: 'pending',
        targetEntityType: 'timeline_branch', entityType: 'timeline_branch',
        kind: 'import_review', title: 'Create branch: 导师控制弧', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'branch_w3_mentor', name: '导师控制弧', mode: 'forked', sortOrder: 202,
                parentBranchId: 'branch_w3_main', forkEventId: 'ev_w3_main3',
                mergeEventId: 'ev_w3_mentor_end', endMode: 'merge', mergeTargetBranchId: 'branch_w3_main' },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_branch_cult', source: 'import', status: 'pending',
        targetEntityType: 'timeline_branch', entityType: 'timeline_branch',
        kind: 'import_review', title: 'Create branch: 修炼进阶弧', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'branch_w3_cult', name: '修炼进阶弧', mode: 'independent', sortOrder: 203, endMode: 'open' },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      // Events (priority 7 in applyImportPackageBatches)
      {
        id: 'prop_w3_ev_main1', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 韩立入门', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_main1', title: '韩立入门', summary: '进入七玄门', branchId: 'branch_w3_main',
                orderIndex: 0, importance: 'high', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_ev_main2', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 七玄门分流', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_main2', title: '七玄门分流', summary: '宗门入学弧分叉', branchId: 'branch_w3_main',
                orderIndex: 1, importance: 'high', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_ev_main3', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 墨大夫出现', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_main3', title: '墨大夫出现', summary: '导师控制弧分叉', branchId: 'branch_w3_main',
                orderIndex: 2, importance: 'high', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_ev_sect1', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 入门考核', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_sect1', title: '入门考核', summary: '考核通过', branchId: 'branch_w3_sect',
                orderIndex: 0, importance: 'medium', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_ev_mentor1', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 墨大夫威胁', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_mentor1', title: '墨大夫威胁', summary: '威胁开始', branchId: 'branch_w3_mentor',
                orderIndex: 0, importance: 'medium', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_ev_mentor_end', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 韩立脱离', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_mentor_end', title: '韩立脱离', summary: '摆脱控制', branchId: 'branch_w3_mentor',
                orderIndex: 1, importance: 'high', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
      {
        id: 'prop_w3_ev_cult1', source: 'import', status: 'pending',
        targetEntityType: 'timeline_event', entityType: 'timeline_event',
        kind: 'import_review', title: 'Create event: 韩立突破', description: '', preview: '', reviewPolicy: 'manual_workbench',
        data: { id: 'ev_w3_cult1', title: '韩立突破', summary: '突破一层', branchId: 'branch_w3_cult',
                orderIndex: 0, importance: 'medium', locationIds: [], participantCharacterIds: [],
                linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        originTaskRunId: 'w3_test', createdAt: now,
      },
    ];

    // Inject proposals into store, then accept them via the real proposal-acceptance path
    await page.evaluate((proposals) => {
      (window as any).__narrativeStore.setState((s: any) => ({
        proposals: [...(s.proposals ?? []), ...proposals],
      }));
    }, fourBranchProposals);

    const allIds = fourBranchProposals.map((p) => p.id);
    await page.evaluate((ids) => {
      (window as any).__narrativeStore.getState().resolveProposals(ids, 'accepted');
    }, allIds);
    await page.waitForTimeout(300);

    // Verify 4 branches were created
    const branchCountAfterAccept = await page.evaluate(() =>
      (window as any).__narrativeStore.getState().timelineBranches
        .filter((b: any) => b.id.startsWith('branch_w3_')).length,
    );
    expect(branchCountAfterAccept).toBe(4);

    // Verify fork/merge topology on mentor branch
    const mentorBranch = await page.evaluate(() =>
      (window as any).__narrativeStore.getState().timelineBranches
        .find((b: any) => b.id === 'branch_w3_mentor'),
    );
    expect(mentorBranch?.endMode).toBe('merge');
    expect(mentorBranch?.mergeEventId).toBe('ev_w3_mentor_end');
    expect(mentorBranch?.mergeTargetBranchId).toBe('branch_w3_main');

    // Two-phase save wait
    await page.waitForFunction(
      () => (window as any).__narrativeStore.getState().saveStatus === 'Unsaved changes',
      { timeout: 5000 },
    );
    await page.waitForFunction(
      () => (window as any).__narrativeStore.getState().saveStatus !== 'Unsaved changes',
      { timeout: 10000 },
    );

    // Reload — triggers normalizeTimelineCollections on open
    await page.reload();
    await goToTimeline(page);

    // Wait for store to repopulate
    await page.waitForFunction(
      () => (window as any).__narrativeStore.getState().timelineBranches
        .some((b: any) => b.id === 'branch_w3_main'),
      { timeout: 10000 },
    );

    // All 4 branches must survive normalization (each has events → not deleted)
    const branchCountAfterReload = await page.evaluate(() =>
      (window as any).__narrativeStore.getState().timelineBranches
        .filter((b: any) => b.id.startsWith('branch_w3_')).length,
    );
    expect(branchCountAfterReload).toBe(4);
  });

  test('user-named empty planning branch survives normalization on reload', async ({ page }) => {
    await openTimeline(page);

    // Ensure at least one event exists so normalization runs (it skips if no events)
    const hasEvents = await page.evaluate(() =>
      (window as any).__narrativeStore.getState().timelineEvents.length > 0,
    );
    if (!hasEvents) {
      await page.evaluate(() => {
        (window as any).__narrativeStore.setState((s: any) => ({
          timelineEvents: [
            ...s.timelineEvents,
            {
              id: 'ev_w3_seed', title: '种子事件', summary: '...', branchId: 'branch_w3_seed_root',
              orderIndex: 0, importance: 'medium' as const,
              locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [],
            },
          ],
          timelineBranches: [
            ...s.timelineBranches,
            { id: 'branch_w3_seed_root', name: 'W3种子主线', mode: 'root', sortOrder: 500, endMode: 'open' },
          ],
        }));
      });
    }

    // Add a user-named empty planning branch (name NOT in the generic deletion list)
    await page.evaluate(() => {
      (window as any).__narrativeStore.setState((s: any) => ({
        timelineBranches: [
          ...s.timelineBranches,
          { id: 'branch_w3_user_plan', name: '未来规划', mode: 'independent', sortOrder: 999, endMode: 'open' },
        ],
      }));
    });

    // Two-phase save wait
    await page.waitForFunction(
      () => (window as any).__narrativeStore.getState().saveStatus === 'Unsaved changes',
      { timeout: 5000 },
    );
    await page.waitForFunction(
      () => (window as any).__narrativeStore.getState().saveStatus !== 'Unsaved changes',
      { timeout: 10000 },
    );

    await page.reload();
    await goToTimeline(page);

    // Wait for store to repopulate
    await page.waitForFunction(
      () => (window as any).__narrativeStore.getState().timelineBranches.length > 0,
      { timeout: 10000 },
    );

    const hasBranch = await page.evaluate(() =>
      (window as any).__narrativeStore.getState().timelineBranches
        .some((b: any) => b.name === '未来规划'),
    );
    expect(hasBranch).toBe(true);
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
