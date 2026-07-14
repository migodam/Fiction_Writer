import { expect, test } from '@playwright/test';

const safetyFixture = {
  metadata: {
    schemaVersion: 5,
    projectId: 'proj_proposal_safety',
    name: 'Proposal Safety Fixture',
    rootPath: 'memory://proposal-safety',
    storageMode: 'memory',
    locale: 'en',
    version: 1,
    createdAt: '2026-07-11T00:00:00.000Z',
    updatedAt: '2026-07-11T00:00:00.000Z',
    template: 'blank',
  },
  worldContainers: [{ id: 'cont_safety', name: 'Safety Locations', type: 'notebook', sortOrder: 0, isCollapsed: false }],
  worldItems: [{ id: 'safety_location', containerId: 'cont_safety', type: 'location', name: 'Safety Bridge', description: 'The original canonical description.', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], assetPath: null, tagIds: [] }],
  proposals: [
    {
      id: 'proposal_safety_update', title: 'Apply safe location correction', source: 'consistency', kind: 'qa_fix', description: 'Correct the canonical location description.', targetEntityType: 'world_item', targetEntityId: 'safety_location', targetEntityRefs: [{ type: 'world_item', id: 'safety_location' }], preview: 'Set the approved canonical description.', proposedOperations: [{ op: 'update', entityType: 'world_item', entityId: 'safety_location', fields: { description: 'The approved canonical description.' } }], originIssueId: 'issue_safety_location', reviewPolicy: 'manual_workbench', status: 'pending', createdAt: '2026-07-11T00:00:00.000Z',
    },
    {
      id: 'proposal_safety_unsupported', title: 'Unsupported canonical operation', source: 'agent', kind: 'import_review', description: 'Attempts an operation the canonical reducer must reject.', targetEntityType: 'proposal', targetEntityId: null, preview: 'An unsupported proposal operation.', proposedOperations: [{ op: 'create', entityType: 'proposal', fields: { source: 'import' } }], reviewPolicy: 'manual_workbench', status: 'pending', createdAt: '2026-07-11T00:00:00.000Z',
    },
  ],
  proposalHistory: [],
  issues: [{ id: 'issue_safety_location', title: 'Safety location mismatch', description: 'The location needs an approved canonical correction.', severity: 'high', status: 'open', source: 'consistency', referenceIds: [{ type: 'world_item', id: 'safety_location' }], suggestedProposalIds: ['proposal_safety_update'] }],
};

test.describe('Workbench proposal safety', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((project) => {
      localStorage.setItem('narrative-ide-project', JSON.stringify(project));
      localStorage.setItem('narrative-ide-last-path', project.metadata.rootPath);
    }, safetyFixture);
    await page.goto('http://localhost:3000/workbench/inbox');
  });

  test('accepting a consistency proposal updates canonical data and cleans up issue state', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_safety_update')).toBeVisible();

    await page.getByTestId('proposal-accept-proposal_safety_update').click();
    await expect(page.getByTestId('proposal-card-proposal_safety_update')).not.toBeVisible();

    await page.getByTestId('sidebar-section-workbench-history').click();
    const historyList = page.getByTestId('workbench-history-list');
    await expect(historyList).toContainText('Apply safe location correction');
    await expect(historyList.getByText('accepted').first()).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-issues').click();
    await expect(page.getByTestId('workbench-issues-list')).not.toContainText('Safety location mismatch');

    await page.getByTestId('activity-btn-world').click();
    await page.getByTestId('world-container-cont_safety').click();
    await page.getByTestId('world-item-safety_location').click();
    await expect(page.locator('textarea').first()).toHaveValue('The approved canonical description.');
  });

  test('rejecting a proposal moves it to history without mutating canonical data or closing the issue', async ({ page }) => {
    await page.getByTestId('proposal-reject-proposal_safety_update').click();
    await expect(page.getByTestId('proposal-card-proposal_safety_update')).not.toBeVisible();

    await page.getByTestId('sidebar-section-workbench-history').click();
    const historyList = page.getByTestId('workbench-history-list');
    await expect(historyList).toContainText('Apply safe location correction');
    await expect(historyList.getByText('rejected').first()).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-issues').click();
    await expect(page.getByTestId('workbench-issues-list')).toContainText('Safety location mismatch');

    await page.getByTestId('activity-btn-world').click();
    await page.getByTestId('world-container-cont_safety').click();
    await page.getByTestId('world-item-safety_location').click();
    await expect(page.locator('textarea').first()).toHaveValue('The original canonical description.');
  });

  test('accepting an unsupported canonical operation keeps the proposal pending and surfaces an issue', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_safety_unsupported')).toBeVisible();

    await page.getByTestId('proposal-accept-proposal_safety_unsupported').click();
    await expect(page.getByTestId('proposal-card-proposal_safety_unsupported')).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-history').click();
    await expect(page.getByTestId('workbench-history-list')).not.toContainText('Unsupported canonical operation');

    await page.getByTestId('sidebar-section-workbench-issues').click();
    await expect(page.getByTestId('workbench-issues-list')).toContainText('Proposal blocked: Unsupported canonical operation');
    await expect(page.getByTestId('workbench-issues-list')).toContainText('supported canonical change');
  });

  test('blocked proposal shows reason banner on card after accept attempt', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_safety_unsupported')).toBeVisible();

    // First attempt — triggers the block
    await page.getByTestId('proposal-accept-proposal_safety_unsupported').click();

    // Reason banner must appear on the card
    const reasonBanner = page.getByTestId('proposal-blocked-reason-proposal_safety_unsupported');
    await expect(reasonBanner).toBeVisible();
    await expect(reasonBanner).toContainText('supported canonical change');
  });

  test('accept button is disabled after a proposal is blocked', async ({ page }) => {
    await expect(page.getByTestId('proposal-card-proposal_safety_unsupported')).toBeVisible();

    // First attempt — triggers the block
    await page.getByTestId('proposal-accept-proposal_safety_unsupported').click();

    // Accept button must be disabled — no silent re-click possible
    const acceptBtn = page.getByTestId('proposal-accept-proposal_safety_unsupported');
    await expect(acceptBtn).toBeDisabled();
  });
});
