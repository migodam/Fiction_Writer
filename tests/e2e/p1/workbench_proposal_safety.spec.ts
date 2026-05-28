import { expect, test } from '@playwright/test';

test.describe('Workbench proposal safety', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.getByTestId('activity-btn-workbench').click();
  });

  test('accepting a consistency proposal updates canonical data and cleans up issue state', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_consistency_fix_bridge')).toBeVisible();

    await page.getByTestId('proposal-accept-proposal_consistency_fix_bridge').click();
    await expect(page.getByTestId('proposal-card-proposal_consistency_fix_bridge')).not.toBeVisible();

    await page.getByTestId('sidebar-section-workbench-history').click();
    const historyList = page.getByTestId('workbench-history-list');
    await expect(historyList).toContainText('Resolve bridge location mismatch');
    await expect(historyList.getByText('accepted').first()).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-issues').click();
    await expect(page.getByTestId('workbench-issues-list')).not.toContainText('Bridge location mismatch');

    await page.getByTestId('activity-btn-world').click();
    await page.getByRole('button', { name: /Locations notebook/i }).click();
    await page.getByRole('button', { name: /Glass Bridge/i }).first().click();
    await expect(page.locator('textarea').first()).toHaveValue('Glass Bridge remains the canonical location reference.');
  });

  test('rejecting a proposal moves it to history without mutating canonical data or closing the issue', async ({ page }) => {
    await page.getByTestId('proposal-reject-proposal_consistency_fix_bridge').click();
    await expect(page.getByTestId('proposal-card-proposal_consistency_fix_bridge')).not.toBeVisible();

    await page.getByTestId('sidebar-section-workbench-history').click();
    const historyList = page.getByTestId('workbench-history-list');
    await expect(historyList).toContainText('Resolve bridge location mismatch');
    await expect(historyList.getByText('rejected').first()).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-issues').click();
    await expect(page.getByTestId('workbench-issues-list')).toContainText('Bridge location mismatch');

    await page.getByTestId('activity-btn-world').click();
    await page.getByRole('button', { name: /Locations notebook/i }).click();
    await page.getByRole('button', { name: /Glass Bridge/i }).first().click();
    await expect(page.locator('textarea').first()).toHaveValue(/suspended transit line/);
  });

  test('accepting an unsupported canonical operation keeps the proposal pending and surfaces an issue', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_import_entities_seed')).toBeVisible();

    await page.getByTestId('proposal-accept-proposal_import_entities_seed').click();
    await expect(page.getByTestId('proposal-card-proposal_import_entities_seed')).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-history').click();
    await expect(page.getByTestId('workbench-history-list')).not.toContainText('Review imported metadata candidates');

    await page.getByTestId('sidebar-section-workbench-issues').click();
    await expect(page.getByTestId('workbench-issues-list')).toContainText('Proposal blocked: Review imported metadata candidates');
    await expect(page.getByTestId('workbench-issues-list')).toContainText('supported canonical change');
  });

  test('blocked proposal shows reason banner on card after accept attempt', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_import_entities_seed')).toBeVisible();

    // First attempt — triggers the block
    await page.getByTestId('proposal-accept-proposal_import_entities_seed').click();

    // Reason banner must appear on the card
    const reasonBanner = page.getByTestId('proposal-blocked-reason-proposal_import_entities_seed');
    await expect(reasonBanner).toBeVisible();
    await expect(reasonBanner).toContainText('supported canonical change');
  });

  test('accept button is disabled after a proposal is blocked', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_import_entities_seed')).toBeVisible();

    // First attempt — triggers the block
    await page.getByTestId('proposal-accept-proposal_import_entities_seed').click();

    // Accept button must be disabled — no silent re-click possible
    const acceptBtn = page.getByTestId('proposal-accept-proposal_import_entities_seed');
    await expect(acceptBtn).toBeDisabled();
  });
});
