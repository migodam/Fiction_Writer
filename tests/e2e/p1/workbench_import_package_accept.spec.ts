import { expect, test } from '@playwright/test';
import { createHash } from 'node:crypto';

const now = () => '2026-05-31T00:00:00.000Z';
const sha256 = (value: string) => createHash('sha256').update(value, 'utf8').digest('hex');

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

const makeSemanticCoverage = (packageId: string, verdict: 'pass' | 'warning' | 'blocked', attemptId = 'attempt_01') => {
  const relativePath = `system/imports/${packageId}/attempts/${attemptId}/semantic_coverage_report.json`;
  const inputHash = sha256(`semantic-input:${packageId}:${attemptId}:${verdict}`);
  const report = {
    contract_version: 'w1-semantic-coverage-report/v1',
    import_run_id: packageId,
    lineage_id: packageId,
    attempt_id: attemptId,
    input_hash: inputHash,
    verdict,
    artifact_paths: { report: relativePath },
  };
  const reportText = JSON.stringify(report);
  const ref = {
    relativePath,
    sha256: sha256(reportText),
    verdict,
    input_hash: inputHash,
    attempt_id: attemptId,
  };
  return {
    reportText,
    ref,
    policy: {
      verdict,
      automatic_acceptance: verdict === 'pass',
      requires_human_review: verdict === 'warning',
      report_path: relativePath,
      input_hash: inputHash,
      ref,
    },
  };
};

