/**
 * Zero-cost E2E tests for World Model Organizer proposal packages in the Workbench Inbox.
 * No live API calls. All proposals are injected synthetically via window.__narrativeStore.
 *
 * Verifies the 'organizer' source (the 4th reviewer source added in W5) renders correctly.
 * Companion to workbench_reviewer_repair_package.spec.ts which covers quality/fact/consistency.
 *
 * TestID contract (from WorkbenchWorkspace.tsx PackageCard):
 *   import-package-{pkg.id}           — outer card container
 *   proposal-package-source-{pkg.id}  — source badge
 *   proposal-package-risk-{pkg.id}    — risk badge
 *   accept-import-package-{pkg.id}    — accept button
 *   proposal-package-expand-{pkg.id}  — expand/collapse toggle
 *
 * For organizer packages:
 *   pkg.id = reviewer-organizer-{runId}  (built by getProposalReviewerPackageKey)
 */
import { expect, test } from '@playwright/test';

const now = () => '2026-06-01T00:00:00.000Z';

const makeOrganizerProposal = (
  runId: string,
  id: string,
  entityType: 'world_item' | 'world_container',
  fields: Record<string, unknown>,
  title = `Organizer: ${String(fields.name ?? entityType)}`,
) => ({
  id,
  title,
  source: 'organizer',
  kind: 'entity_update',
  description: `Organizer proposal for ${entityType} '${String(fields.name ?? id)}'`,
  targetEntityType: entityType,
  targetEntityId: (fields.id as string) ?? null,
  targetEntityRefs: [],
  preview: String(fields.name ?? id),
  proposedOperations: [{ op: 'create', entityType, entityId: fields.id, fields }],
  reviewPolicy: 'manual_workbench',
  status: 'pending',
  createdAt: now(),
  data: { reviewerRunId: runId },
  originTaskRunId: runId,
  confidence: 0.85,
});

const orgPkgTestId = (runId: string) => `reviewer-organizer-${runId}`;

async function injectOrganizerPackage(
  page: import('@playwright/test').Page,
  proposals: unknown[],
) {
  await page.goto('http://localhost:3000');
  await page.evaluate(
    ({ proposals }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore not exposed in DEV mode');
      store.setState((state: any) => ({
        ...state,
        characters: [],
        characterTags: [],
        timelineEvents: [],
        timelineBranches: [],
        relationships: [],
        chapters: [],
        scenes: [],
        worldContainers: [],
        worldItems: [],
        proposals,
        proposalHistory: [],
        issues: [],
        unreadUpdates: {
          ...state.unreadUpdates,
          activities: { ...state.unreadUpdates.activities, workbench: true },
          sections: { ...state.unreadUpdates.sections, 'workbench.inbox': true },
          entities: {},
        },
      }));
    },
    { proposals },
  );
  await page.getByTestId('activity-btn-workbench').click();
}

// ────────────────────────────────────────────────────────────────────
// Test 1: organizer package card renders with source badge
// ────────────────────────────────────────────────────────────────────
test('organizer package renders with source badge', async ({ page }) => {
  const runId = 'org_render_test';
  await injectOrganizerPackage(page, [
    makeOrganizerProposal(runId, 'org_p1', 'world_item', {
      id: 'wi_qixuanmen',
      name: '七玄门',
      category: 'organization',
      containerKey: 'organizations',
      categoryPath: ['世界模型', '门派组织', '七玄门'],
      description: '凡人修仙传中的主要门派',
      confidence: 0.9,
    }),
  ]);

  const testId = orgPkgTestId(runId);
  await expect(page.getByTestId(`import-package-${testId}`)).toBeVisible();
  await expect(page.getByTestId(`proposal-package-source-${testId}`)).toHaveAttribute('data-source', 'organizer');
});

