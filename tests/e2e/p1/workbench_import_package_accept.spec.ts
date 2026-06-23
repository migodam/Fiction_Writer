import { expect, test } from '@playwright/test';

const now = () => '2026-05-31T00:00:00.000Z';

const packageTestId = (packageId: string) => `import-${packageId}`;

const makePackageProposal = (
  packageId: string,
  id: string,
  entityType: string,
  fields: Record<string, unknown>,
  title = `Create ${entityType}`,
) => ({
  id,
  title,
  source: 'import',
  kind: 'entity_update',
  description: `Synthetic import package proposal for ${entityType}`,
  targetEntityType: entityType,
  targetEntityId: (fields.id as string) ?? null,
  targetEntityRefs: [],
  preview: String(fields.title || fields.name || fields.id || entityType),
  proposedOperations: [{ op: 'create', entityType, entityId: fields.id, fields: { ...fields, importRunId: packageId } }],
  reviewPolicy: 'manual_workbench',
  status: 'pending',
  createdAt: now(),
  source_workflow: 'W1_import',
  importRunId: packageId,
  packageId,
});

async function injectImportPackage(page: import('@playwright/test').Page, proposals: unknown[]) {
  await page.goto('http://localhost:3000');
  await page.evaluate(({ proposals }) => {
    const store = (window as any).__narrativeStore;
    if (!store) throw new Error('__narrativeStore is not exposed in DEV mode');
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
  }, { proposals });
  await page.getByTestId('activity-btn-workbench').click();
}

