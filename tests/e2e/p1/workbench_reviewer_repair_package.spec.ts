/**
 * Zero-cost E2E tests for reviewer repair packages in the Workbench Inbox.
 * No live API calls. All proposals are injected synthetically via window.__narrativeStore.
 */
import { expect, test } from '@playwright/test';

const now = () => '2026-06-01T00:00:00.000Z';

type ReviewerSource = 'quality_reviewer' | 'fact_reviewer' | 'consistency_reviewer';

const makeReviewerProposal = (
  source: ReviewerSource,
  reviewerRunId: string,
  id: string,
  entityType: string,
  fields: Record<string, unknown>,
  title = `Repair ${entityType}`,
) => ({
  id,
  title,
  source,
  kind: 'qa_fix',
  description: `Synthetic reviewer repair proposal for ${entityType}`,
  targetEntityType: entityType,
  targetEntityId: (fields.id as string) ?? null,
  targetEntityRefs: [],
  preview: String(fields.name || fields.id || entityType),
  proposedOperations: [{ op: 'create', entityType, entityId: fields.id, fields }],
  reviewPolicy: 'manual_workbench',
  status: 'pending',
  createdAt: now(),
  data: { reviewerRunId },
  originTaskRunId: reviewerRunId,
});

const pkgTestId = (source: ReviewerSource, runId: string) =>
  `reviewer-${source}-${runId}`;

async function injectReviewerPackage(
  page: import('@playwright/test').Page,
  proposals: unknown[],
  existingState?: Record<string, unknown>,
) {
  await page.goto('http://localhost:3000');
  await page.evaluate(
    ({ proposals, extra }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore not exposed in DEV mode');
      store.setState((state: any) => ({
        ...state,
        characters: extra?.characters ?? [],
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
    { proposals, extra: existingState ?? {} },
  );
  await page.getByTestId('activity-btn-workbench').click();
}

// ────────────────────────────────────────────────────────────────────
// Test 1: package card renders with source badge
// ────────────────────────────────────────────────────────────────────
test('reviewer repair package renders with source badge', async ({ page }) => {
  const runId = 'rev_render_test';
  const source: ReviewerSource = 'quality_reviewer';
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_p1', 'character', { id: 'char_a1', name: 'Hero' }),
    makeReviewerProposal(source, runId, 'rev_p2', 'character_tag', { id: 'tag_a1', label: 'Protagonist' }),
  ]);

  const testId = pkgTestId(source, runId);
  await expect(page.getByTestId(`import-package-${testId}`)).toBeVisible();
  await expect(page.getByTestId(`proposal-package-source-${testId}`)).toHaveAttribute('data-source', 'quality_reviewer');
});

// ────────────────────────────────────────────────────────────────────
// Test 2: accept reviewer repair package (no blocking deps)
// ────────────────────────────────────────────────────────────────────
test('accepts reviewer repair package with no dependency conflicts', async ({ page }) => {
  const runId = 'rev_accept_test';
  const source: ReviewerSource = 'fact_reviewer';
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_acc_p1', 'character_tag', {
      id: 'tag_courage',
      label: 'Courageous',
    }),
    makeReviewerProposal(source, runId, 'rev_acc_p2', 'character_tag', {
      id: 'tag_wise',
      label: 'Wise',
    }),
  ]);

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();
  await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

  const state = await page.evaluate(() => {
    const s = (window as any).__narrativeStore.getState();
    return {
      tags: s.characterTags.map((t: any) => t.id),
      history: s.proposalHistory.map((p: any) => p.id),
    };
  });

  expect(state.tags).toEqual(expect.arrayContaining(['tag_courage', 'tag_wise']));
  expect(state.history).toEqual(expect.arrayContaining(['rev_acc_p1', 'rev_acc_p2']));
});

