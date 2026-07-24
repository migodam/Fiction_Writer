import { expect, test } from '@playwright/test';

test('approved world-to-character relocation is atomic, preserves profile data, and removes dangling references', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_relocate', name: '世界模型', type: 'notebook', sortOrder: 0 }],
      worldItems: [{ id: 'world_wang', folderId: 'nb_relocate', containerId: 'nb_relocate', type: 'organization', name: '正门主王六', description: '', attributes: [{ key: '境界', value: '炼气期' }], linkedCharacterIds: [], linkedEventIds: ['event_relocate'], linkedSceneIds: ['scene_relocate'], mapMarkers: [], tagIds: [] }],
      characters: [{ id: 'char_wang', name: '王六', summary: '', background: '', aliases: ['王6'], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: ['world_wang'], statusFlags: {} }],
      timelineBranches: [{ id: 'branch_relocate', name: '主线', sortOrder: 0, mode: 'root' }],
      timelineEvents: [{ id: 'event_relocate', title: '入门', summary: '', branchId: 'branch_relocate', orderIndex: 0, locationIds: ['world_wang'], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: ['world_wang'], tags: [] }],
      chapters: [{ id: 'chapter_relocate', title: '第一章', summary: '', goal: '', notes: '', sceneIds: ['scene_relocate'], orderIndex: 0, status: 'draft' }],
      scenes: [{ id: 'scene_relocate', chapterId: 'chapter_relocate', title: '相遇', summary: '', content: '', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: ['world_wang'], status: 'draft' }],
      proposals: [{ id: 'proposal_relocate', title: '搬运正门主王六', source: 'quality_reviewer', kind: 'import_review', description: '', targetEntityType: 'world_item', targetEntityId: 'world_wang', preview: '', reviewPolicy: 'manual_workbench', status: 'pending', createdAt: '2026-07-25T00:00:00.000Z', proposedOperations: [{ op: 'relocate_world_item_to_character', entityType: 'world_item', entityId: 'world_wang', fields: { sourceWorldItemId: 'world_wang', targetCharacterId: 'char_wang', aliases: ['王大门主'], role: '正门主', evidenceRefs: ['evidence_01'], customAttributes: { 身份: '七玄门正门主' } } }] }],
      proposalHistory: [], issues: [],
    }));
  });
  await page.evaluate(() => (window as any).__narrativeStore.getState().resolveProposal('proposal_relocate', 'accepted'));
  const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
  expect(state.worldItems.find((item: any) => item.id === 'world_wang')).toBeUndefined();
  const character = state.characters.find((item: any) => item.id === 'char_wang');
  expect(character.aliases).toEqual(expect.arrayContaining(['王6', '正门主王六', '王大门主']));
  expect(character.role).toBe('正门主');
  expect(character.linkedEventIds).toContain('event_relocate');
  expect(character.linkedSceneIds).toContain('scene_relocate');
  expect(character.customAttributes).toEqual(expect.arrayContaining([expect.objectContaining({ label: '境界', value: '炼气期' }), expect.objectContaining({ label: '身份', value: '七玄门正门主' })]));
  expect(state.timelineEvents[0].locationIds).not.toContain('world_wang');
  expect(state.timelineEvents[0].linkedWorldItemIds).not.toContain('world_wang');
  expect(state.scenes[0].linkedWorldItemIds).not.toContain('world_wang');
});

test('relocation proposal stays pending when its target character is missing', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_missing', name: '世界模型', type: 'notebook', sortOrder: 0 }],
      worldItems: [{ id: 'world_missing', folderId: 'nb_missing', containerId: 'nb_missing', type: 'note', name: '待搬运', description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [] }],
      proposals: [{ id: 'proposal_missing_target', title: '无效搬运', source: 'quality_reviewer', kind: 'import_review', description: '', targetEntityType: 'world_item', targetEntityId: 'world_missing', preview: '', reviewPolicy: 'manual_workbench', status: 'pending', createdAt: '2026-07-25T00:00:00.000Z', proposedOperations: [{ op: 'relocate_world_item_to_character', entityType: 'world_item', entityId: 'world_missing', fields: { targetCharacterId: 'char_not_found' } }] }],
    }));
  });
  await page.evaluate(() => (window as any).__narrativeStore.getState().resolveProposal('proposal_missing_target', 'accepted'));
  const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
  expect(state.proposals.find((proposal: any) => proposal.id === 'proposal_missing_target')).toMatchObject({
    status: 'pending',
    lastBlockReason: expect.stringContaining('target character char_not_found does not exist'),
  });
});

test('reviewer relocation_plan wire format is accepted by the canonical applier', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_wire', name: '世界模型', type: 'notebook', sortOrder: 0 }],
      worldItems: [{ id: 'world_wire', folderId: 'nb_wire', containerId: 'nb_wire', type: 'organization', name: '正门主王六', description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [] }],
      characters: [{ id: 'char_wire', name: '王六', summary: '', background: '', aliases: ['王6'], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: ['world_wire'], statusFlags: {} }],
      proposals: [{
        id: 'proposal_wire',
        title: '搬运人物职务混合条目',
        source: 'quality_reviewer',
        kind: 'import_review',
        description: '',
        targetEntityType: 'world_item',
        targetEntityId: 'world_wire',
        preview: '',
        reviewPolicy: 'manual_workbench',
        status: 'pending',
        createdAt: '2026-07-25T00:00:00.000Z',
        proposedOperations: [{
          op: 'relocate_world_item',
          entityType: 'world_item',
          entityId: 'world_wire',
          relocation_plan: {
            plan_id: 'relocate_world_wire_to_char_wire',
            source_candidate_id: 'world_wire',
            target_kind: 'character',
            target_entity_id: 'char_wire',
            field_merge_plan: {
              aliases: ['正门主王六'],
              role: '正门主',
              evidence_refs: ['evidence_wire'],
            },
            status: 'approved',
            deterministic: true,
          },
        }],
      }],
      proposalHistory: [],
      issues: [],
    }));
  });

  await page.evaluate(() => (window as any).__narrativeStore.getState().resolveProposal('proposal_wire', 'accepted'));
  const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
  expect(state.worldItems.some((item: any) => item.id === 'world_wire')).toBe(false);
  expect(state.characters.find((item: any) => item.id === 'char_wire')).toMatchObject({
    aliases: expect.arrayContaining(['王6', '正门主王六']),
    role: '正门主',
    evidenceRefs: ['evidence_wire'],
  });
});
