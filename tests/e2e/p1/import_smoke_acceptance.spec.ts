import { expect, test } from '@playwright/test';

const now = () => '2026-05-29T00:00:00.000Z';

const makeProposal = (id: string, entityType: string, fields: Record<string, unknown>) => ({
  id,
  title: `Create ${entityType}`,
  source: 'import',
  kind: 'entity_update',
  description: `Synthetic W1 import ${entityType}`,
  targetEntityType: entityType,
  targetEntityId: (fields.id as string) ?? null,
  targetEntityRefs: [],
  preview: String(fields.title || fields.name || fields.id || entityType),
  proposedOperations: [{ op: 'create', entityType, entityId: fields.id, fields }],
  reviewPolicy: 'manual_workbench',
  status: 'pending',
  createdAt: now(),
});

const makeUpdateProposal = (id: string, entityType: string, fields: Record<string, unknown>) => ({
  ...makeProposal(id, entityType, fields),
  title: `Update ${entityType}`,
  targetEntityId: (fields.id as string) ?? entityType,
  proposedOperations: [{ op: 'update', entityType, entityId: (fields.id as string) ?? entityType, fields }],
});

async function injectW1ImportBatch(page: import('@playwright/test').Page) {
  await page.goto('http://localhost:3000');
  await page.evaluate(({ proposals }) => {
    const store = (window as any).__narrativeStore;
    if (!store) throw new Error('__narrativeStore is not exposed in DEV mode');
    store.setState((state: any) => ({
      ...state,
      characters: [],
      characterTags: [],
      timelineEvents: [],
      timelineBranches: [{ id: 'branch_main', name: 'Main Branch', description: 'Default story branch.', sortOrder: 0, collapsed: false }],
      relationships: [],
      chapters: [{ id: 'chap_1', title: 'Chapter 1', summary: 'Starting chapter.', goal: '', notes: '', sceneIds: ['scene_1'], orderIndex: 0, status: 'draft' }],
      scenes: [{ id: 'scene_1', chapterId: 'chap_1', title: 'Scene 1', summary: 'Empty starter scene.', content: '', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' }],
      worldContainers: [
        { id: 'cont_locations', name: 'Locations', type: 'notebook', isDefault: true },
        { id: 'cont_orgs', name: 'Organizations', type: 'graph', isDefault: true },
        { id: 'cont_items', name: 'Items', type: 'notebook', isDefault: true },
      ],
      worldItems: [{ id: 'map_city', containerId: 'cont_locations', type: 'map', name: 'World Map', description: 'Blank map.', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [] }],
      proposals,
      proposalHistory: [],
      issues: [],
    }));
  }, {
    proposals: [
      makeProposal('p_branch', 'timeline_branch', { id: 'branch_zhang_tie', name: '张铁分支', description: '导入主线', sortOrder: 0, mode: 'root', collapsed: false }),
      makeProposal('p_container_location', 'world_container', { id: 'cont_import_locations', name: '地点', type: 'map', importCategoryKey: 'locations', isDefault: true }),
      makeProposal('p_container_methods', 'world_container', { id: 'cont_import_cultivation_methods', name: '功法与术法', type: 'notebook', importCategoryKey: 'cultivation_methods' }),
      makeProposal('p_chapter', 'chapter', { id: 'chap_3', title: '第三章', summary: '韩立进入七绝堂。', goal: '核对本章导入正文。', notes: 'Imported from smoke fixture.', sceneIds: [], orderIndex: 0, status: 'draft' }),
      makeProposal('p_scene', 'scene', { id: 'scene_chap_3', chapterId: 'chap_3', title: '章节正文', summary: '韩立进入七绝堂。', content: '韩立进入七绝堂，发现长春功残卷。', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' }),
      makeProposal('p_location', 'world_item', { id: 'world_qijue_tang', containerId: 'cont_import_locations', type: 'location', category: 'location', name: '七绝堂', description: '宗门内的一处堂口。', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [] }),
      makeProposal('p_method', 'world_item', { id: 'world_changchun_gong', containerId: 'cont_import_cultivation_methods', type: 'cultivation_method', category: 'cultivation_method', name: '长春功', description: '基础功法。', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [] }),
      makeProposal('p_char_han', 'character', { id: 'char_han_li', name: '韩立', summary: '主角。', background: '', aliases: [], tagIds: [], organizationIds: [], linkedSceneIds: ['scene_chap_3'], linkedEventIds: ['event_qijue'], linkedWorldItemIds: [], statusFlags: {}, importance: 'core' }),
      makeProposal('p_char_mo', 'character', { id: 'char_mo', name: '墨大夫', summary: '关键人物。', background: '', aliases: [], tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: ['event_qijue'], linkedWorldItemIds: [], statusFlags: {}, importance: 'major' }),
      makeProposal('p_event', 'timeline_event', { id: 'event_qijue', title: '进入七绝堂', summary: '韩立进入七绝堂并发现功法线索。', branchId: 'branch_zhang_tie', orderIndex: 0, locationIds: ['world_qijue_tang'], participantCharacterIds: ['char_han_li', 'char_mo'], linkedSceneIds: ['scene_chap_3'], linkedWorldItemIds: ['world_changchun_gong'], tags: ['imported'] }),
      makeProposal('p_relationship', 'relationship', { id: 'rel_han_mo', sourceId: 'char_han_li', targetId: 'char_mo', type: 'mentor', description: '墨大夫影响韩立早期修炼。', strength: 0.7 }),
    ],
  });
}

test.describe('W1 import smoke acceptance', () => {
  test('Accept All applies same-batch dependencies and removes blank starter defaults', async ({ page }) => {
    await injectW1ImportBatch(page);
    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByTestId('accept-all-proposals-btn')).toBeVisible();
    await page.getByTestId('accept-all-proposals-btn').click();
    await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return {
        chapters: s.chapters.map((chapter: any) => ({ id: chapter.id, title: chapter.title, summary: chapter.summary, sceneIds: chapter.sceneIds })),
        scenes: s.scenes.map((scene: any) => ({ id: scene.id, chapterId: scene.chapterId, title: scene.title, content: scene.content })),
        branches: s.timelineBranches.map((branch: any) => ({ id: branch.id, name: branch.name })),
        characters: s.characters.map((character: any) => character.name),
        events: s.timelineEvents.map((event: any) => ({ title: event.title, participants: event.participantCharacterIds })),
        relationships: s.relationships.map((rel: any) => rel.id),
        containers: s.worldContainers.map((container: any) => container.name),
        worldItems: s.worldItems.map((item: any) => ({ name: item.name, type: item.type, containerId: item.containerId })),
      };
    });

    expect(state.chapters).toEqual([{ id: 'chap_3', title: '第三章', summary: '韩立进入七绝堂。', sceneIds: ['scene_chap_3'] }]);
    expect(state.scenes).toEqual([{ id: 'scene_chap_3', chapterId: 'chap_3', title: '章节正文', content: '韩立进入七绝堂，发现长春功残卷。' }]);
    expect(state.branches).toEqual([{ id: 'branch_zhang_tie', name: '张铁分支' }]);
    expect(state.characters).toEqual(['韩立', '墨大夫']);
    expect(state.events[0].participants).toEqual(['char_han_li', 'char_mo']);
    expect(state.relationships).toEqual(['rel_han_mo']);
    expect(state.containers).toEqual(['地点', '功法与术法']);
    expect(state.worldItems.map((item: any) => item.name).sort()).toEqual(['七绝堂', '长春功']);
  });

  test('Accept All recovers stale W1 proposals with branch_main, duplicates, and world settings', async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.evaluate(({ proposals }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore is not exposed in DEV mode');
      store.setState((state: any) => ({
        ...state,
        timelineBranches: [{
          id: 'branch_item',
          name: '韩立修仙之路',
          description: 'Imported root branch.',
          sortOrder: 0,
          collapsed: false,
          mode: 'root',
        }],
        timelineEvents: [],
        characters: [],
        chapters: [{
          id: 'chap_1',
          title: '第一章',
          summary: 'Already accepted chapter.',
          goal: '',
          notes: '',
          sceneIds: ['scene_1'],
          orderIndex: 0,
          status: 'draft',
        }],
        scenes: [{
          id: 'scene_1',
          chapterId: 'chap_1',
          title: '章节正文',
          summary: 'Existing scene.',
          content: 'Existing manuscript text.',
          orderIndex: 0,
          povCharacterId: null,
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedWorldItemIds: [],
          status: 'draft',
        }],
        relationships: [],
        worldSettings: {
          projectType: 'novel',
          narrativePacing: '',
          languageStyle: '',
          narrativePerspective: '',
          lengthStrategy: '',
          worldRulesSummary: '',
        },
        proposals,
        proposalHistory: [],
        issues: [],
      }));
    }, {
      proposals: [
        makeProposal('p_event_stale_branch', 'timeline_event', {
          id: 'event_legacy_branch',
          title: '七玄门王护法接走韩立',
          summary: '事件来自 W1 遗留 proposal。',
          branchId: 'branch_main',
          orderIndex: 0,
          locationIds: [],
          participantCharacterIds: ['char_han_li'],
          linkedSceneIds: ['scene_1'],
          linkedWorldItemIds: [],
          tags: ['imported'],
        }),
        makeProposal('p_char_depends_event', 'character', {
          id: 'char_han_li',
          name: '韩立',
          summary: '主角。',
          background: '',
          aliases: [],
          tagIds: [],
          organizationIds: [],
          linkedSceneIds: ['scene_1'],
          linkedEventIds: ['event_legacy_branch'],
          linkedWorldItemIds: [],
          statusFlags: {},
          importance: 'core',
        }),
        makeProposal('p_duplicate_chapter', 'chapter', {
          id: 'chap_1',
          title: '第一章',
          summary: 'Duplicate proposal from an already accepted W1 chapter.',
          goal: '',
          notes: '',
          sceneIds: ['scene_1'],
          orderIndex: 0,
          status: 'draft',
        }),
        makeUpdateProposal('p_world_settings', 'world_settings', {
          projectType: 'xianxia',
          worldRulesSummary: '七玄门、修仙功法、江湖门派并存。',
        }),
      ],
    });

    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByTestId('accept-all-proposals-btn')).toBeVisible();
    await page.getByTestId('accept-all-proposals-btn').click();
    await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return {
        proposals: s.proposals,
        history: s.proposalHistory.map((proposal: any) => proposal.id),
        events: s.timelineEvents.map((event: any) => ({ id: event.id, branchId: event.branchId })),
        characters: s.characters.map((character: any) => ({ id: character.id, linkedEventIds: character.linkedEventIds })),
        chapters: s.chapters.map((chapter: any) => ({ id: chapter.id, title: chapter.title })),
        worldSettings: s.worldSettings,
      };
    });

    expect(state.proposals).toEqual([]);
    expect(state.history).toEqual(expect.arrayContaining(['p_event_stale_branch', 'p_char_depends_event', 'p_duplicate_chapter', 'p_world_settings']));
    expect(state.events).toEqual([{ id: 'event_legacy_branch', branchId: 'branch_item' }]);
    expect(state.characters).toEqual([{ id: 'char_han_li', linkedEventIds: ['event_legacy_branch'] }]);
    expect(state.chapters).toEqual([{ id: 'chap_1', title: '第一章' }]);
    expect(state.worldSettings.worldRulesSummary).toContain('七玄门');
  });

  test('imported chapter detail and manuscript scene content are visible in Writing', async ({ page }) => {
    await injectW1ImportBatch(page);
    await page.getByTestId('activity-btn-workbench').click();
    await page.getByTestId('accept-all-proposals-btn').click();
    await page.getByTestId('activity-btn-writing').click();
    await page.getByTestId('sidebar-section-writing-chapters').click();

    await expect(page.getByTestId('chapter-title-input')).toHaveValue('第三章');
    await expect(page.getByTestId('chapter-summary-input')).toHaveValue('韩立进入七绝堂。');
    await expect(page.getByTestId('chapter-goal-input')).toHaveValue('核对本章导入正文。');
    await expect(page.getByTestId('chapter-preview-btn-chap_3')).toBeVisible();
    await page.getByTestId('chapter-preview-btn-chap_3').click();
    await expect(page.getByTestId('chapter-preview-modal')).toContainText('韩立进入七绝堂');
  });
});
