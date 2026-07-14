import { expect, test } from '@playwright/test';

const now = () => '2026-05-31T00:00:00.000Z';

const packageTestId = (packageId: string) => `import-${packageId}`;
const sourceSpan = (sourceHash: string, content: string, start = 0, end = Array.from(content).length, substringHash = sourceHash) => ({
  raw_source_hash: sourceHash,
  absolute_start: start,
  absolute_end: end,
  substring_hash: substringHash,
});

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

const makeStagedProjectionPackage = (packageId: string, artifactPath: string, chapterId = 'chap_projection', sceneId = 'scene_projection') => [
  makePackageProposal(packageId, `${packageId}_chapter`, 'chapter', {
    id: chapterId, title: 'Projection Chapter', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
    stagedManuscriptProjection: { artifact_path: artifactPath, contract_version: 'w1-staged-manuscript-v1', chapter_id: chapterId, scene_id: sceneId },
  }),
  makePackageProposal(packageId, `${packageId}_scene`, 'scene', {
    id: sceneId, chapterId, title: 'Chapter Text', summary: '', content: 'Proposal-owned preview only.', orderIndex: 0,
    povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft',
    stagedManuscriptProjection: { artifact_path: artifactPath, contract_version: 'w1-staged-manuscript-v1', chapter_id: chapterId, scene_id: sceneId },
  }),
];

