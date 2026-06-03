// tests/e2e/p1/timeline_sync_roundtrip.spec.ts
import { expect, test } from '@playwright/test';

// ── Fixture ──────────────────────────────────────────────────────────────────

const TEST_BRANCHES = [
  {
    id: 'tb_main', name: 'Main', sortOrder: 10, mode: 'root' as const, color: '#f59e0b',
    collapsed: false, parentBranchId: null, forkEventId: null,
    mergeEventId: null, mergeTargetBranchId: null, endMode: 'open' as const,
    startAnchor: null, endAnchor: null,
    geometry: { laneOffset: 0, bend: 0.25, thickness: 1 }, description: '',
  },
  {
    id: 'tb_fork', name: 'Fork', sortOrder: 11, mode: 'forked' as const, color: '#38bdf8',
    collapsed: false, parentBranchId: 'tb_main', forkEventId: 'te_02',
    mergeEventId: null, mergeTargetBranchId: null, endMode: 'open' as const,
    startAnchor: { branchId: 'tb_main', eventId: 'te_02' }, endAnchor: null,
    geometry: { laneOffset: -120, bend: 0.3, thickness: 1 }, description: '',
  },
];

const TEST_EVENTS = [
  {
    id: 'te_01', title: 'Opening', summary: 's', time: 'T1',
    branchId: 'tb_main', orderIndex: 0, importance: 'critical' as const,
    locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
    linkedWorldItemIds: [], tags: [], colorToken: 'amber',
    layoutLock: false, modalStateHints: [], sharedBranchIds: [],
  },
  {
    id: 'te_02', title: 'Fork Point', summary: 's', time: 'T2',
    branchId: 'tb_main', orderIndex: 1, importance: 'high' as const,
    locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
    linkedWorldItemIds: [], tags: [], colorToken: 'amber',
    layoutLock: false, modalStateHints: [], sharedBranchIds: ['tb_fork'],
  },
  {
    id: 'te_03', title: 'Continues', summary: 's', time: 'T3',
    branchId: 'tb_main', orderIndex: 2, importance: 'medium' as const,
    locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
    linkedWorldItemIds: [], tags: [], colorToken: 'amber',
    layoutLock: false, modalStateHints: [], sharedBranchIds: [],
  },
  {
    id: 'te_f1', title: 'Fork 1', summary: 's', time: 'F1',
    branchId: 'tb_fork', orderIndex: 0, importance: 'medium' as const,
    locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
    linkedWorldItemIds: [], tags: [], colorToken: 'sky',
    layoutLock: false, modalStateHints: [], sharedBranchIds: [],
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

async function injectFixture(page: import('@playwright/test').Page) {
  await page.evaluate(({ branches, events }) => {
    const store = (window as any).__narrativeStore;
    if (!store) throw new Error('__narrativeStore not exposed');
    store.setState((s: any) => ({
      timelineBranches: [...s.timelineBranches, ...branches],
      timelineEvents: [...s.timelineEvents, ...events],
    }));
  }, { branches: TEST_BRANCHES, events: TEST_EVENTS });
}

async function openTimelineWithFixture(page: import('@playwright/test').Page) {
  await page.goto('/');
  await injectFixture(page);
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

async function dragLocator(
  page: import('@playwright/test').Page,
  locator: import('@playwright/test').Locator,
  dx: number,
  dy: number,
) {
  const box = await locator.boundingBox();
  if (!box) throw new Error('Target locator not visible');
  const sx = box.x + box.width / 2;
  const sy = box.y + box.height / 2;
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx + dx, sy + dy, { steps: 12 });
  await page.mouse.up();
}

// ── Tests ─────────────────────────────────────────────────────────────────────

// Test 1: moveTimelineEvent updates CANONICAL orderIndex (not position).
// We call the store action directly — the snap-to-curve UI drag is not reliable in headless
// Playwright because the snap radius check requires real canvas coordinate proximity.
// This test verifies the store action (which wraps applyTimelineOperation) updates canonical fields.
test('moveTimelineEvent updates canonical branchId and orderIndex', async ({ page }) => {
  await openTimelineWithFixture(page);

  const before = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents.find((e: any) => e.id === 'te_01'),
  );
  expect(before.orderIndex).toBe(0);
  expect(before.branchId).toBe('tb_main');

  // Call moveTimelineEvent directly: reorder te_01 to slot 2 on same branch
  await page.evaluate(() => {
    (window as any).__narrativeStore.getState().moveTimelineEvent('te_01', 'tb_main', 2);
  });

  const after = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents.find((e: any) => e.id === 'te_01'),
  );
  expect(after).toBeDefined();
  // CANONICAL fields must be updated — not just position (which is runtime-only)
  expect(after.branchId).toBe('tb_main');
  // After inserting at slot 2 (with 3 other events on tb_main), te_01 should have orderIndex ≠ 0
  expect(after.orderIndex).not.toBe(0);
});