// ────────────────────────────────────────────────────────────────────
// Test 2: accept organizer package writes world items to store
// ────────────────────────────────────────────────────────────────────
test('accepts organizer package and writes world items to store', async ({ page }) => {
  const runId = 'org_accept_test';
  await injectOrganizerPackage(page, [
    makeOrganizerProposal(runId, 'org_acc_wi1', 'world_item', {
      id: 'wi_changchungong',
      name: '长春功',
      category: 'cultivation_method',
      containerKey: 'cultivation_methods',
      categoryPath: ['世界模型', '功法与术法', '长春功'],
      description: '七玄门入门功法',
      confidence: 0.88,
    }),
    makeOrganizerProposal(runId, 'org_acc_wi2', 'world_item', {
      id: 'wi_shenshengu',
      name: '神手谷',
      category: 'location',
      containerKey: 'locations',
      categoryPath: ['世界模型', '地理位置', '神手谷'],
      description: '炼药师聚集之地',
      confidence: 0.82,
    }),
  ]);

  const testId = orgPkgTestId(runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();
  await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

  const state = await page.evaluate(() => {
    const s = (window as any).__narrativeStore.getState();
    return {
      worldItems: s.worldItems.map((w: any) => w.id),
      history: s.proposalHistory.map((p: any) => p.id),
    };
  });

  expect(state.worldItems).toEqual(
    expect.arrayContaining(['wi_changchungong', 'wi_shenshengu']),
  );
  expect(state.history).toEqual(
    expect.arrayContaining(['org_acc_wi1', 'org_acc_wi2']),
  );
});

// ────────────────────────────────────────────────────────────────────
// Test 3: risk badge shows low for clean organizer output
// ────────────────────────────────────────────────────────────────────
test('organizer package shows low risk badge when no blocking', async ({ page }) => {
  const runId = 'org_risk_test';
  await injectOrganizerPackage(page, [
    makeOrganizerProposal(runId, 'org_risk_p1', 'world_item', {
      id: 'wi_risk_org',
      name: '青牛门',
      category: 'organization',
      containerKey: 'organizations',
      categoryPath: ['世界模型', '门派组织', '青牛门'],
      description: '另一个门派',
      confidence: 0.86,
    }),
  ]);

  const testId = orgPkgTestId(runId);
  await expect(page.getByTestId(`import-package-${testId}`)).toBeVisible();
  // Low risk: no blockedReason, confidence >= 0.7
  await expect(page.getByTestId(`proposal-package-risk-${testId}`)).toContainText('low');
});

// ────────────────────────────────────────────────────────────────────
// Test 4: expand/collapse toggle shows world item names
// ────────────────────────────────────────────────────────────────────
test('expand shows world item names in organizer package', async ({ page }) => {
  const runId = 'org_expand_test';
  await injectOrganizerPackage(page, [
    makeOrganizerProposal(runId, 'org_exp_p1', 'world_item', {
      id: 'wi_exp_loc',
      name: '七玄堂',
      category: 'location',
      containerKey: 'locations',
      categoryPath: ['世界模型', '地理位置', '七玄堂'],
      description: '七玄门内的议事大堂',
      confidence: 0.75,
    }),
    makeOrganizerProposal(runId, 'org_exp_p2', 'world_item', {
      id: 'wi_exp_cult',
      name: '金刚诀',
      category: 'cultivation_method',
      containerKey: 'cultivation_methods',
      categoryPath: ['世界模型', '功法与术法', '金刚诀'],
      description: '强化体魄的基础功法',
      confidence: 0.80,
    }),
  ]);

  const testId = orgPkgTestId(runId);
  const expandBtn = page.getByTestId(`proposal-package-expand-${testId}`);
  await expandBtn.click();

  await expect(page.locator('[data-testid^="import-package-"]')).toContainText('七玄堂');
  await expect(page.locator('[data-testid^="import-package-"]')).toContainText('金刚诀');

  // Collapse and verify items are hidden
  await expandBtn.click();
  await expect(page.locator('text=七玄堂')).not.toBeVisible();
});