const makeProjection = (packageId: string, sourceHash: string, chapterId = 'chap_projection', sceneId = 'scene_projection') => ({
  contract_version: 'w1-staged-manuscript-v1',
  import_run_id: packageId,
  acceptance_required: true,
  chapters: [{ chapter_id: chapterId, scene_id: sceneId, source_span: sourceSpan(sourceHash, 'Projection-owned manuscript content.') }],
  nodes: [
    { id: `mn_${chapterId}`, title: 'Projection Chapter', type: 'chapter_outline', parentId: null, orderIndex: 0, linkedChapterId: chapterId, linkedSceneId: null, depth: 0, collapsed: false, wordCount: 3 },
    { id: `mn_${sceneId}`, title: 'Chapter Text', type: 'scene_outline', parentId: `mn_${chapterId}`, orderIndex: 0, linkedChapterId: chapterId, linkedSceneId: sceneId, depth: 1, collapsed: false, wordCount: 3 },
  ],
  scene_documents: [{ node_id: `mn_${sceneId}`, scene_id: sceneId, content: 'Projection-owned manuscript content.', source_span: sourceSpan(sourceHash, 'Projection-owned manuscript content.') }],
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

async function installProjectionFilesystem(
  page: import('@playwright/test').Page,
  artifactPath: string,
  projection: Record<string, unknown>,
  manifest: Record<string, unknown>,
  escapedArtifactPath?: string,
  sourceTextOverride?: string,
  sourcePathOverride?: string,
  escapedSourcePath?: string,
) {
  const manifestPath = artifactPath.replace(/staged_manuscript_projection\.json$/, 'manifest.json');
  const runDirectory = artifactPath.replace(/\/staged_manuscript_projection\.json$/, '');
  const sourcePath = sourcePathOverride ?? `${runDirectory}/raw_source.txt`;
  const sourceText = sourceTextOverride ?? String(((projection.scene_documents as Array<Record<string, unknown>> | undefined)?.[0]?.content) || '');
  const sourceHash = String(((projection.chapters as Array<Record<string, unknown>> | undefined)?.[0]?.source_span as Record<string, unknown> | undefined)?.raw_source_hash || '');
  const projectionPayload = { ...projection, source_file_path: sourcePath };
  await page.addInitScript(
    ({ artifactPath, manifestPath, runDirectory, projectionPayload, manifest, escapedArtifactPath, sourcePath, escapedSourcePath, sourceText, sourceHash }) => {
      (window as any).require = (moduleName: string) => {
        if (moduleName === 'fs') return {
          existsSync: (path: string) => path === artifactPath || path === manifestPath || path === runDirectory || path === sourcePath,
          realpathSync: (path: string) => path === artifactPath && escapedArtifactPath
            ? escapedArtifactPath
            : path === sourcePath && escapedSourcePath ? escapedSourcePath : path,
          readFileSync: (path: string) => path === artifactPath ? JSON.stringify(projectionPayload) : path === manifestPath ? JSON.stringify(manifest) : path === sourcePath ? sourceText : '',
        };
        if (moduleName === 'crypto') return {
          createHash: () => {
            let value = '';
            return {
              update: (next: string) => { value += next; return { digest: () => value === sourceText ? sourceHash : `hash:${value}` }; },
            };
          },
        };
        if (moduleName === 'path') return {
          resolve: (...parts: string[]) => parts.join('/').replace(/\/+/g, '/'),
          relative: (from: string, to: string) => to.startsWith(from) ? to.slice(from.length).replace(/^\/+/, '') : '../outside',
          isAbsolute: (path: string) => path.startsWith('/'),
        };
        if (moduleName === 'process' || moduleName === 'buffer') return {};
        throw new Error(`Unexpected module: ${moduleName}`);
      };
    },
    { artifactPath, manifestPath, runDirectory, projectionPayload, manifest, escapedArtifactPath, sourcePath, escapedSourcePath, sourceText, sourceHash },
  );
}

test.describe('Workbench import package accept', () => {
  test('consumes a staged manuscript projection atomically with its import package', async ({ page }) => {
    const packageId = 'pkg_staged_projection';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_projection';
    const projection = {
      contract_version: 'w1-staged-manuscript-v1',
      import_run_id: packageId,
      acceptance_required: true,
      chapters: [{ chapter_id: 'chap_projection', scene_id: 'scene_projection', source_span: sourceSpan(sourceHash, 'Projection-owned manuscript content.') }],
      nodes: [
        { id: 'mn_chap_projection', title: 'Projection Chapter', type: 'chapter_outline', parentId: null, orderIndex: 0, linkedChapterId: 'chap_projection', linkedSceneId: null, depth: 0, collapsed: false, wordCount: 3 },
        { id: 'mn_scene_projection', title: 'Chapter Text', type: 'scene_outline', parentId: 'mn_chap_projection', orderIndex: 0, linkedChapterId: 'chap_projection', linkedSceneId: 'scene_projection', depth: 1, collapsed: false, wordCount: 3 },
      ],
      scene_documents: [{ node_id: 'mn_scene_projection', scene_id: 'scene_projection', content: 'Projection-owned manuscript content.', source_span: sourceSpan(sourceHash, 'Projection-owned manuscript content.') }],
    };
    await installProjectionFilesystem(page, artifactPath, projection, { import_run_id: packageId, source_hash: sourceHash });

    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_projection_chapter', 'chapter', {
        id: 'chap_projection', title: 'Projection Chapter', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
        stagedManuscriptProjection: { artifact_path: artifactPath, contract_version: 'w1-staged-manuscript-v1', chapter_id: 'chap_projection', scene_id: 'scene_projection' },
      }),
      makePackageProposal(packageId, 'pkg_projection_scene', 'scene', {
        id: 'scene_projection', chapterId: 'chap_projection', title: 'Chapter Text', summary: '', content: 'Proposal-owned preview only.', orderIndex: 0,
        povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft',
        stagedManuscriptProjection: { artifact_path: artifactPath, contract_version: 'w1-staged-manuscript-v1', chapter_id: 'chap_projection', scene_id: 'scene_projection' },
      }),
    ]);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({
        ...state,
        projectRoot: '/project',
        currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } },
      }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return {
        sceneContent: s.scenes.find((scene: any) => scene.id === 'scene_projection')?.content,
        manuscriptNodes: s.manuscriptNodes.map((node: any) => node.id),
      };
    });
    expect(state.sceneContent).toBe('Projection-owned manuscript content.');
    expect(state.manuscriptNodes).toEqual(expect.arrayContaining(['mn_chap_projection', 'mn_scene_projection']));
  });

  test('rolls back an import package when its staged manuscript projection is invalid', async ({ page }) => {
    const packageId = 'pkg_invalid_projection';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_invalid';
    const projection = {
      contract_version: 'w1-staged-manuscript-v1',
      import_run_id: packageId,
      acceptance_required: true,
      chapters: [],
      nodes: [],
      scene_documents: [{ node_id: 'mn_missing', scene_id: 'scene_not_in_package', content: 'Must not be written.' }],
    };
    await installProjectionFilesystem(page, artifactPath, projection, { import_run_id: packageId, source_hash: sourceHash });
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_invalid_projection_chapter', 'chapter', {
        id: 'chap_invalid_projection', title: 'Invalid Projection', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
        stagedManuscriptProjection: { artifact_path: artifactPath, contract_version: 'w1-staged-manuscript-v1' },
      }),
      makePackageProposal(packageId, 'pkg_invalid_projection_scene', 'scene', {
        id: 'scene_invalid_projection', chapterId: 'chap_invalid_projection', title: 'Chapter Text', summary: '', content: 'Proposal content.', orderIndex: 0,
        povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft',
        stagedManuscriptProjection: { artifact_path: artifactPath, contract_version: 'w1-staged-manuscript-v1' },
      }),
    ]);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    await expect(page.getByTestId(`retry-blocked-package-${packageTestId(packageId)}`)).toBeVisible();
    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return { chapters: s.chapters, scenes: s.scenes, manuscriptNodes: s.manuscriptNodes };
    });
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.manuscriptNodes).toEqual([]);
  });

  test('never overwrites an unrelated existing scene with a staged projection', async ({ page }) => {
    const packageId = 'pkg_projection_existing_scene';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_existing_scene';
    await installProjectionFilesystem(page, artifactPath, makeProjection(packageId, sourceHash), { import_run_id: packageId, source_hash: sourceHash });
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({
        ...state,
        projectRoot: '/project',
        scenes: [{ id: 'scene_projection', chapterId: 'chap_unrelated', title: 'Keep me', summary: '', content: 'Unrelated canonical text.', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' }],
      }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.scenes[0].content).toBe('Unrelated canonical text.');
    expect(state.chapters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('Cannot create duplicate scene scene_projection');
  });

  test('blocks malformed artifact chapter-to-scene mappings before package mutation', async ({ page }) => {
    const packageId = 'pkg_projection_bad_mapping';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_bad_mapping';
    await installProjectionFilesystem(page, artifactPath, makeProjection(packageId, sourceHash, 'chap_other', 'scene_other'), { import_run_id: packageId, source_hash: sourceHash });
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('chapters do not exactly match');
  });

  test('blocks a cross-run artifact and preserves package rollback', async ({ page }) => {
    const packageId = 'pkg_projection_cross_run';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_cross_run';
    const projection = { ...makeProjection(packageId, sourceHash), import_run_id: 'different_run' };
    await installProjectionFilesystem(page, artifactPath, projection, { import_run_id: packageId, source_hash: sourceHash });
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('importRunId, or source hash');
  });

  test('blocks a projection whose chapter source hash disagrees with its run manifest', async ({ page }) => {
    const packageId = 'pkg_projection_source_hash';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    await installProjectionFilesystem(
      page,
      artifactPath,
      makeProjection(packageId, 'artifact_source_hash'),
      { import_run_id: packageId, source_hash: 'manifest_source_hash' },
    );
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('raw source does not match its manifest hash');
  });

  test('blocks a staged projection that resolves through a symlink', async ({ page }) => {
    const packageId = 'pkg_projection_symlink';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_symlink';
    await installProjectionFilesystem(
      page,
      artifactPath,
      makeProjection(packageId, sourceHash),
      { import_run_id: packageId, source_hash: sourceHash },
      '/outside/staged_manuscript_projection.json',
    );
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('resolves through a symlink');
  });

  test('blocks raw source evidence outside the import run', async ({ page }) => {
    const packageId = 'pkg_projection_external_source';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_external';
    await installProjectionFilesystem(
      page,
      artifactPath,
      makeProjection(packageId, sourceHash),
      { import_run_id: packageId, source_hash: sourceHash },
      undefined,
      undefined,
      '/outside/raw_source.txt',
    );
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('raw_source.txt inside its import run');
  });

  test('blocks raw source evidence that resolves through a symlink', async ({ page }) => {
    const packageId = 'pkg_projection_source_symlink';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_source_symlink';
    await installProjectionFilesystem(
      page,
      artifactPath,
      makeProjection(packageId, sourceHash),
      { import_run_id: packageId, source_hash: sourceHash },
      undefined,
      undefined,
      undefined,
      '/outside/raw_source.txt',
    );
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project' }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('raw source evidence resolves through a symlink');
  });

  test('keeps a single-proposal import staged until its package is accepted', async ({ page }) => {
    const packageId = 'pkg_singleton_staged';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_singleton_chapter', 'chapter', {
        id: 'chap_singleton',
        title: 'Staged Chapter',
        summary: 'This import must remain staged.',
        goal: '',
        notes: '',
        sceneIds: [],
        orderIndex: 0,
        status: 'draft',
      }),
    ]);

    const testId = packageTestId(packageId);
    await expect(page.getByTestId(`import-package-${testId}`)).toBeVisible();
    await expect(page.getByTestId('proposal-card-pkg_singleton_chapter')).toHaveCount(0);
    await expect(page.getByTestId('accept-all-proposals-btn')).toHaveCount(0);
    await page.getByTestId('sidebar-section-workbench-tasks').click();
    await page.getByTestId('backlog-proposals-tab').click();
    await expect(page.getByTestId('proposal-item-pkg_singleton_chapter')).toHaveCount(0);
    await page.getByTestId('sidebar-section-workbench-inbox').click();

    const staged = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return { chapters: s.chapters, proposals: s.proposals.map((proposal: any) => proposal.id) };
    });
    expect(staged.chapters).toEqual([]);
    expect(staged.proposals).toEqual(['pkg_singleton_chapter']);

    await page.getByTestId(`accept-import-package-${testId}`).click();
    await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');
    const accepted = await page.evaluate(() => (window as any).__narrativeStore.getState().chapters.map((chapter: any) => chapter.id));
    expect(accepted).toEqual(['chap_singleton']);
  });

  test('rejecting one package does not resolve a different import run', async ({ page }) => {
    await injectImportPackage(page, [
      makePackageProposal('pkg_reject_a', 'pkg_reject_a_chapter', 'chapter', {
        id: 'chap_reject_a', title: 'Reject A', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
      }),
      makePackageProposal('pkg_reject_b', 'pkg_reject_b_chapter', 'chapter', {
        id: 'chap_reject_b', title: 'Keep B', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
      }),
    ]);

    await page.getByTestId('reject-import-package-import-pkg_reject_a').click();
    await expect(page.getByTestId('import-package-import-pkg_reject_b')).toBeVisible();
    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return { pending: s.proposals.map((proposal: any) => proposal.id), history: s.proposalHistory.map((proposal: any) => proposal.id), chapters: s.chapters };
    });
    expect(state.pending).toEqual(['pkg_reject_b_chapter']);
    expect(state.history).toEqual(['pkg_reject_a_chapter']);
    expect(state.chapters).toEqual([]);
  });

  test('blocks imported create with a canonical ID collision instead of reporting false success', async ({ page }) => {
    const packageId = 'pkg_character_id_collision';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'collision_branch', 'timeline_branch', { id: 'branch_collision', name: 'Must roll back', sortOrder: 0, mode: 'root', collapsed: false }),
      makePackageProposal(packageId, 'collision_character', 'character', { id: 'char_canonical', name: 'Imported impostor', aliases: [], tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }),
    ]);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, characters: [{ id: 'char_canonical', name: 'Canonical Hero', summary: 'Preserve me.', background: '', aliases: [], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }] }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.timelineBranches).toEqual([]);
    expect(state.characters).toEqual([expect.objectContaining({ id: 'char_canonical', name: 'Canonical Hero', summary: 'Preserve me.' })]);
    expect(state.proposals[0].lastBlockReason).toContain('Cannot create duplicate character char_canonical');
  });

  test('blocks same-name or alias character creates without an EntityMergeDecision', async ({ page }) => {
    const packageId = 'pkg_character_semantic_conflict';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'semantic_branch', 'timeline_branch', { id: 'branch_semantic', name: 'Must roll back', sortOrder: 0, mode: 'root', collapsed: false }),
      makePackageProposal(packageId, 'semantic_character', 'character', { id: 'char_imported', name: 'Alias Hero', summary: 'A much longer imported summary must not win.', background: '', aliases: ['Canonical Hero'], tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }),
    ]);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, characters: [{ id: 'char_canonical', name: 'Canonical Hero', summary: 'Canonical summary.', background: '', aliases: ['Alias Hero'], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }] }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.timelineBranches).toEqual([]);
    expect(state.characters).toEqual([expect.objectContaining({ id: 'char_canonical', summary: 'Canonical summary.' })]);
    expect(state.proposals[0].lastBlockReason).toContain('EntityMergeDecision/v1');
  });

  test('rolls back missing branch and reference edges rather than filtering or defaulting them', async ({ page }) => {
    const packageId = 'pkg_missing_branch_and_refs';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'missing_refs_character', 'character', { id: 'char_would_create', name: 'Must roll back', aliases: [], tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }),
      makePackageProposal(packageId, 'missing_refs_event', 'timeline_event', { id: 'event_missing_edges', title: 'Broken event', branchId: 'branch_missing', orderIndex: 0, locationIds: ['world_missing'], participantCharacterIds: ['char_missing'], linkedSceneIds: ['scene_missing'], linkedWorldItemIds: ['world_missing'], tags: [] }),
    ]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.timelineBranches).toEqual([]);
    expect(state.timelineEvents).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('references missing branch: branch_missing');
  });

  test('does not treat a same-package update as the creator of a missing referenced entity', async ({ page }) => {
    const packageId = 'pkg_update_is_not_creator';
    const character = makePackageProposal(packageId, 'update_ref_character', 'character', {
      id: 'char_update_ref', name: 'Must roll back', aliases: [], tagIds: [],
      organizationIds: [], linkedSceneIds: [], linkedEventIds: ['event_not_canonical'],
      linkedWorldItemIds: [], statusFlags: {},
    });
    const eventUpdate = makePackageProposal(packageId, 'update_ref_event', 'timeline_event', {
      id: 'event_not_canonical', title: 'Missing canonical event', branchId: 'branch_missing',
      orderIndex: 0, locationIds: [], participantCharacterIds: [], linkedSceneIds: [],
      linkedWorldItemIds: [], tags: [],
    });
    eventUpdate.proposedOperations[0].op = 'update';
    await injectImportPackage(page, [character, eventUpdate]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.timelineEvents).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('event_not_canonical');
  });

  test('validates imported branch topology anchors as package references', async ({ page }) => {
    const packageId = 'pkg_branch_topology_missing_anchor';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'topology_root', 'timeline_branch', {
        id: 'branch_topology_root', name: 'Root', mode: 'root', sortOrder: 0,
      }),
      makePackageProposal(packageId, 'topology_fork', 'timeline_branch', {
        id: 'branch_topology_fork', name: 'Fork', mode: 'forked', sortOrder: 1,
        parentBranchId: 'branch_topology_root', forkEventId: 'event_missing_anchor',
      }),
    ]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.timelineBranches).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('event_missing_anchor');
  });

  test('blocks import creates with missing required branch, chapter, or container IDs instead of defaulting them', async ({ page }) => {
    const cases = [
      { entityType: 'timeline_event', id: 'event_no_branch', fields: { id: 'event_no_branch', title: 'No branch', orderIndex: 0, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [] }, reason: 'missing required branchId' },
      { entityType: 'scene', id: 'scene_no_chapter', fields: { id: 'scene_no_chapter', title: 'No chapter', content: '', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' }, reason: 'missing required chapterId' },
      { entityType: 'world_item', id: 'world_no_container', fields: { id: 'world_no_container', name: 'No container', type: 'note', description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [] }, reason: 'missing required containerId' },
      { entityType: 'relationship', id: 'relationship_no_target', fields: { id: 'relationship_no_target', sourceId: '', targetId: '', type: 'related' }, reason: 'missing required sourceId or targetId' },
    ];

    for (const entry of cases) {
      const packageId = `pkg_required_${entry.id}`;
      await injectImportPackage(page, [makePackageProposal(packageId, entry.id, entry.entityType, entry.fields)]);
      await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
      const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
      expect(state.proposals[0].lastBlockReason).toContain(entry.reason);
      expect(state.timelineEvents).toEqual([]);
      expect(state.scenes).toEqual([]);
      expect(state.worldItems).toEqual([]);
    }
  });

  test('reconstructs Python code-point SourceSpan offsets through non-BMP characters', async ({ page }) => {
    const packageId = 'pkg_projection_code_points';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_code_points';
    const rawSource = 'A😀B projection body.';
    const content = 'B projection body.';
    const span = sourceSpan(sourceHash, rawSource, 2, Array.from(rawSource).length, `hash:${content}`);
    const projection = {
      contract_version: 'w1-staged-manuscript-v1',
      import_run_id: packageId,
      acceptance_required: true,
      chapters: [{ chapter_id: 'chap_projection', scene_id: 'scene_projection', source_span: span }],
      nodes: [
        { id: 'mn_chap_projection', title: 'Projection Chapter', type: 'chapter_outline', parentId: null, orderIndex: 0, linkedChapterId: 'chap_projection', linkedSceneId: null, depth: 0, collapsed: false, wordCount: 3 },
        { id: 'mn_scene_projection', title: 'Chapter Text', type: 'scene_outline', parentId: 'mn_chap_projection', orderIndex: 0, linkedChapterId: 'chap_projection', linkedSceneId: 'scene_projection', depth: 1, collapsed: false, wordCount: 3 },
      ],
      scene_documents: [{ node_id: 'mn_scene_projection', scene_id: 'scene_projection', content, source_span: span }],
    };
    await installProjectionFilesystem(page, artifactPath, projection, { import_run_id: packageId, source_hash: sourceHash }, undefined, rawSource);
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const accepted = await page.evaluate(() => (window as any).__narrativeStore.getState().scenes.find((scene: any) => scene.id === 'scene_projection')?.content);
    expect(accepted).toBe(content);
  });

  test('blocks undeclared and stale EntityMergeDecision fields without mutating canonical characters', async ({ page }) => {
    const packageId = 'pkg_merge_contract_enforcement';
    const makeUpdate = (id: string, fields: Record<string, unknown>) => {
      const proposal = makePackageProposal(packageId, id, 'character', fields, 'Merge character');
      proposal.proposedOperations[0].op = 'update';
      return proposal;
    };
    const decision = {
      contract: 'EntityMergeDecision/v1', import_id: 'import_hero', existing_id: 'char_canonical', conflicts: [],
      fields: { aliases: { action: 'union', value: ['Canonical Hero', 'Imported Hero'], source: 'existing+import' } },
    };
    const evidence = { importCharacterId: 'import_hero', entityMergeDecision: decision, semanticConflicts: [] };
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'merge_branch', 'timeline_branch', { id: 'branch_merge', name: 'Must roll back', sortOrder: 0, mode: 'root', collapsed: false }),
      makeUpdate('merge_forged', { id: 'char_canonical', aliases: decision.fields.aliases.value, summary: 'Forged update', mergeEvidence: evidence }),
    ]);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, characters: [{ id: 'char_canonical', name: 'Canonical Hero', summary: 'Canonical summary.', background: 'Current history.', aliases: ['Canonical Hero'], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }] }));
    });
    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    let state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.timelineBranches).toEqual([]);
    expect(state.characters[0].summary).toBe('Canonical summary.');
    expect(state.proposals[0].lastBlockReason).toContain('undeclared field summary');

    const staleDecision = { ...decision, fields: { background: { action: 'preserve_existing', value: 'Old history.', source: 'existing+import' } } };
    const staleEvidence = { importCharacterId: 'import_hero', entityMergeDecision: staleDecision, semanticConflicts: [] };
    await page.evaluate(({ staleDecision, staleEvidence }) => {
      const store = (window as any).__narrativeStore;
      const proposal = store.getState().proposals.find((item: any) => item.id === 'merge_forged');
      proposal.proposedOperations[0].fields = { id: 'char_canonical', background: staleDecision.fields.background.value, mergeEvidence: staleEvidence, importRunId: proposal.importRunId };
      store.setState((state: any) => ({ ...state, proposals: [proposal] }));
    }, { staleDecision, staleEvidence });
    await page.getByTestId(`retry-blocked-package-${packageTestId(packageId)}`).click();
    state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters[0].background).toBe('Current history.');
    expect(state.proposals[0].lastBlockReason).toContain('stale for preserved field background');
  });

  test('blocks tampered staged scene content when it no longer reconstructs from SourceSpan', async ({ page }) => {
    const packageId = 'pkg_projection_content_tamper';
    const artifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_tamper';
    const projection = makeProjection(packageId, sourceHash);
    projection.scene_documents[0].content = 'Tampered artifact body.';
    await installProjectionFilesystem(page, artifactPath, projection, { import_run_id: packageId, source_hash: sourceHash }, undefined, 'Projection-owned manuscript content.');
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, artifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.scenes).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('invalid or unapproved scene document');
  });

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

  test('does not rewrite package-external dangling scene and event references', async ({ page }) => {
    const packageId = 'pkg_external_dangling_refs';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_external_chapter', 'chapter', {
        id: 'chap_pkg_valid', title: 'Valid package chapter', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
      }),
      makePackageProposal(packageId, 'pkg_external_branch', 'timeline_branch', {
        id: 'branch_pkg_valid', name: 'Valid package branch', sortOrder: 0, mode: 'root', collapsed: false,
      }),
    ]);
    const externalScene = {
      id: 'scene_external_dangling', chapterId: 'chap_missing_external', title: 'External scene', summary: 'Keep every field.', content: 'Canonical text.', orderIndex: 7,
      povCharacterId: null, linkedCharacterIds: ['char_missing_external'], linkedEventIds: ['event_missing_external'], linkedWorldItemIds: ['world_missing_external'], status: 'draft',
    };
    const externalEvent = {
      id: 'event_external_dangling', title: 'External event', summary: 'Keep every field.', branchId: 'branch_missing_external', orderIndex: 9,
      locationIds: ['world_missing_external'], participantCharacterIds: ['char_missing_external'], linkedSceneIds: ['scene_missing_external'], linkedWorldItemIds: ['world_missing_external'], tags: ['legacy'],
    };
    await page.evaluate(({ externalScene, externalEvent }) => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, scenes: [externalScene], timelineEvents: [externalEvent] }));
    }, { externalScene, externalEvent });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');

    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      return {
        externalScene: s.scenes.find((scene: any) => scene.id === 'scene_external_dangling'),
        externalEvent: s.timelineEvents.find((event: any) => event.id === 'event_external_dangling'),
        chapters: s.chapters.map((chapter: any) => chapter.id),
        branches: s.timelineBranches.map((branch: any) => branch.id),
        history: s.proposalHistory.map((proposal: any) => proposal.id),
      };
    });

    expect(state.externalScene).toEqual(externalScene);
    expect(state.externalEvent).toEqual(externalEvent);
    expect(state.chapters).toEqual(['chap_pkg_valid']);
    expect(state.branches).toEqual(['branch_pkg_valid']);
    expect(state.history).toEqual(expect.arrayContaining(['pkg_external_chapter', 'pkg_external_branch']));
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

    await expect(page.getByTestId(`retry-blocked-package-${packageTestId(packageId)}`)).toBeVisible();
  });
});