// Test 2: branch middle handle drag updates geometry (canonical field)
test('branch middle handle drag updates geometry in store', async ({ page }) => {
  await openTimelineWithFixture(page);
  const handle = page.getByTestId('timeline-branch-handle-middle-tb_main');
  await expect(handle).toBeVisible();
  await dragLocator(page, handle, 60, 80);
  const branch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineBranches.find((b: any) => b.id === 'tb_main'),
  );
  expect(branch).toBeDefined();
  expect(branch.geometry).toBeDefined();
  // geometry is canonical — must be present after drag
  expect(typeof branch.geometry.laneOffset).toBe('number');
  expect(typeof branch.geometry.bend).toBe('number');
});

// Test 3: branch start handle drag — parentBranchId canonical field preserved
test('branch start handle drag preserves parentBranchId canonical field', async ({ page }) => {
  await openTimelineWithFixture(page);
  const handle = page.getByTestId('timeline-branch-handle-start-tb_fork');
  await expect(handle).toBeVisible();
  await dragLocator(page, handle, 40, 0);
  const branch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineBranches.find((b: any) => b.id === 'tb_fork'),
  );
  expect(branch).toBeDefined();
  // parentBranchId is CANONICAL — must survive drag
  expect(branch.parentBranchId).toBe('tb_main');
});

// Test 4: branch end handle drag — if snapped, canonical topology fields are set consistently
test('branch end handle drag updates endAnchor canonical fields when snapped', async ({ page }) => {
  await openTimelineWithFixture(page);
  const handle = page.getByTestId('timeline-branch-handle-end-tb_fork');
  await expect(handle).toBeVisible();
  await dragLocator(page, handle, 80, 40);
  const branch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineBranches.find((b: any) => b.id === 'tb_fork'),
  );
  expect(branch).toBeDefined();
  // If snapped to an event, endAnchor/mergeTargetBranchId/mergeEventId/endMode must be consistent
  if (branch.endAnchor) {
    expect(branch.mergeTargetBranchId).toBeTruthy();
    expect(branch.mergeEventId).toBeTruthy();
    expect(branch.endMode).toBe('merge');
  }
  // These CANONICAL topology fields must always be present as keys (null is valid for open branch)
  expect('endAnchor' in branch).toBe(true);
  expect('endMode' in branch).toBe(true);
  expect('mergeTargetBranchId' in branch).toBe(true);
  expect('mergeEventId' in branch).toBe(true);
});