test.describe('Workbench import package accept', () => {
  test('accepts same-package branch, event, character, relationship, and world item references together', async ({ page }) => {
    const packageId = 'pkg_accept_success';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_branch', 'timeline_branch', {
        id: 'branch_pkg_arc',
        name: 'Package Arc',
        description: 'Imported package branch.',
        sortOrder: 0,
        mode: 'root',
        collapsed: false,
      }),
      makePackageProposal(packageId, 'pkg_container', 'world_container', {
        id: 'cont_pkg_locations',
        name: 'Package Locations',
        type: 'map',
        isDefault: true,
      }),
      makePackageProposal(packageId, 'pkg_world', 'world_item', {
        id: 'world_pkg_gate',
        containerId: 'cont_pkg_locations',
        type: 'location',
        name: 'Silver Gate',
        description: 'A same-package location.',
        attributes: [],
        linkedCharacterIds: ['char_pkg_hero'],
        linkedEventIds: ['event_pkg_cross'],
        linkedSceneIds: [],
      }),
      makePackageProposal(packageId, 'pkg_hero', 'character', {
        id: 'char_pkg_hero',
        name: 'Mira',
        summary: 'Package hero.',
        background: '',
        aliases: [],
        tagIds: [],
        organizationIds: [],
        linkedSceneIds: [],
        linkedEventIds: ['event_pkg_cross'],
        linkedWorldItemIds: ['world_pkg_gate'],
        statusFlags: {},
      }),
      makePackageProposal(packageId, 'pkg_mentor', 'character', {
        id: 'char_pkg_mentor',
        name: 'Soren',
        summary: 'Package mentor.',
        background: '',
        aliases: [],
        tagIds: [],
        organizationIds: [],
        linkedSceneIds: [],
        linkedEventIds: ['event_pkg_cross'],
        linkedWorldItemIds: [],
        statusFlags: {},
      }),
      makePackageProposal(packageId, 'pkg_event', 'timeline_event', {
        id: 'event_pkg_cross',
        title: 'Cross the Silver Gate',
        summary: 'Mira and Soren enter the gate.',
        branchId: 'branch_pkg_arc',
        orderIndex: 0,
        locationIds: ['world_pkg_gate'],
        participantCharacterIds: ['char_pkg_hero', 'char_pkg_mentor'],
        linkedSceneIds: [],
        linkedWorldItemIds: ['world_pkg_gate'],
        tags: ['imported'],
      }),
      makePackageProposal(packageId, 'pkg_relationship', 'relationship', {
        id: 'rel_pkg_hero_mentor',
        sourceId: 'char_pkg_hero',
        targetId: 'char_pkg_mentor',
        type: 'mentor',
        description: 'Soren guides Mira.',
        strength: 0.8,
      }),
    ]);

    await expect(page.getByTestId(`import-package-${packageTestId(packageId)}`)).toBeVisible();
    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return {
        branches: s.timelineBranches.map((branch: any) => branch.id),
        events: s.timelineEvents.map((event: any) => ({
          id: event.id,
          branchId: event.branchId,
          participants: event.participantCharacterIds,
          locationIds: event.locationIds,
        })),
        characters: s.characters.map((character: any) => ({
          id: character.id,
          linkedEventIds: character.linkedEventIds,
          linkedWorldItemIds: character.linkedWorldItemIds,
        })),
        relationships: s.relationships.map((relationship: any) => ({
          id: relationship.id,
          sourceId: relationship.sourceId,
          targetId: relationship.targetId,
        })),
        worldItems: s.worldItems.map((item: any) => ({
          id: item.id,
          containerId: item.containerId,
          linkedCharacterIds: item.linkedCharacterIds,
          linkedEventIds: item.linkedEventIds,
        })),
        history: s.proposalHistory.map((proposal: any) => proposal.id),
      };
    });

    expect(state.branches).toEqual(['branch_pkg_arc']);
    expect(state.events).toEqual([{
      id: 'event_pkg_cross',
      branchId: 'branch_pkg_arc',
      participants: ['char_pkg_hero', 'char_pkg_mentor'],
      locationIds: ['world_pkg_gate'],
    }]);
    expect(state.characters).toEqual(expect.arrayContaining([
      { id: 'char_pkg_hero', linkedEventIds: ['event_pkg_cross'], linkedWorldItemIds: ['world_pkg_gate'] },
      { id: 'char_pkg_mentor', linkedEventIds: ['event_pkg_cross'], linkedWorldItemIds: [] },
    ]));
    expect(state.relationships).toEqual([{ id: 'rel_pkg_hero_mentor', sourceId: 'char_pkg_hero', targetId: 'char_pkg_mentor' }]);
    expect(state.worldItems).toEqual([{
      id: 'world_pkg_gate',
      containerId: 'cont_pkg_locations',
      linkedCharacterIds: ['char_pkg_hero'],
      linkedEventIds: ['event_pkg_cross'],
    }]);
    expect(state.history).toEqual(expect.arrayContaining([
      'pkg_branch',
      'pkg_container',
      'pkg_world',
      'pkg_hero',
      'pkg_mentor',
      'pkg_event',
      'pkg_relationship',
    ]));
  });

  test('rolls back the whole package when one proposal has a blocking edge', async ({ page }) => {
    const packageId = 'pkg_accept_failure';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_fail_branch', 'timeline_branch', {
        id: 'branch_pkg_fail',
        name: 'Rollback Branch',
        sortOrder: 0,
        mode: 'root',
        collapsed: false,
      }),
      makePackageProposal(packageId, 'pkg_fail_char', 'character', {
        id: 'char_pkg_ok',
        name: 'Rollback Hero',
        summary: 'Should not persist after package failure.',
        background: '',
        aliases: [],
        tagIds: [],
        organizationIds: [],
        linkedSceneIds: [],
        linkedEventIds: [],
        linkedWorldItemIds: [],
        statusFlags: {},
      }),
      makePackageProposal(packageId, 'pkg_fail_event', 'timeline_event', {
        id: 'event_pkg_fail',
        title: 'Broken Import Event',
        summary: 'References a missing character.',
        branchId: 'branch_pkg_fail',
        orderIndex: 0,
        locationIds: [],
        participantCharacterIds: ['char_missing'],
        linkedSceneIds: [],
        linkedWorldItemIds: [],
        tags: ['imported'],
      }),
    ]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    await expect(page.getByTestId(`import-package-${packageTestId(packageId)}`)).toBeVisible();

    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return {
        proposals: s.proposals.map((proposal: any) => ({
          id: proposal.id,
          lastBlockReason: proposal.lastBlockReason,
        })),
        history: s.proposalHistory,
        branches: s.timelineBranches.map((branch: any) => branch.id),
        characters: s.characters.map((character: any) => character.id),
        events: s.timelineEvents.map((event: any) => event.id),
      };
    });

    expect(state.history).toEqual([]);
    expect(state.branches).toEqual([]);
    expect(state.characters).toEqual([]);
    expect(state.events).toEqual([]);
    expect(state.proposals).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'pkg_fail_branch', lastBlockReason: expect.stringContaining('char_missing') }),
      expect.objectContaining({ id: 'pkg_fail_char', lastBlockReason: expect.stringContaining('char_missing') }),
      expect.objectContaining({ id: 'pkg_fail_event', lastBlockReason: expect.stringContaining('char_missing') }),
    ]));
  });

  test('shows a readable blocked reason with the blocking edge', async ({ page }) => {
    const packageId = 'pkg_readable_reason';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_reason_branch', 'timeline_branch', {
        id: 'branch_pkg_reason',
        name: 'Readable Branch',
        sortOrder: 0,
        mode: 'root',
        collapsed: false,
      }),
      makePackageProposal(packageId, 'pkg_reason_event', 'timeline_event', {
        id: 'event_pkg_reason',
        title: 'Readable Broken Event',
        summary: 'References a missing participant.',
        branchId: 'branch_pkg_reason',
        orderIndex: 0,
        locationIds: [],
        participantCharacterIds: ['char_reason_missing'],
        linkedSceneIds: [],
        linkedWorldItemIds: [],
        tags: ['imported'],
      }),
    ]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();

    const packageReason = page.getByTestId(`import-package-blocked-reason-${packageTestId(packageId)}`);
    await expect(packageReason).toBeVisible();
    await expect(packageReason).toContainText('Blocking edge');
    await expect(packageReason).toContainText('timeline_event event_pkg_reason');
    await expect(packageReason).toContainText('char_reason_missing');
    await expect(packageReason).toContainText('Reason:');

    const proposalReason = page.getByTestId('proposal-blocked-reason-pkg_reason_event');
    await expect(proposalReason).toContainText('Blocking edge');
    await expect(page.getByTestId(`accept-import-package-${packageTestId(packageId)}`)).toBeEnabled();
  });
});