const attachSemanticCoverage = (
  proposals: ReturnType<typeof makePackageProposal>[],
  coverage: ReturnType<typeof makeSemanticCoverage>,
) => proposals.map((proposal) => {
  (proposal as any).semanticCoverageRef = coverage.ref;
  (proposal as any).semanticCoverage = coverage.policy;
  proposal.proposedOperations[0].semanticCoverageRef = coverage.ref;
  return proposal;
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

const makeArtifactRefProjectionPackage = (packageId: string, artifactPath: string, artifactSha256: string, attemptId = 'attempt_01', chapterId = 'chap_projection', sceneId = 'scene_projection') => {
  const relativePath = `system/imports/${packageId}/attempts/${attemptId}/staged_manuscript_projection.json`;
  const artifactRef = {
    relativePath,
    sha256: artifactSha256,
    contractVersion: 'w1-staged-manuscript-v2',
    lineageId: packageId,
    attemptId,
  };
  return makeStagedProjectionPackage(packageId, artifactPath, chapterId, sceneId).map((proposal) => {
    proposal.proposedOperations[0].fields!.stagedManuscriptProjection = {
      artifactRef,
      contract_version: 'w1-staged-manuscript-v2',
      chapter_id: chapterId,
      scene_id: sceneId,
    };
    return proposal;
  });
};

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
  artifactSourcePathOverride?: string,
  extraFiles: Record<string, string> = {},
  realpathOverrides: Record<string, string> = {},
) {
  const manifestPath = artifactPath.replace(/staged_manuscript_projection\.json$/, 'manifest.json');
  const runDirectory = artifactPath.replace(/\/staged_manuscript_projection\.json$/, '');
  const sourcePath = sourcePathOverride ?? `${runDirectory}/raw_source.txt`;
  const sourceText = sourceTextOverride ?? String(((projection.scene_documents as Array<Record<string, unknown>> | undefined)?.[0]?.content) || '');
  const fixtureHash = String(((projection.chapters as Array<Record<string, unknown>> | undefined)?.[0]?.source_span as Record<string, unknown> | undefined)?.raw_source_hash || '');
  const shouldNormalizeHashes = manifest.source_hash === fixtureHash;
  const sourceHash = shouldNormalizeHashes ? sha256(sourceText) : fixtureHash;
  const projectionPayload = JSON.parse(JSON.stringify({ ...projection, source_file_path: artifactSourcePathOverride ?? sourcePath })) as Record<string, any>;
  const manifestPayload = { ...manifest };
  if (shouldNormalizeHashes) {
    manifestPayload.source_hash = sourceHash;
    const normalizeSpan = (span: Record<string, unknown> | undefined) => {
      if (!span) return;
      const start = Number(span.absolute_start ?? 0);
      const end = Number(span.absolute_end ?? Array.from(sourceText).length);
      const content = Array.from(sourceText).slice(start, end).join('');
      span.raw_source_hash = sourceHash;
      span.substring_hash = sha256(content);
    };
    for (const chapter of projectionPayload.chapters ?? []) normalizeSpan(chapter.source_span);
    for (const document of projectionPayload.scene_documents ?? []) normalizeSpan(document.source_span);
  }
  await page.addInitScript(
    ({ artifactPath, manifestPath, runDirectory, projectionPayload, manifestPayload, escapedArtifactPath, sourcePath, escapedSourcePath, sourceText, sourceHash, extraFiles, realpathOverrides }) => {
      const files = new Map<string, string>([
        [artifactPath, JSON.stringify(projectionPayload)],
        [manifestPath, JSON.stringify(manifestPayload)],
        [sourcePath, sourceText],
        ...Object.entries(extraFiles),
      ]);
      const directories = new Set([runDirectory]);
      const writes: string[] = [];
      const directChildren = (directory: string) => {
        const prefix = `${directory}/`;
        return Array.from(new Set([...directories, ...files.keys()]
          .filter((path) => path.startsWith(prefix))
          .map((path) => path.slice(prefix.length).split('/')[0])
          .filter(Boolean)));
      };
      (window as any).__projectionFs = { files, directories, writes };
      delete (window as any).require;
      (window as any).narrativeIDE = {
        projectFileExists: ({ path }: any) => files.has(path) || directories.has(path),
        projectFileRead: ({ path }: any) => files.get(path) ?? '',
        projectFileWrite: ({ path, data }: any) => { files.set(path, String(data)); writes.push(path); },
        projectFileMkdir: ({ path }: any) => { directories.add(path); },
        projectFileReaddir: ({ path }: any) => directChildren(path),
        projectFileUnlink: ({ path }: any) => { files.delete(path); },
        projectFileRealpath: ({ path }: any) => realpathOverrides[path]
          ?? (path === artifactPath && escapedArtifactPath
          ? escapedArtifactPath
          : path === sourcePath && escapedSourcePath ? escapedSourcePath : path),
        projectFileCopy: ({ path }: any) => { throw new Error(`Unexpected copy: ${path}`); },
        projectFileRename: ({ path, destination }: any) => { files.set(destination, files.get(path) ?? ''); files.delete(path); writes.push(destination); },
      };
    },
    { artifactPath, manifestPath, runDirectory, projectionPayload, manifestPayload, escapedArtifactPath, sourcePath, escapedSourcePath, sourceText, sourceHash, extraFiles, realpathOverrides },
  );
}

async function installSemanticCoverageFilesystem(
  page: import('@playwright/test').Page,
  coverage: ReturnType<typeof makeSemanticCoverage>,
  realpathOverrides: Record<string, string> = {},
) {
  const reportPath = `/project/${coverage.ref.relativePath}`;
  await installProjectionFilesystem(
    page,
    '/project/system/imports/fixture/staged_manuscript_projection.json',
    makeProjection('fixture', 'fixture-source'),
    { import_run_id: 'fixture', source_hash: 'fixture-source' },
    undefined,
    undefined,
    undefined,
    undefined,
    undefined,
    { [reportPath]: coverage.reportText },
    realpathOverrides,
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
      const starterChapter = { id: 'chap_1784040375337', title: 'Chapter 1', summary: '', goal: '', notes: '', sceneIds: ['scene_1784040375344'], orderIndex: 0, status: 'draft' };
      const starterScene = { id: 'scene_1784040375344', chapterId: starterChapter.id, title: 'Scene 1', summary: '', content: '', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' };
      const fs = (window as any).__projectionFs;
      fs.files.set('/project/writing/chapters/chap_1784040375337.json', JSON.stringify(starterChapter));
      fs.files.set('/project/writing/scenes/scene_1784040375344.md', '');
      fs.files.set('/project/writing/scenes/scene_1784040375344.meta.json', JSON.stringify({ ...starterScene, content: undefined }));
      fs.files.set('/project/unrelated/keep.txt', 'keep');
      fs.directories.add('/project/writing/chapters');
      fs.directories.add('/project/writing/scenes');
      store.setState((state: any) => ({
        ...state,
        projectRoot: '/project',
        chapters: [starterChapter],
        scenes: [starterScene],
        currentProject: {
          ...state.currentProject,
          chapters: [starterChapter],
          scenes: [starterScene],
          metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs', template: 'blank' },
        },
      }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => {
      const s = (window as any).__narrativeStore.getState();
      const fs = (window as any).__projectionFs;
      return {
        sceneContent: s.scenes.find((scene: any) => scene.id === 'scene_projection')?.content,
        chapterIds: s.chapters.map((chapter: any) => chapter.id),
        sceneIds: s.scenes.map((scene: any) => scene.id),
        manuscriptNodes: s.manuscriptNodes.map((node: any) => node.id),
        persistedStarterFiles: [
          fs.files.has('/project/writing/chapters/chap_1784040375337.json'),
          fs.files.has('/project/writing/scenes/scene_1784040375344.md'),
          fs.files.has('/project/writing/scenes/scene_1784040375344.meta.json'),
        ],
        unrelated: fs.files.get('/project/unrelated/keep.txt'),
      };
    });
    expect(state.sceneContent).toBe('Projection-owned manuscript content.');
    expect(state.chapterIds).toEqual(['chap_projection']);
    expect(state.sceneIds).toEqual(['scene_projection']);
    expect(state.manuscriptNodes).toEqual(expect.arrayContaining(['mn_chap_projection', 'mn_scene_projection']));
    expect(state.persistedStarterFiles).toEqual([false, false, false]);
    expect(state.unrelated).toBe('keep');
  });

  test('accepts a relocated project artifact reference without trusting its former /tmp path', async ({ page }) => {
    const packageId = 'pkg_relocated_projection';
    const attemptId = 'attempt_relocated_02';
    const artifactPath = `/project/system/imports/${packageId}/attempts/${attemptId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_relocated';
    const projection = makeProjection(packageId, sourceHash);
    await installProjectionFilesystem(page, artifactPath, projection, { import_run_id: packageId, source_hash: sourceHash });
    await page.goto('http://localhost:3000');
    const artifactHash = await page.evaluate((path) => (window as any).__projectionFs.files.get(path), artifactPath);
    await injectImportPackage(page, makeArtifactRefProjectionPackage(packageId, artifactPath, sha256(artifactHash), attemptId));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.scenes.find((scene: any) => scene.id === 'scene_projection')?.content).toBe('Projection-owned manuscript content.');
    expect(state.proposals).toEqual([]);
  });

  test('rejects an ArtifactRef traversal before mutating the package', async ({ page }) => {
    const packageId = 'pkg_artifact_ref_traversal';
    const attemptId = 'attempt_traversal_03';
    const artifactPath = `/project/system/imports/${packageId}/attempts/${attemptId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_traversal';
    await installProjectionFilesystem(page, artifactPath, makeProjection(packageId, sourceHash), { import_run_id: packageId, source_hash: sourceHash });
    const projection = makeProjection(packageId, sourceHash);
    const proposals = makeArtifactRefProjectionPackage(packageId, artifactPath, `hash:${JSON.stringify({ ...projection, source_file_path: `/project/system/imports/${packageId}/attempts/${attemptId}/raw_source.txt` })}`, attemptId);
    (proposals[0].proposedOperations[0].fields!.stagedManuscriptProjection as any).artifactRef.relativePath = '../outside.json';
    await injectImportPackage(page, proposals);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.chapters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('ArtifactRef');
  });

  test('repairs a blocked stale legacy package without accepting proposals, then accepts explicitly', async ({ page }) => {
    const packageId = 'pkg_legacy_repair';
    const currentArtifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const oldArtifactPath = `/tmp/old-project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const oldSourcePath = `/tmp/old-project/system/imports/${packageId}/raw_source.txt`;
    const sourceHash = 'source_hash_legacy_repair';
    const projection = makeProjection(packageId, sourceHash);
    await installProjectionFilesystem(page, currentArtifactPath, projection, { import_run_id: packageId, source_hash: sourceHash }, undefined, undefined, undefined, undefined, oldSourcePath);
    const legacyProposals = makeStagedProjectionPackage(packageId, oldArtifactPath) as any[];
    legacyProposals.forEach((proposal) => {
      proposal.operations = proposal.proposedOperations;
      delete proposal.proposedOperations;
    });
    await injectImportPackage(page, legacyProposals);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const blocked = await page.evaluate(() => {
      const state = (window as any).__narrativeStore.getState();
      return {
        chapters: state.chapters,
        scenes: state.scenes,
        proposals: state.proposals.map((proposal: any) => ({ id: proposal.id, reason: proposal.lastBlockReason })),
        history: state.proposalHistory,
      };
    });
    expect(blocked.chapters).toEqual([]);
    expect(blocked.scenes).toEqual([]);
    expect(blocked.proposals).toHaveLength(2);
    expect(blocked.proposals.every((proposal: any) => proposal.reason)).toBe(true);
    expect(blocked.history).toEqual([]);

    await page.getByTestId(`repair-blocked-package-${packageTestId(packageId)}`).click();
    const repaired = await page.evaluate(({ packageId }) => {
      const store = (window as any).__narrativeStore;
      const state = store.getState();
      store.getState().repairImportPackage(state.proposals.map((proposal: any) => proposal.id));
      const repeated = store.getState();
      return {
        chapters: repeated.chapters,
        scenes: repeated.scenes,
        proposals: repeated.proposals.map((proposal: any) => ({ id: proposal.id, reason: proposal.lastBlockReason })),
        history: repeated.proposalHistory,
        transactions: [...(window as any).__projectionFs.files.keys()].filter((path: string) => path.includes(`/system/transactions/repair-package-${packageId}`)),
      };
    }, { packageId });
    expect(repaired.chapters).toEqual([]);
    expect(repaired.scenes).toEqual([]);
    expect(repaired.proposals).toHaveLength(2);
    expect(repaired.proposals.every((proposal: any) => !proposal.reason)).toBe(true);
    expect(repaired.history).toEqual([]);
    expect(repaired.transactions.length).toBeGreaterThan(0);
    const repairedDescriptors = await page.evaluate(() => {
      const proposals = (window as any).__narrativeStore.getState().proposals;
      return proposals.flatMap((proposal: any) => [
        ...(proposal.operations || []),
        ...(proposal.proposedOperations || []),
      ]).map((operation: any) => operation.fields?.stagedManuscriptProjection).filter(Boolean);
    });
    expect(repairedDescriptors).toHaveLength(2);
    expect(repairedDescriptors.every((descriptor: any) => !Object.prototype.hasOwnProperty.call(descriptor, 'artifact_path'))).toBe(true);
    expect(repairedDescriptors.every((descriptor: any) => descriptor.artifactRef?.contractVersion === 'w1-staged-manuscript-v2')).toBe(true);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const result = await page.evaluate(({ currentArtifactPath, packageId }) => {
      const state = (window as any).__narrativeStore.getState();
      const fs = (window as any).__projectionFs;
      const artifact = JSON.parse(fs.files.get(currentArtifactPath));
      return {
        content: state.scenes.find((scene: any) => scene.id === 'scene_projection')?.content,
        sourceRef: artifact.source_ref,
        hasLegacyPath: Object.prototype.hasOwnProperty.call(artifact, 'source_file_path'),
        transactions: [...fs.files.keys()].filter((path: string) => path.includes(`/system/transactions/repair-package-${packageId}`)),
      };
    }, { currentArtifactPath, packageId });
    expect(result.content).toBe('Projection-owned manuscript content.');
    expect(result.hasLegacyPath).toBe(false);
    expect(result.sourceRef).toEqual(expect.objectContaining({ relativePath: `system/imports/${packageId}/raw_source.txt`, attemptId: 'legacy' }));
    expect(result.transactions.length).toBeGreaterThan(0);
  });

  test('repairs a legacy projection stored in an attempt directory and preserves the attempt identity', async ({ page }) => {
    const packageId = 'pkg_attempt_legacy_repair';
    const attemptId = 'legacy_attempt_02';
    const artifactPath = `/project/system/imports/${packageId}/attempts/${attemptId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_attempt_legacy_repair';
    await installProjectionFilesystem(
      page,
      artifactPath,
      makeProjection(packageId, sourceHash),
      { import_run_id: packageId, source_hash: sourceHash, attempt_id: attemptId },
    );
    const proposals = makeStagedProjectionPackage(packageId, artifactPath).map((proposal) => ({
      ...proposal,
      lastBlockReason: 'Legacy package requires repair.',
    }));
    await injectImportPackage(page, proposals);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({
        ...state,
        projectRoot: '/project',
        currentProject: {
          ...state.currentProject,
          metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' },
        },
      }));
    });

    await page.getByTestId(`repair-blocked-package-${packageTestId(packageId)}`).click();
    const repaired = await page.evaluate(() => {
      const state = (window as any).__narrativeStore.getState();
      const descriptors = state.proposals.flatMap((proposal: any) => proposal.proposedOperations)
        .map((operation: any) => operation.fields?.stagedManuscriptProjection);
      return { proposals: state.proposals, descriptors };
    });
    expect(repaired.proposals.every((proposal: any) => !proposal.lastBlockReason)).toBe(true);
    expect(repaired.descriptors.every((descriptor: any) =>
      descriptor.artifactRef?.attemptId === attemptId
      && descriptor.artifactRef?.relativePath === `system/imports/${packageId}/attempts/${attemptId}/staged_manuscript_projection.json`
    )).toBe(true);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const accepted = await page.evaluate(() => {
      const state = (window as any).__narrativeStore.getState();
      const artifact = JSON.parse((window as any).__projectionFs.files.get(
        '/project/system/imports/pkg_attempt_legacy_repair/attempts/legacy_attempt_02/staged_manuscript_projection.json',
      ));
      return { content: state.scenes[0]?.content, sourceRef: artifact.source_ref, pending: state.proposals.length };
    });
    expect(accepted.content).toBe('Projection-owned manuscript content.');
    expect(accepted.pending).toBe(0);
    expect(accepted.sourceRef).toEqual(expect.objectContaining({
      attemptId,
      relativePath: `system/imports/${packageId}/attempts/${attemptId}/raw_source.txt`,
    }));
  });

  test('failed legacy repair writes no receipt and leaves the projection artifact unchanged', async ({ page }) => {
    const packageId = 'pkg_legacy_repair_failure';
    const currentArtifactPath = `/project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const oldArtifactPath = `/tmp/old-project/system/imports/${packageId}/staged_manuscript_projection.json`;
    const sourceHash = 'source_hash_legacy_failure';
    const projection = makeProjection(packageId, sourceHash);
    await installProjectionFilesystem(page, currentArtifactPath, projection, { import_run_id: packageId, source_hash: 'wrong_manifest_hash' }, undefined, undefined, undefined, undefined, '/tmp/old/raw_source.txt');
    await injectImportPackage(page, makeStagedProjectionPackage(packageId, oldArtifactPath));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });
    const before = await page.evaluate((path) => (window as any).__projectionFs.files.get(path), currentArtifactPath);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const result = await page.evaluate((path) => {
      const fs = (window as any).__projectionFs;
      return { after: fs.files.get(path), writes: fs.writes, files: [...fs.files.keys()] };
    }, currentArtifactPath);
    expect(result.after).toBe(before);
    expect(result.writes).toEqual([]);
    expect(result.files.some((path: string) => path.endsWith('.receipt.json'))).toBe(false);
  });

  test('accepts an 89-proposal package once and leaves a repeated accept inert', async ({ page }) => {
    const packageId = 'pkg_eighty_nine';
    const proposals = Array.from({ length: 89 }, (_, index) => makePackageProposal(packageId, `proposal_${index}`, 'character', {
      id: `char_${index}`, name: `Imported ${index}`, summary: '', background: '', aliases: [], birthdayText: '',
      tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
    }));
    await injectImportPackage(page, proposals);
    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    await page.evaluate((ids) => (window as any).__narrativeStore.getState().resolveProposals(ids, 'accepted'), proposals.map((proposal) => proposal.id));
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toHaveLength(89);
    expect(state.proposalHistory).toHaveLength(89);
    expect(state.proposals).toEqual([]);
  });

  test('accepts a pass semantic report emitted with policy only on the proposal', async ({ page }) => {
    const packageId = 'pkg_semantic_pass';
    const coverage = makeSemanticCoverage(packageId, 'pass');
    await installSemanticCoverageFilesystem(page, coverage);
    await injectImportPackage(page, attachSemanticCoverage([
      makePackageProposal(packageId, 'semantic_pass_character', 'character', {
        id: 'char_semantic_pass', name: 'Verified Hero', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], coverage));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([expect.objectContaining({ id: 'char_semantic_pass' })]);
    expect(state.proposals).toEqual([]);
  });

  test('fails closed when new W1 semantic policy lacks a report reference', async ({ page }) => {
    const packageId = 'pkg_semantic_missing_ref';
    const coverage = makeSemanticCoverage(packageId, 'pass');
    const proposal = makePackageProposal(packageId, 'semantic_missing_ref_character', 'character', {
      id: 'char_semantic_missing_ref', name: 'Missing Receipt', summary: '', background: '', aliases: [], birthdayText: '',
      tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
    });
    (proposal as any).semanticCoverage = coverage.policy;
    await injectImportPackage(page, [proposal]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('missing its immutable report reference');
  });

  test('fails closed when proposal and operation semantic references disagree', async ({ page }) => {
    const packageId = 'pkg_semantic_ref_mismatch';
    const coverage = makeSemanticCoverage(packageId, 'pass');
    await installSemanticCoverageFilesystem(page, coverage);
    const proposals = attachSemanticCoverage([
      makePackageProposal(packageId, 'semantic_ref_mismatch_a', 'character', {
        id: 'char_semantic_ref_mismatch_a', name: 'Reference A', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
      makePackageProposal(packageId, 'semantic_ref_mismatch_b', 'character', {
        id: 'char_semantic_ref_mismatch_b', name: 'Reference B', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], coverage);
    proposals[1].proposedOperations[0].semanticCoverageRef = { ...coverage.ref, sha256: sha256('different receipt') };
    await injectImportPackage(page, proposals);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('references disagree');
  });

  test('fails closed when a semantic report hash, attempt, or relative path is tampered', async ({ page }) => {
    const packageId = 'pkg_semantic_tamper';
    const coverage = makeSemanticCoverage(packageId, 'pass');
    coverage.ref.sha256 = sha256('different report');
    await installSemanticCoverageFilesystem(page, coverage);
    const proposals = attachSemanticCoverage([
      makePackageProposal(packageId, 'semantic_tamper_character', 'character', {
        id: 'char_semantic_tamper', name: 'Must Stay Pending', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], coverage);
    await injectImportPackage(page, proposals);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('report hash');

    const traversalPackageId = 'pkg_semantic_traversal';
    const traversalCoverage = makeSemanticCoverage(traversalPackageId, 'pass');
    traversalCoverage.ref.relativePath = `system/imports/${traversalPackageId}/attempts/attempt_01/../semantic_coverage_report.json`;
    traversalCoverage.policy.report_path = traversalCoverage.ref.relativePath;
    await injectImportPackage(page, attachSemanticCoverage([
      makePackageProposal(traversalPackageId, 'semantic_traversal_character', 'character', {
        id: 'char_semantic_traversal', name: 'Path Escape', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], traversalCoverage));
    await page.getByTestId(`accept-import-package-${packageTestId(traversalPackageId)}`).click();
    const traversalState = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(traversalState.characters).toEqual([]);
    expect(traversalState.proposals[0].lastBlockReason).toContain('inconsistent or unsafe');
  });

  test('rejects a semantic report from another attempt', async ({ page }) => {
    const packageId = 'pkg_semantic_attempt';
    const coverage = makeSemanticCoverage(packageId, 'pass', 'attempt_02');
    const mismatchedReport = JSON.parse(coverage.reportText);
    mismatchedReport.attempt_id = 'attempt_01';
    coverage.reportText = JSON.stringify(mismatchedReport);
    coverage.ref.sha256 = sha256(coverage.reportText);
    await installSemanticCoverageFilesystem(page, coverage);
    await injectImportPackage(page, attachSemanticCoverage([
      makePackageProposal(packageId, 'semantic_attempt_character', 'character', {
        id: 'char_semantic_attempt', name: 'Wrong Attempt', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], coverage));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('does not match this package, attempt');
  });

  test('rejects a semantic report that resolves through a symlink', async ({ page }) => {
    const packageId = 'pkg_semantic_symlink';
    const coverage = makeSemanticCoverage(packageId, 'pass');
    await installSemanticCoverageFilesystem(page, coverage, { [`/project/${coverage.ref.relativePath}`]: '/outside/semantic_coverage_report.json' });
    await injectImportPackage(page, attachSemanticCoverage([
      makePackageProposal(packageId, 'semantic_symlink_character', 'character', {
        id: 'char_semantic_symlink', name: 'Escaped Report', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], coverage));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.proposals[0].lastBlockReason).toContain('resolves through a symlink');
  });

  test('allows a warning through an explicit single PackageCard acceptance', async ({ page }) => {
    const packageId = 'pkg_semantic_warning_manual';
    const coverage = makeSemanticCoverage(packageId, 'warning');
    await installSemanticCoverageFilesystem(page, coverage);
    await injectImportPackage(page, attachSemanticCoverage([
      makePackageProposal(packageId, 'semantic_warning_manual_character', 'character', {
        id: 'char_semantic_warning_manual', name: 'Manual Only', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], coverage));
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([expect.objectContaining({ id: 'char_semantic_warning_manual' })]);
    expect(state.proposals).toEqual([]);
  });

  test('rejects warning semantic coverage through a bulk acceptance path', async ({ page }) => {
    const firstPackageId = 'pkg_semantic_warning_a';
    const secondPackageId = 'pkg_semantic_warning_b';
    const firstCoverage = makeSemanticCoverage(firstPackageId, 'warning');
    const secondCoverage = makeSemanticCoverage(secondPackageId, 'warning');
    await installProjectionFilesystem(
      page,
      '/project/system/imports/fixture/staged_manuscript_projection.json',
      makeProjection('fixture', 'fixture-source'),
      { import_run_id: 'fixture', source_hash: 'fixture-source' },
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      {
        [`/project/${firstCoverage.ref.relativePath}`]: firstCoverage.reportText,
        [`/project/${secondCoverage.ref.relativePath}`]: secondCoverage.reportText,
      },
    );
    const firstProposal = attachSemanticCoverage([
      makePackageProposal(firstPackageId, 'semantic_warning_a_character', 'character', {
        id: 'char_semantic_warning_a', name: 'Manual A', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], firstCoverage);
    const secondProposal = attachSemanticCoverage([
      makePackageProposal(secondPackageId, 'semantic_warning_b_character', 'character', {
        id: 'char_semantic_warning_b', name: 'Manual B', summary: '', background: '', aliases: [], birthdayText: '',
        tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
      }),
    ], secondCoverage);
    await injectImportPackage(page, [...firstProposal, ...secondProposal]);
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.setState((state: any) => ({ ...state, projectRoot: '/project', currentProject: { ...state.currentProject, metadata: { ...state.currentProject.metadata, rootPath: '/project', storageMode: 'nodefs' } } }));
    });

    await page.evaluate(async () => {
      const store = (window as any).__narrativeStore;
      await store.getState().resolveProposals(['semantic_warning_a_character', 'semantic_warning_b_character'], 'accepted', 'bulk');
    });
    let state = await page.evaluate(() => (window as any).__narrativeStore.getState());
    expect(state.characters).toEqual([]);
    expect(state.proposals.find((proposal: any) => proposal.id === 'semantic_warning_a_character').lastBlockReason).toContain('bulk acceptance is blocked');
    expect(state.proposals.map((proposal: any) => proposal.id)).toEqual([
      'semantic_warning_a_character',
      'semantic_warning_b_character',
    ]);
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
    await expect(page.getByTestId(`repair-blocked-package-${packageTestId(packageId)}`)).toBeVisible();
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

  test('blocks direct single-proposal acceptance for a package-scoped proposal', async ({ page }) => {
    const packageId = 'pkg_direct_accept_guard';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'pkg_direct_accept_chapter', 'chapter', {
        id: 'chap_direct_accept',
        title: 'Package-only Chapter',
        summary: '',
        goal: '',
        notes: '',
        sceneIds: [],
        orderIndex: 0,
        status: 'draft',
      }),
    ]);

    const result = await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      store.getState().resolveProposal('pkg_direct_accept_chapter', 'accepted');
      const state = store.getState();
      return {
        chapters: state.chapters,
        history: state.proposalHistory,
        proposal: state.proposals[0],
      };
    });

    expect(result.chapters).toEqual([]);
    expect(result.history).toEqual([]);
    expect(result.proposal.status).toBe('pending');
    expect(result.proposal.lastBlockReason).toContain('complete package transaction');
  });

  test('blocks a partial package selection instead of falling back to a non-atomic batch', async ({ page }) => {
    const packageId = 'pkg_partial_selection_guard';
    await injectImportPackage(page, [
      makePackageProposal(packageId, 'partial_chapter_a', 'chapter', {
        id: 'chap_partial_a', title: 'Partial A', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft',
      }),
      makePackageProposal(packageId, 'partial_chapter_b', 'chapter', {
        id: 'chap_partial_b', title: 'Partial B', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 1, status: 'draft',
      }),
    ]);

    const result = await page.evaluate(async () => {
      const store = (window as any).__narrativeStore;
      await store.getState().resolveProposals(['partial_chapter_a'], 'accepted');
      const state = store.getState();
      return { chapters: state.chapters, proposals: state.proposals, history: state.proposalHistory };
    });

    expect(result.chapters).toEqual([]);
    expect(result.history).toEqual([]);
    expect(result.proposals).toHaveLength(2);
    expect(result.proposals.every((proposal: any) => proposal.lastBlockReason?.includes('selection is incomplete'))).toBe(true);
  });

  test('uses the compiler execution plan when a same-package update arrives before its create', async ({ page }) => {
    const packageId = 'pkg_compiler_order';
    const create = makePackageProposal(packageId, 'compiler_create', 'world_container', {
      id: 'container_compiler_order', name: 'Initial name', type: 'folder', isDefault: false, sortOrder: 0,
    });
    const update = makePackageProposal(packageId, 'compiler_update', 'world_container', {
      id: 'container_compiler_order', name: 'Updated by compiler',
    });
    update.proposedOperations[0].op = 'update';
    const orderedProposalIds = [create.id, update.id];
    [create, update].forEach((proposal, order) => {
      (proposal as any).packageCompiler = {
        contractVersion: 'w1-package-graph-v2',
        order,
        proposalCount: 2,
        orderedProposalIds,
      };
    });
    await injectImportPackage(page, [update, create]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    await expect(page.getByTestId('workbench-inbox-list')).toContainText('Inbox clear');
    const result = await page.evaluate(() => {
      const state = (window as any).__narrativeStore.getState();
      return { containers: state.worldContainers, pending: state.proposals.length, history: state.proposalHistory.map((proposal: any) => proposal.id) };
    });
    expect(result.containers).toEqual([expect.objectContaining({ id: 'container_compiler_order', name: 'Updated by compiler' })]);
    expect(result.pending).toBe(0);
    expect(result.history).toEqual(orderedProposalIds);
  });

  test('rejects inconsistent compiler order metadata and recompiles the legacy dependency order', async ({ page }) => {
    const packageId = 'pkg_inconsistent_compiler_order';
    const create = makePackageProposal(packageId, 'inconsistent_create', 'world_container', {
      id: 'container_inconsistent_order', name: 'Initial name', type: 'folder', isDefault: false, sortOrder: 0,
    });
    const update = makePackageProposal(packageId, 'inconsistent_update', 'world_container', {
      id: 'container_inconsistent_order', name: 'Updated after fallback compile',
    });
    update.proposedOperations[0].op = 'update';
    const invalidOrder = [update.id, create.id];
    [update, create].forEach((proposal) => {
      (proposal as any).packageCompiler = {
        contractVersion: 'w1-package-graph-v2',
        order: 0,
        proposalCount: 2,
        orderedProposalIds: invalidOrder,
      };
    });
    await injectImportPackage(page, [update, create]);

    await page.getByTestId(`accept-import-package-${packageTestId(packageId)}`).click();
    const result = await page.evaluate(() => {
      const state = (window as any).__narrativeStore.getState();
      return { containers: state.worldContainers, pending: state.proposals.length };
    });
    expect(result.containers).toEqual([
      expect.objectContaining({ id: 'container_inconsistent_order', name: 'Updated after fallback compile' }),
    ]);
    expect(result.pending).toBe(0);
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
    await page.evaluate(() => {
      const store = (window as any).__narrativeStore;
      return store.getState().resolveProposals(store.getState().proposals.map((proposal: any) => proposal.id), 'accepted');
    });
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

    await expect(page.getByTestId(`repair-blocked-package-${packageTestId(packageId)}`)).toBeVisible();
  });
});