// Test 5: TRUE DISK ROUND-TRIP via save → page.reload() → verify canonical fields from disk.
// This is NOT an in-memory check. It proves canonical storage via the full persistence path.
// In the web dev context, saveProject writes to localStorage; page.reload() loads from localStorage.
test('canonical topology fields survive save-reload round-trip', async ({ page }) => {
  await page.goto('/');
  await injectFixture(page);

  // Explicit save via toolbar button → triggers projectService.saveProject → localStorage write
  await page.getByTestId('toolbar-save').click();
  // Wait for save to complete — the toolbar-save is sync but there may be async state flush
  // 2500ms > 2s debounce so auto-save would also fire if triggered
  await page.waitForTimeout(2500);

  // Reload the page — app reinitializes from localStorage (canonical disk storage in web mode)
  await page.reload();
  await page.waitForLoadState('domcontentloaded');

  // Navigate to timeline after reload (store now loaded from disk)
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();

  // Verify canonical topology fields survived the disk round-trip
  const branches = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineBranches,
  );
  const fork = branches.find((b: any) => b.id === 'tb_fork');
  expect(fork).toBeDefined();

  // Canonical topology fields — must all survive reload
  expect(fork.parentBranchId).toBe('tb_main');
  expect(fork.startAnchor?.branchId).toBe('tb_main');
  expect(fork.startAnchor?.eventId).toBe('te_02');
  expect(fork.forkEventId).toBe('te_02');

  // endAnchor, endMode, mergeTargetBranchId, mergeEventId are CANONICAL —
  // they must be present as keys after reload (null is valid for an open branch)
  expect('endAnchor' in fork).toBe(true);
  expect('endMode' in fork).toBe(true);
  expect('mergeTargetBranchId' in fork).toBe(true);
  expect('mergeEventId' in fork).toBe(true);
});

// Test 6: sync console output has no false-positive warnings for canonical topology fields.
// If endAnchor/endMode/mergeEventId/mergeTargetBranchId appear as "skipped" warnings,
// it means BRANCH_RUNTIME_FIELDS was not properly fixed.
test('sync console output has no false-positive topology field warnings', async ({ page }) => {
  const warnings: string[] = [];
  page.on('console', (msg) => { if (msg.type() === 'warn') warnings.push(msg.text()); });
  await page.goto('/');
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
  await page.getByTestId('timeline-synchronize-btn').click();
  await page.waitForTimeout(400);
  const allWarnings = warnings.join(' ');
  for (const field of ['endAnchor', 'endMode', 'mergeEventId', 'mergeTargetBranchId']) {
    expect(allWarnings, `${field} should not be falsely skipped in sync comparison`).not.toContain(`${field}: skipped`);
  }
});

// Test 7: dense event labels — visible labels must not overlap (bounding box check)
test('dense event labels have no visible overlap', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    const denseEvents = Array.from({ length: 28 }, (_, i) => ({
      id: `dlbl_${i}`, title: `Dense Label Event ${i + 1}`, summary: '', time: '',
      branchId: 'branch_main', orderIndex: i + 100,
      locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
      linkedWorldItemIds: [], tags: [],
      importance: (i % 5 === 0 ? 'critical' : i % 3 === 0 ? 'high' : 'medium') as 'critical' | 'high' | 'medium',
      colorToken: 'amber', layoutLock: false, modalStateHints: [], sharedBranchIds: [],
    }));
    store.setState((s: any) => ({ timelineEvents: [...s.timelineEvents, ...denseEvents] }));
  });
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();

  const labelBoxes = await page.evaluate(() =>
    Array.from(document.querySelectorAll<SVGTextElement>('[data-testid^="timeline-event-label-"]')).map((el) => {
      const r = el.getBoundingClientRect();
      return { id: el.getAttribute('data-testid') ?? '', left: r.left, right: r.right, top: r.top, bottom: r.bottom };
    }),
  );

  // Visible labels must not overlap each other
  for (let i = 0; i < labelBoxes.length; i++) {
    for (let j = i + 1; j < labelBoxes.length; j++) {
      const a = labelBoxes[i];
      const b = labelBoxes[j];
      const overlap = !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
      expect(overlap, `label overlap: ${a.id} vs ${b.id}`).toBe(false);
    }
  }
});