// ────────────────────────────────────────────────────────────────────
// Test 3: package rollback when blocking edge is present
// ────────────────────────────────────────────────────────────────────
test('rolls back reviewer repair package when blocking edge present, shows retry button', async ({ page }) => {
  const runId = 'rev_block_test';
  const source: ReviewerSource = 'consistency_reviewer';
  // character references a tag that is NOT in the batch — triggers blocked reference
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_blk_char', 'character', {
      id: 'char_blocked',
      name: 'Blocked Hero',
      tagIds: ['tag_does_not_exist_anywhere'],
    }),
    makeReviewerProposal(source, runId, 'rev_blk_tag', 'character_tag', {
      id: 'tag_actual',
      label: 'Actual Tag',
    }),
  ]);

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();

  // Should see retry button (blocked) instead of accept button
  await expect(page.getByTestId(`retry-blocked-package-${testId}`)).toBeVisible();
  // Blocked reason banner should appear
  await expect(page.getByTestId(`import-package-blocked-reason-${testId}`)).toBeVisible();

  // Proposals must remain pending (not moved to history)
  const pending = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().proposals.map((p: any) => p.id),
  );
  expect(pending).toEqual(expect.arrayContaining(['rev_blk_char', 'rev_blk_tag']));
});

// ────────────────────────────────────────────────────────────────────
// Test 4: cyclic character↔event refs succeed via pre-registered IDs
// ────────────────────────────────────────────────────────────────────
test('accepts package with cyclic character-event cross-references', async ({ page }) => {
  const runId = 'rev_cyclic_test';
  const source: ReviewerSource = 'quality_reviewer';
  // character refs event, event refs character — resolved via collectReferenceSets pre-registry
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_cyc_char', 'character', {
      id: 'char_cyc_a',
      name: 'Cyclic Hero',
      linkedEventIds: ['event_cyc_b'],
    }),
    makeReviewerProposal(source, runId, 'rev_cyc_event', 'timeline_event', {
      id: 'event_cyc_b',
      title: 'Cyclic Meeting',
      participantCharacterIds: ['char_cyc_a'],
      branchId: 'branch_cyc_main',
      orderIndex: 0,
      locationIds: [],
      linkedSceneIds: [],
      linkedWorldItemIds: [],
    }),
    makeReviewerProposal(source, runId, 'rev_cyc_branch', 'timeline_branch', {
      id: 'branch_cyc_main',
      name: 'Cyclic Branch',
      sortOrder: 0,
      mode: 'root',
      collapsed: false,
    }),
  ]);

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();
  await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');
});

// ────────────────────────────────────────────────────────────────────
// Test 5: blocked reason shows precise culprit entity
// ────────────────────────────────────────────────────────────────────
test('blocked reason contains precise culprit entity reference', async ({ page }) => {
  const runId = 'rev_precise_test';
  const source: ReviewerSource = 'quality_reviewer';
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_prec_char', 'character', {
      id: 'char_precise',
      name: 'Precise Hero',
      tagIds: ['tag_missing_precise'],
    }),
    makeReviewerProposal(source, runId, 'rev_prec_other', 'character', {
      id: 'char_precise_b',
      name: 'Other Hero',
    }),
  ]);

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();

  const blockedText = await page.getByTestId(`import-package-blocked-reason-${testId}`).textContent();
  // The blocked reason must name the culprit proposal ID or the missing entity
  expect(blockedText).toMatch(/tag_missing_precise|rev_prec_char/);
});