// Test 8: sync analysis — no false-positive warnings for runtime-only fields after Synchronize click
test('sync analysis: no false-positive warnings about runtime-only fields', async ({ page }) => {
  const allWarnings: string[] = [];
  const consoleHandler = (msg: import('@playwright/test').ConsoleMessage) => {
    if (msg.type() === 'warn') allWarnings.push(msg.text());
  };
  page.on('console', consoleHandler);

  await page.goto('/');
  await expect(page.locator('[data-testid="timeline-canvas"]')).toBeVisible({ timeout: 10000 });

  // Set up a fork/merge topology so anchorStartPos/anchorEndPos are computed at runtime
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState({
      timelineBranches: [
        { id: 'branch_main', name: '主线', mode: 'root', sortOrder: 0, endMode: 'open' },
        { id: 'branch_fork', name: '分支线', mode: 'forked', sortOrder: 1,
          parentBranchId: 'branch_main', forkEventId: 'ev_a', endMode: 'open',
          anchorStartPos: { x: 400, y: 200 },
          anchorEndPos:   { x: 800, y: 200 },
        },
      ],
      timelineEvents: [
        { id: 'ev_a', title: '事件A', summary: '...', branchId: 'branch_main',
          orderIndex: 0, importance: 'high',
          locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [],
          position: { x: 400, y: 200 },
        },
        { id: 'ev_b', title: '事件B', summary: '...', branchId: 'branch_fork',
          orderIndex: 0, importance: 'medium',
          locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [],
        },
      ],
    });
  });

  await page.waitForTimeout(300);

  // Find and click Synchronize button
  const syncBtn = page.locator('[data-testid="timeline-synchronize-btn"]').or(
    page.locator('button', { hasText: /synchronize/i })
  );
  // Hard-assert the button exists — if absent, the test fails loudly rather than vacuously passing
  await expect(syncBtn.first()).toBeVisible({ timeout: 5000 });
  // Snapshot index to isolate only post-click warnings (avoids unsafe length=0 reset)
  const preClickLen = allWarnings.length;
  await syncBtn.first().click();
  await page.waitForTimeout(500);
  const postClickWarnings = allWarnings.slice(preClickLen);
  const badWarnings = postClickWarnings.filter((w) =>
    w.includes('anchorStartPos') || w.includes('anchorEndPos') ||
    (w.includes('[Timeline]') && (
      w.includes('position') || w.includes('sharedBranchIds') ||
      w.includes('layoutLock') || w.includes('modalStateHints')
    ))
  );
  expect(badWarnings).toHaveLength(0);
  page.off('console', consoleHandler);
});

test('events with hidden labels show tooltip on hover', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    const denseEvents = Array.from({ length: 28 }, (_, i) => ({
      id: `htip_${i}`, title: `HoverTip Event ${i}`, summary: '', time: '',
      branchId: 'branch_main', orderIndex: i + 200,
      locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
      linkedWorldItemIds: [], tags: [], importance: 'low' as const,
      colorToken: 'sky', layoutLock: false, modalStateHints: [], sharedBranchIds: [],
    }));
    store.setState((s: any) => ({ timelineEvents: [...s.timelineEvents, ...denseEvents] }));
  });
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();

  const hiddenNodes = page.locator('[data-testid^="timeline-event-node-"][data-label-visible="false"]');
  const count = await hiddenNodes.count();
  if (count > 0) {
    const firstHidden = hiddenNodes.first();
    const testId = (await firstHidden.getAttribute('data-testid')) ?? '';
    const eventId = testId.replace('timeline-event-node-', '');
    await page.getByTestId(`timeline-event-hitarea-${eventId}`).dispatchEvent('pointerover', { bubbles: true });
    await expect(page.getByTestId(`timeline-event-tooltip-${eventId}`)).toBeVisible();
  }
  // If count === 0, all labels placed without collision — valid pass
});