// ────────────────────────────────────────────────────────────────────
// Test 6: retry blocked package succeeds after root cause removed
// ────────────────────────────────────────────────────────────────────
test('retry unblocks package after root-cause proposal is removed', async ({ page }) => {
  const runId = 'rev_retry_test';
  const source: ReviewerSource = 'consistency_reviewer';
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_ret_char', 'character', {
      id: 'char_retry',
      name: 'Retry Hero',
      tagIds: ['tag_bad_ref'],
    }),
    makeReviewerProposal(source, runId, 'rev_ret_tag', 'character_tag', {
      id: 'tag_good',
      label: 'Good Tag',
    }),
  ]);

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();
  await expect(page.getByTestId(`retry-blocked-package-${testId}`)).toBeVisible();

  // Fix: remove the bad ref by patching the proposal in the store
  await page.evaluate((runId) => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      ...state,
      proposals: state.proposals.map((p: any) =>
        p.id === 'rev_ret_char'
          ? {
              ...p,
              lastBlockReason: undefined,
              lastBlockedAt: undefined,
              proposedOperations: [
                {
                  op: 'create',
                  entityType: 'character',
                  entityId: 'char_retry',
                  fields: { id: 'char_retry', name: 'Retry Hero', tagIds: [], data: { reviewerRunId: runId } },
                },
              ],
            }
          : p,
      ),
    }));
  }, runId);

  await page.getByTestId(`retry-blocked-package-${testId}`).click();
  await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');
});

// ────────────────────────────────────────────────────────────────────
// Test 7: package card is collapsed by default; expand shows proposals
// ────────────────────────────────────────────────────────────────────
test('package card is collapsed by default; expand button reveals proposal list', async ({ page }) => {
  const runId = 'rev_expand_test';
  const source: ReviewerSource = 'quality_reviewer';
  await injectReviewerPackage(page, [
    makeReviewerProposal(source, runId, 'rev_exp_p1', 'character', { id: 'char_exp_a', name: 'Alpha' }),
    makeReviewerProposal(source, runId, 'rev_exp_p2', 'character', { id: 'char_exp_b', name: 'Beta' }),
  ]);

  const testId = pkgTestId(source, runId);
  const expandBtn = page.getByTestId(`proposal-package-expand-${testId}`);

  // Collapsed by default: proposal titles should not be visible
  await expect(expandBtn).toBeVisible();
  await expect(page.locator(`[data-testid="import-package-${testId}"]`)).not.toContainText('Alpha');

  // Expand
  await expandBtn.click();
  await expect(page.locator(`[data-testid="import-package-${testId}"]`)).toContainText('Alpha');
  await expect(page.locator(`[data-testid="import-package-${testId}"]`)).toContainText('Beta');

  // Collapse again
  await expandBtn.click();
  await expect(page.locator(`[data-testid="import-package-${testId}"]`)).not.toContainText('Alpha');
});

// ────────────────────────────────────────────────────────────────────
// Test 8: risk badge shows "high" when any proposal in package is blocked
// ────────────────────────────────────────────────────────────────────
test('risk badge shows high when package contains a blocked proposal', async ({ page }) => {
  const runId = 'rev_risk_test';
  const source: ReviewerSource = 'fact_reviewer';
  await injectReviewerPackage(page, [
    {
      ...makeReviewerProposal(source, runId, 'rev_risk_p1', 'character', {
        id: 'char_risk_a',
        name: 'Risky Hero',
      }),
      lastBlockReason: 'character rev_risk_p1 references missing tag: tag_missing',
      lastBlockedAt: now(),
    },
    makeReviewerProposal(source, runId, 'rev_risk_p2', 'character', {
      id: 'char_risk_b',
      name: 'Safe Hero',
    }),
  ]);

  const testId = pkgTestId(source, runId);
  await expect(page.getByTestId(`proposal-package-risk-${testId}`)).toContainText('high');
});

// ────────────────────────────────────────────────────────────────────
// Test 9: op:update repair proposal actually updates an existing character
// ────────────────────────────────────────────────────────────────────
test('accepting op:update repair package updates existing character field', async ({ page }) => {
  const runId = 'rev_update_test';
  const source: ReviewerSource = 'quality_reviewer';
  const charId = 'char_update_target';

  await page.goto('http://localhost:3000');
  await page.evaluate(
    ({ charId, proposals }: { charId: string; proposals: unknown[] }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore not exposed');
      store.setState((state: any) => ({
        ...state,
        characters: [{ id: charId, name: 'Target Hero', summary: 'Old summary with a repeated repeated phrase.' }],
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
    {
      charId,
      proposals: [
        {
          id: 'rev_upd_p1',
          title: 'Clean Repeated Phrase',
          source,
          kind: 'qa_fix',
          description: 'Remove repeated phrase from summary',
          targetEntityType: 'character',
          targetEntityId: charId,
          targetEntityRefs: [],
          preview: 'Target Hero',
          proposedOperations: [
            {
              op: 'update',
              entityType: 'character',
              entityId: charId,
              fields: { summary: 'Old summary with a repeated phrase.' },
            },
          ],
          reviewPolicy: 'manual_workbench',
          status: 'pending',
          createdAt: now(),
          data: { reviewerRunId: runId },
          originTaskRunId: runId,
        },
        {
          id: 'rev_upd_p2',
          title: 'Dummy second proposal',
          source,
          kind: 'qa_fix',
          description: 'Second proposal to form a package',
          targetEntityType: 'character',
          targetEntityId: 'char_upd_b',
          targetEntityRefs: [],
          preview: 'Other Hero',
          proposedOperations: [
            {
              op: 'update',
              entityType: 'character',
              entityId: charId,
              fields: { summary: 'Old summary with a repeated phrase.' },
            },
          ],
          reviewPolicy: 'manual_workbench',
          status: 'pending',
          createdAt: now(),
          data: { reviewerRunId: runId },
          originTaskRunId: runId,
        },
      ],
    },
  );
  await page.getByTestId('activity-btn-workbench').click();

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();
  await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

  const updatedSummary = await page.evaluate((id: string) => {
    const chars = (window as any).__narrativeStore.getState().characters as Array<{ id: string; summary: string }>;
    return chars.find((c) => c.id === id)?.summary ?? null;
  }, charId);

  expect(updatedSummary).toBe('Old summary with a repeated phrase.');
});

// ────────────────────────────────────────────────────────────────────
// Test 10: unsupported op (link) is blocked with precise reason
// ────────────────────────────────────────────────────────────────────
test('repair package with unsupported op is blocked with precise reason', async ({ page }) => {
  const runId = 'rev_link_test';
  const source: ReviewerSource = 'fact_reviewer';
  await injectReviewerPackage(page, [
    {
      id: 'rev_lnk_p1',
      title: 'Link Character',
      source,
      kind: 'qa_fix',
      description: 'Attempt unsupported link op',
      targetEntityType: 'character',
      targetEntityId: 'char_link_a',
      targetEntityRefs: [],
      preview: 'Link Hero',
      proposedOperations: [{ op: 'link', entityType: 'character', entityId: 'char_link_a', fields: {} }],
      reviewPolicy: 'manual_workbench',
      status: 'pending',
      createdAt: now(),
      data: { reviewerRunId: runId },
      originTaskRunId: runId,
    },
    {
      id: 'rev_lnk_p2',
      title: 'Dummy second',
      source,
      kind: 'qa_fix',
      description: 'Second proposal for packaging',
      targetEntityType: 'character',
      targetEntityId: 'char_link_b',
      targetEntityRefs: [],
      preview: 'Other',
      proposedOperations: [{ op: 'link', entityType: 'character', entityId: 'char_link_b', fields: {} }],
      reviewPolicy: 'manual_workbench',
      status: 'pending',
      createdAt: now(),
      data: { reviewerRunId: runId },
      originTaskRunId: runId,
    },
  ]);

  const testId = pkgTestId(source, runId);
  await page.getByTestId(`accept-import-package-${testId}`).click();

  await expect(page.getByTestId(`retry-blocked-package-${testId}`)).toBeVisible();
  const blockedText = await page.getByTestId(`import-package-blocked-reason-${testId}`).textContent();
  expect(blockedText).toMatch(/not supported/i);
});
