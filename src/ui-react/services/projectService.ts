import type {
  CreateProjectInput,
  DependencyEdge,
  EntityKind,
  ExportArtifact,
  ExportProjectInput,
  Locale,
  NarrativeProject,
  PackageSource,
  ProjectTemplate,
  Proposal,
  ProposalOperation,
  ProposalPackage,
  StorageMode,
} from '../models/project';
import { PROJECT_SCHEMA_VERSION } from '../models/project';
import { createBlankProject, createStarterProject } from '../mock/seedProject';

const STORAGE_KEY = 'narrative-ide-project';
const LAST_PATH_KEY = 'narrative-ide-last-path';

type NodeRuntime = {
  fs: typeof import('fs');
  path: typeof import('path');
  process: NodeJS.Process;
  buffer: typeof import('buffer');
};

const getNodeRuntime = (): NodeRuntime | null => {
  const scope = globalThis as typeof globalThis & { require?: NodeRequire; process?: NodeJS.Process };
  const loader = scope.require;
  if (!loader) {
    return null;
  }

  try {
    return {
      fs: loader('fs'),
      path: loader('path'),
      process: scope.process || loader('process'),
      buffer: loader('buffer'),
    };
  } catch {
    return null;
  }
};

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || 'narrative-project';

const writeJson = (fs: typeof import('fs'), filePath: string, payload: unknown) => {
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), 'utf8');
};

const writeText = (fs: typeof import('fs'), filePath: string, payload: string) => {
  fs.writeFileSync(filePath, payload, 'utf8');
};

const ensureDir = (fs: typeof import('fs'), directory: string) => {
  if (!fs.existsSync(directory)) {
    fs.mkdirSync(directory, { recursive: true });
  }
};

const createProjectByTemplate = (
  template: ProjectTemplate,
  name: string,
  rootPath: string,
  locale: Locale,
  storageMode: StorageMode
) => {
  return template === 'blank'
    ? createBlankProject(name, rootPath, locale, storageMode)
    : createStarterProject(name, rootPath, locale, storageMode);
};

const safeReadJson = <T>(fs: typeof import('fs'), filePath: string, fallback: T): T => {
  return fs.existsSync(filePath) ? (JSON.parse(fs.readFileSync(filePath, 'utf8')) as T) : fallback;
};

const normalizeIdentityKey = (value: unknown) =>
  String(value || '').trim().toLowerCase().replace(/\s+/g, '');

const uniqueStrings = (values: unknown[]) =>
  Array.from(new Set(values.flatMap((value) => Array.isArray(value) ? value : [value]).map((value) => String(value || '').trim()).filter(Boolean)));

const isImportProposal = (proposal: Proposal) => {
  const raw = proposal as Proposal & { source_workflow?: string; sourceWorkflow?: string };
  return proposal.source === 'import'
    || raw.source_workflow === 'W1_import'
    || raw.sourceWorkflow === 'W1_import'
    || String(proposal.originTaskRunId || '').startsWith('W1');
};

const mergeDiskInboxForSave = (
  fs: typeof import('fs'),
  inboxPath: string,
  incoming: Proposal[],
  history: Proposal[]
) => {
  const diskInbox = safeReadJson<Proposal[]>(fs, inboxPath, []);
  if (!diskInbox.length) return incoming;

  const incomingIds = new Set(incoming.map((proposal) => proposal.id));
  const resolvedIds = new Set(history.map((proposal) => proposal.id));
  const protectedDiskProposals = diskInbox.filter((proposal) =>
    isImportProposal(proposal)
    && !incomingIds.has(proposal.id)
    && !resolvedIds.has(proposal.id)
  );

  return [...protectedDiskProposals, ...incoming];
};

const safeReadText = (fs: typeof import('fs'), filePath: string, fallback = '') => {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : fallback;
};

const WORLD_CATEGORY_PATH_MAP: Record<string, string[]> = {
  location:           ['世界模型', '地理位置'],
  organization:       ['世界模型', '门派组织'],
  faction:            ['世界模型', '门派组织'],
  item:               ['世界模型', '物品与法器'],
  artifact:           ['世界模型', '物品与法器'],
  cultivation_method: ['世界模型', '功法与术法'],
  rule:               ['世界模型', '修炼境界与制度'],
  system:             ['世界模型', '修炼境界与制度'],
  concept:            ['世界模型', '概念与设定'],
  culture:            ['世界模型', '文化与习俗'],
  custom:             ['世界模型', '概念与设定'],
};

function normalizeWorldItem(item: NarrativeProject['worldItems'][number]): NarrativeProject['worldItems'][number] {
  if (item.categoryPath && item.categoryPath.length > 0) return item;
  const category = (item as unknown as Record<string, unknown>).category as string | undefined;
  const root = (category && WORLD_CATEGORY_PATH_MAP[category]) ?? WORLD_CATEGORY_PATH_MAP['concept'];
  return {
    ...item,
    categoryPath: [...root, item.name],
    parentId: item.parentId ?? null,
    importCategoryKey: item.importCategoryKey ?? category ?? '',
  };
}

const readJsonFilesSafe = <T = Record<string, unknown>>(runtime: NodeRuntime, directory: string): T[] => {
  if (!runtime.fs.existsSync(directory)) {
    return [] as T[];
  }
  return runtime.fs
    .readdirSync(directory)
    .filter((fileName) => fileName.endsWith('.json'))
    .map((fileName) => JSON.parse(runtime.fs.readFileSync(runtime.path.join(directory, fileName), 'utf8')) as T);
};

/*
Timeline contract audit, resolved on 2026-04-03:
- `timelineBranches[].anchorStartPos` / `anchorEndPos` were being written but dropped during service normalization.
- `timelineBranches[].endAnchor` was missing from the normalized contract even though the canvas needs a persistent end snap reference.
- `project.json` persisted `counts.timelineEvents` but omitted `counts.timelineBranches`, which made the frontend audit report a false mismatch.
- SQLite JSON migration expected `tags`, while the project model exposes `characterTags`.
- The checked-in starter demo timeline JSON lagged behind the typed model and seed data for branch anchor metadata and event option fields.
Resolved by preserving both semantic anchors and resolved positions in the service/model, writing branch counts, fixing the DB migration key, and updating the starter demo JSON fixtures.
*/

const normalizeStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((entry) => String(entry)) : [];

const normalizePoint = (value: unknown): { x: number; y: number } | undefined => {
  const point = value as Record<string, unknown> | null | undefined;
  if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') {
    return undefined;
  }

  return {
    x: Number(point.x),
    y: Number(point.y),
  };
};

const normalizeBranchAnchor = (
  value: unknown,
): NarrativeProject['timelineBranches'][number]['startAnchor'] | NarrativeProject['timelineBranches'][number]['endAnchor'] => {
  const anchor = value as Record<string, unknown> | null | undefined;
  if (!anchor?.branchId || !anchor?.eventId) {
    return null;
  }

  return {
    branchId: String(anchor.branchId),
    eventId: String(anchor.eventId),
  };
};

const normalizeBranches = (branches: unknown): NarrativeProject['timelineBranches'] =>
  Array.isArray(branches)
    ? branches.map((branch, index) => {
        const value = branch as Record<string, unknown>;
        const startAnchor = normalizeBranchAnchor(value.startAnchor);
        const endAnchor =
          normalizeBranchAnchor(value.endAnchor) ||
          ((value.mergeEventId && value.mergeTargetBranchId)
            ? { branchId: String(value.mergeTargetBranchId), eventId: String(value.mergeEventId) }
            : null);
        const mergeEventId = value.mergeEventId ? String(value.mergeEventId) : endAnchor?.eventId ?? null;
        const mergeTargetBranchId = value.mergeTargetBranchId
          ? String(value.mergeTargetBranchId)
          : endAnchor?.branchId ?? null;
        return {
          id: String(value.id || `branch_${index}`),
          name: String(value.name || `Branch ${index + 1}`),
          description: value.description ? String(value.description) : '',
          parentBranchId: value.parentBranchId ? String(value.parentBranchId) : null,
          forkEventId: value.forkEventId ? String(value.forkEventId) : null,
          mergeEventId,
          color: value.color ? String(value.color) : '#f59e0b',
          sortOrder: typeof value.sortOrder === 'number' ? value.sortOrder : index,
          collapsed: Boolean(value.collapsed),
          mode: (value.mode as NarrativeProject['timelineBranches'][number]['mode']) || (index === 0 ? 'root' : value.parentBranchId ? 'forked' : 'independent'),
          startAnchor,
          endAnchor: endAnchor as NarrativeProject['timelineBranches'][number]['endAnchor'],
          endMode: (value.endMode as NarrativeProject['timelineBranches'][number]['endMode']) || (endAnchor ? 'merge' : 'open'),
          mergeTargetBranchId,
          geometry: {
            laneOffset: typeof (value.geometry as Record<string, unknown> | undefined)?.laneOffset === 'number' ? Number((value.geometry as Record<string, unknown>).laneOffset) : index * 96,
            bend: typeof (value.geometry as Record<string, unknown> | undefined)?.bend === 'number' ? Number((value.geometry as Record<string, unknown>).bend) : 0.25,
            thickness: typeof (value.geometry as Record<string, unknown> | undefined)?.thickness === 'number' ? Number((value.geometry as Record<string, unknown>).thickness) : 1,
          },
          anchorStartPos: normalizePoint(value.anchorStartPos),
          anchorEndPos: normalizePoint(value.anchorEndPos),
        };
      })
    : [];

const normalizeGraphBoards = (boards: unknown): NarrativeProject['graphBoards'] =>
  Array.isArray(boards)
    ? boards.map((board, index) => {
        const value = board as Record<string, unknown>;
        return {
          id: String(value.id || `board_${index}`),
          name: String(value.name || `Board ${index + 1}`),
          description: String(value.description || ''),
          nodes: Array.isArray(value.nodes) ? (value.nodes as NarrativeProject['graphBoards'][number]['nodes']) : [],
          edges: Array.isArray(value.edges) ? (value.edges as NarrativeProject['graphBoards'][number]['edges']) : [],
          view: {
            zoom: typeof (value.view as Record<string, unknown> | undefined)?.zoom === 'number' ? Number((value.view as Record<string, unknown>).zoom) : 1,
            panX: typeof (value.view as Record<string, unknown> | undefined)?.panX === 'number' ? Number((value.view as Record<string, unknown>).panX) : 0,
            panY: typeof (value.view as Record<string, unknown> | undefined)?.panY === 'number' ? Number((value.view as Record<string, unknown>).panY) : 0,
          },
          selectedNodeIds: Array.isArray(value.selectedNodeIds) ? (value.selectedNodeIds as string[]) : [],
          sortOrder: typeof value.sortOrder === 'number' ? value.sortOrder : index,
        };
      })
    : [];

const normalizeUiState = (raw: unknown, fallbackProject: NarrativeProject): NarrativeProject['uiState'] => {
  const value = (raw || {}) as Partial<NarrativeProject['uiState']>;
  const fallback = fallbackProject.uiState;
  return {
    panes: {
      ...fallback.panes,
      ...(value.panes || {}),
    },
    view: {
      ...fallback.view,
      ...(value.view || {}),
    },
    density: value.density || fallback.density,
    editorWidth: value.editorWidth || fallback.editorWidth,
    motionLevel: value.motionLevel || fallback.motionLevel,
    experimentalFlags: value.experimentalFlags || fallback.experimentalFlags,
  };
};

const CJK_DIGITS: Record<string, number> = {
  '〇': 0, '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000,
};

const parseChapterNumber = (title: string): number => {
  const arabic = title.match(/\d+/);
  if (arabic) return parseInt(arabic[0], 10);
  const cjk = title.match(/[〇零一二三四五六七八九十百千]+/);
  if (!cjk) return 9999;
  const chars = cjk[0].split('');
  let result = 0; let current = 0;
  for (const ch of chars) {
    const val = CJK_DIGITS[ch] ?? 0;
    if (val >= 10) { result += (current || 1) * val; current = 0; }
    else { current = val; }
  }
  return result + current;
};

const isBlankStarterChapter = (chapter: NarrativeProject['chapters'][number], scenes: NarrativeProject['scenes']) =>
  chapter.id === 'chap_1'
  && /^chapter 1$/i.test(chapter.title || '')
  && (chapter.summary || '').trim() === 'Starting chapter.'
  && scenes.some((scene) =>
    scene.id === 'scene_1'
    && scene.chapterId === 'chap_1'
    && /^scene 1$/i.test(scene.title || '')
    && !(scene.content || '').trim()
  );

const cleanupImportedWritingArtifacts = (project: NarrativeProject): NarrativeProject => {
  const importedChapters = project.chapters.filter((chapter) => chapter.id !== 'chap_1');
  if (!importedChapters.length) return project;

  const starterChapterIds = new Set(
    project.chapters
      .filter((chapter) => isBlankStarterChapter(chapter, project.scenes))
      .map((chapter) => chapter.id)
  );
  const starterSceneIds = new Set(
    project.scenes
      .filter((scene) => starterChapterIds.has(scene.chapterId) && !(scene.content || '').trim())
      .map((scene) => scene.id)
  );

  const duplicateSceneIds = new Set<string>();
  const scenesByChapter = new Map<string, NarrativeProject['scenes']>();
  for (const scene of project.scenes) {
    if (starterSceneIds.has(scene.id)) continue;
    const list = scenesByChapter.get(scene.chapterId) || [];
    list.push(scene);
    scenesByChapter.set(scene.chapterId, list);
  }
  for (const scenes of scenesByChapter.values()) {
    const byContent = new Map<string, NarrativeProject['scenes'][number]>();
    for (const scene of scenes) {
      const contentKey = (scene.content || '').trim();
      if (!contentKey) continue;
      const existing = byContent.get(contentKey);
      if (!existing) {
        byContent.set(contentKey, scene);
        continue;
      }
      const sceneLooksGenerated = /— content$/.test(scene.title || '');
      const existingLooksGenerated = /— content$/.test(existing.title || '');
      duplicateSceneIds.add(sceneLooksGenerated || !existingLooksGenerated ? scene.id : existing.id);
      if (!sceneLooksGenerated && existingLooksGenerated) {
        byContent.set(contentKey, scene);
      }
    }
  }

  const removedSceneIds = new Set([...starterSceneIds, ...duplicateSceneIds]);
  const chapters = project.chapters
    .filter((chapter) => !starterChapterIds.has(chapter.id))
    .sort((a, b) => a.orderIndex - b.orderIndex || parseChapterNumber(a.title) - parseChapterNumber(b.title) || a.title.localeCompare(b.title))
    .map((chapter, index) => ({
      ...chapter,
      orderIndex: index,
      sceneIds: chapter.sceneIds.filter((id) => !removedSceneIds.has(id)),
    }));
  const scenes = project.scenes
    .filter((scene) => !removedSceneIds.has(scene.id) && !starterChapterIds.has(scene.chapterId))
    .map((scene) => {
      const chapterScenes = project.scenes
        .filter((candidate) => candidate.chapterId === scene.chapterId && !removedSceneIds.has(candidate.id))
        .sort((a, b) => a.orderIndex - b.orderIndex || a.id.localeCompare(b.id));
      return { ...scene, orderIndex: Math.max(0, chapterScenes.findIndex((candidate) => candidate.id === scene.id)) };
    });

  return { ...project, chapters, scenes };
};

const migrateProject = (
  rawProject: Partial<NarrativeProject>,
  rootPath: string,
  storageMode: StorageMode,
  locale?: Locale
): NarrativeProject => {
  const fallbackProject = createStarterProject(
    (rawProject.metadata?.name as string | undefined) || 'Starter Demo Project',
    rootPath,
    locale || (rawProject.metadata?.locale as Locale | undefined) || 'en',
    storageMode
  );

  const migrated: NarrativeProject = {
    ...fallbackProject,
    ...rawProject,
    metadata: {
      ...fallbackProject.metadata,
      ...(rawProject.metadata || {}),
      schemaVersion: PROJECT_SCHEMA_VERSION,
      rootPath,
      storageMode,
      locale: locale || rawProject.metadata?.locale || fallbackProject.metadata.locale,
      updatedAt: new Date().toISOString(),
      capabilities: rawProject.metadata?.capabilities || fallbackProject.metadata.capabilities,
      storageBackends: rawProject.metadata?.storageBackends || fallbackProject.metadata.storageBackends,
      futureBackends: rawProject.metadata?.futureBackends || fallbackProject.metadata.futureBackends,
    },
    characters: (rawProject.characters || fallbackProject.characters).map((character) => ({
      ...character,
      importance: character.importance || 'ungrouped',
      groupKey: character.groupKey || character.importance || 'ungrouped',
      relationshipIds: character.relationshipIds || [],
      povInsights: character.povInsights || null,
    })),
    characterTags: rawProject.characterTags || fallbackProject.characterTags,
    candidates: rawProject.candidates || fallbackProject.candidates,
    timelineBranches: normalizeBranches(rawProject.timelineBranches || fallbackProject.timelineBranches),
    timelineEvents: (rawProject.timelineEvents || fallbackProject.timelineEvents).map((event, index) => ({
      ...event,
      orderIndex: typeof event.orderIndex === 'number' ? event.orderIndex : index,
      sharedBranchIds: normalizeStringArray(event.sharedBranchIds),
      importance: event.importance || 'medium',
      colorToken: event.colorToken || '',
      layoutLock: Boolean(event.layoutLock),
      modalStateHints: normalizeStringArray(event.modalStateHints),
      position: normalizePoint(event.position),
    })),
    relationships: (rawProject.relationships || fallbackProject.relationships).map((relationship) => ({
      ...relationship,
      category: relationship.category || 'general',
      directionality: relationship.directionality || 'bidirectional',
      status: relationship.status || 'active',
      sourceNotes: relationship.sourceNotes || '',
    })),
    chapters: rawProject.chapters || fallbackProject.chapters,
    scenes: rawProject.scenes || fallbackProject.scenes,
    worldContainers: rawProject.worldContainers || fallbackProject.worldContainers,
    worldItems: rawProject.worldItems || fallbackProject.worldItems,
    worldSettings: rawProject.worldSettings || fallbackProject.worldSettings,
    worldMaps: rawProject.worldMaps || fallbackProject.worldMaps,
    graphBoards: normalizeGraphBoards(rawProject.graphBoards || fallbackProject.graphBoards),
    betaPersonas: rawProject.betaPersonas || fallbackProject.betaPersonas,
    betaRuns: rawProject.betaRuns || fallbackProject.betaRuns,
    simulationEngines: rawProject.simulationEngines || fallbackProject.simulationEngines,
    simulationLabs: rawProject.simulationLabs || fallbackProject.simulationLabs,
    simulationReviewers: rawProject.simulationReviewers || fallbackProject.simulationReviewers,
    simulationRuns: rawProject.simulationRuns || fallbackProject.simulationRuns,
    taskRequests: rawProject.taskRequests || [],
    taskRuns: rawProject.taskRuns || [],
    taskArtifacts: rawProject.taskArtifacts || [],
    taskRunLogs: rawProject.taskRunLogs || [],
    importJobs: rawProject.importJobs || [],
    promptTemplates:
      Array.isArray(rawProject.promptTemplates) && rawProject.promptTemplates.length > 0
        ? rawProject.promptTemplates
        : fallbackProject.promptTemplates,
    ragDocuments: rawProject.ragDocuments || [],
    ragChunks: rawProject.ragChunks || [],
    ragManifest: rawProject.ragManifest || fallbackProject.ragManifest,
    retrievalHistory: rawProject.retrievalHistory || [],
    scripts: rawProject.scripts || [],
    storyboards: rawProject.storyboards || [],
    videoPackages: rawProject.videoPackages || [],
    proposals: rawProject.proposals || fallbackProject.proposals,
    proposalHistory: rawProject.proposalHistory || fallbackProject.proposalHistory,
    issues: (rawProject.issues || fallbackProject.issues).map((issue) => ({
      ...issue,
      visibility: issue.visibility || 'default',
      dismissedAt: issue.dismissedAt || null,
      resolvedByProposalId: issue.resolvedByProposalId || null,
      resolvedByRunId: issue.resolvedByRunId || null,
    })),
    exports: (rawProject.exports || []).map((artifact) => ({
      ...artifact,
      scope: artifact.scope || 'project',
      chapterIds: artifact.chapterIds || [],
    })),
    unreadUpdates: rawProject.unreadUpdates || fallbackProject.unreadUpdates,
    archivedIds: rawProject.archivedIds || [],
    metadataFiles: rawProject.metadataFiles || [],
    todos: rawProject.todos ?? [],
    uiState: normalizeUiState(rawProject.uiState, fallbackProject),
  };

  if (!migrated.uiState.view.activeGraphBoardId) {
    migrated.uiState.view.activeGraphBoardId = migrated.graphBoards[0]?.id || null;
  }
  if (!migrated.uiState.view.activeTimelineBranchId) {
    migrated.uiState.view.activeTimelineBranchId = migrated.timelineBranches[0]?.id || null;
  }
  if (!migrated.uiState.view.lastOpenedSceneId) {
    migrated.uiState.view.lastOpenedSceneId = migrated.scenes[0]?.id || null;
  }

  return cleanupImportedWritingArtifacts(migrated);
};

const serializeProjectToFolder = (
  project: NarrativeProject,
  runtime: NodeRuntime,
  rootPath: string
) => {
  const { fs, path } = runtime;
  ensureDir(fs, rootPath);

  const entitiesDir = path.join(rootPath, 'entities');
  const charactersDir = path.join(entitiesDir, 'characters');
  const timelineDir = path.join(entitiesDir, 'timeline');
  const worldDir = path.join(entitiesDir, 'world');
  const graphDir = path.join(entitiesDir, 'graph');
  const scriptsDir = path.join(entitiesDir, 'scripts');
  const storyboardsDir = path.join(entitiesDir, 'storyboards');
  const writingDir = path.join(rootPath, 'writing');
  const chaptersDir = path.join(writingDir, 'chapters');
  const scenesDir = path.join(writingDir, 'scenes');
  const systemDir = path.join(rootPath, 'system');
  const schemaDir = path.join(systemDir, 'schema');
  const tasksDir = path.join(systemDir, 'tasks');
  const runsDir = path.join(systemDir, 'runs');
  const runLogsDir = path.join(runsDir, 'logs');
  const promptsDir = path.join(systemDir, 'prompts');
  const promptTemplatesDir = path.join(promptsDir, 'templates');
  const importsDir = path.join(systemDir, 'imports');
  const importStagingDir = path.join(importsDir, 'staging');
  const ragDir = path.join(systemDir, 'rag');
  const ragDocsDir = path.join(ragDir, 'documents');
  const ragChunksDir = path.join(ragDir, 'chunks');
  const ragIndexesDir = path.join(ragDir, 'indexes');
  const assetsDir = path.join(rootPath, 'assets');
  const exportsDir = path.join(rootPath, 'exports');
  const videoExportsDir = path.join(exportsDir, 'video');

  [
    entitiesDir,
    charactersDir,
    timelineDir,
    worldDir,
    graphDir,
    scriptsDir,
    storyboardsDir,
    writingDir,
    chaptersDir,
    scenesDir,
    systemDir,
    schemaDir,
    tasksDir,
    runsDir,
    runLogsDir,
    promptsDir,
    promptTemplatesDir,
    importsDir,
    importStagingDir,
    ragDir,
    ragDocsDir,
    ragChunksDir,
    ragIndexesDir,
    path.join(assetsDir, 'portraits'),
    path.join(assetsDir, 'world'),
    path.join(assetsDir, 'maps'),
    path.join(assetsDir, 'graph'),
    path.join(exportsDir, 'markdown'),
    path.join(exportsDir, 'html'),
    videoExportsDir,
  ].forEach((directory) => ensureDir(fs, directory));

  writeJson(fs, path.join(rootPath, 'project.json'), {
    metadata: project.metadata,
    counts: {
      characters: project.characters.length,
      timelineBranches: project.timelineBranches.length,
      timelineEvents: project.timelineEvents.length,
      scenes: project.scenes.length,
      worldItems: project.worldItems.length,
      scripts: project.scripts.length,
      storyboards: project.storyboards.length,
      importJobs: project.importJobs.length,
      proposals: project.proposals.length,
      exports: project.exports.length,
    },
  });

  project.characters.forEach((character) => {
    writeJson(fs, path.join(charactersDir, `${character.id}.json`), character);
  });

  writeJson(fs, path.join(entitiesDir, 'character-tags.json'), project.characterTags);
  writeJson(fs, path.join(entitiesDir, 'candidates.json'), project.candidates);
  writeJson(fs, path.join(entitiesDir, 'relationships.json'), project.relationships);
  writeJson(fs, path.join(timelineDir, 'branches.json'), project.timelineBranches);
  const keepEventIds = new Set(project.timelineEvents.map((e) => e.id));
  // Delete stale event files (orphans left by previous deletions)
  if (fs.existsSync(timelineDir)) {
    fs.readdirSync(timelineDir).forEach((fileName) => {
      if (fileName === 'branches.json' || !fileName.endsWith('.json')) return;
      const eventId = fileName.replace(/\.json$/, '');
      if (!keepEventIds.has(eventId)) {
        try { fs.unlinkSync(path.join(timelineDir, fileName)); } catch { /* ignore */ }
      }
    });
  }
  project.timelineEvents.forEach((event) => {
    writeJson(fs, path.join(timelineDir, `${event.id}.json`), event);
  });
  writeJson(fs, path.join(worldDir, 'containers.json'), project.worldContainers);
  writeJson(fs, path.join(worldDir, 'settings.json'), project.worldSettings);
  writeJson(fs, path.join(worldDir, 'maps.json'), project.worldMaps);
  project.worldItems.forEach((item) => {
    writeJson(fs, path.join(worldDir, `${item.id}.json`), item);
  });
  project.graphBoards.forEach((board) => {
    writeJson(fs, path.join(graphDir, `${board.id}.json`), board);
  });
  project.scripts.forEach((script) => {
    writeJson(fs, path.join(scriptsDir, `${script.id}.json`), {
      ...script,
      content: undefined,
    });
    writeText(fs, path.join(scriptsDir, `${script.id}.fountain`), script.content || '');
  });
  project.storyboards.forEach((storyboard) => {
    writeJson(fs, path.join(storyboardsDir, `${storyboard.id}.json`), storyboard);
  });
  project.chapters.forEach((chapter) => {
    writeJson(fs, path.join(chaptersDir, `${chapter.id}.json`), chapter);
  });
  project.scenes.forEach((scene) => {
    fs.writeFileSync(path.join(scenesDir, `${scene.id}.md`), scene.content, 'utf8');
    writeJson(fs, path.join(scenesDir, `${scene.id}.meta.json`), {
      ...scene,
      content: undefined,
    });
  });
  const inboxPath = path.join(systemDir, 'inbox.json');
  writeJson(fs, inboxPath, mergeDiskInboxForSave(fs, inboxPath, project.proposals, project.proposalHistory));
  writeJson(fs, path.join(systemDir, 'history.json'), project.proposalHistory);
  writeJson(fs, path.join(systemDir, 'issues.json'), project.issues);
  writeJson(fs, path.join(systemDir, 'exports.json'), project.exports);
  writeJson(fs, path.join(schemaDir, 'schema.json'), {
    schemaVersion: project.metadata.schemaVersion,
    updatedAt: project.metadata.updatedAt,
    capabilities: project.metadata.capabilities,
    storageBackends: project.metadata.storageBackends,
    futureBackends: project.metadata.futureBackends,
    entities: {
      timelineBranch: {
        required: ['id', 'name', 'sortOrder'],
        optional: [
          'description',
          'parentBranchId',
          'forkEventId',
          'mergeEventId',
          'color',
          'collapsed',
          'mode',
          'startAnchor',
          'endAnchor',
          'endMode',
          'mergeTargetBranchId',
          'geometry',
          'anchorStartPos',
          'anchorEndPos',
        ],
      },
      timelineEvent: {
        required: ['id', 'title', 'summary', 'branchId', 'orderIndex', 'locationIds', 'participantCharacterIds', 'linkedSceneIds', 'linkedWorldItemIds', 'tags'],
        optional: ['time', 'sharedBranchIds', 'importance', 'colorToken', 'layoutLock', 'modalStateHints', 'position', 'globalOrderIndex', 'chapterNumber', 'sourceChunkIds', 'sourceOrder'],
      },
    },
  });
  writeJson(fs, path.join(systemDir, 'ui-state.json'), project.uiState);
  writeJson(fs, path.join(tasksDir, 'requests.json'), project.taskRequests);
  writeJson(fs, path.join(runsDir, 'runs.json'), project.taskRuns);
  writeJson(fs, path.join(runsDir, 'artifacts.json'), project.taskArtifacts);
  writeJson(fs, path.join(runsDir, 'logs.json'), project.taskRunLogs);
  project.taskRunLogs.forEach((logRef) => {
    if (logRef.path) {
      const resolvedLogPath = path.join(rootPath, logRef.path);
      ensureDir(fs, path.dirname(resolvedLogPath));
      if (!fs.existsSync(resolvedLogPath)) {
        writeText(fs, resolvedLogPath, '');
      }
    }
  });
  writeJson(fs, path.join(systemDir, 'beta-personas.json'), project.betaPersonas);
  writeJson(fs, path.join(systemDir, 'beta-runs.json'), project.betaRuns);
  writeJson(fs, path.join(systemDir, 'simulation-engines.json'), project.simulationEngines);
  writeJson(fs, path.join(systemDir, 'simulation-labs.json'), project.simulationLabs);
  writeJson(fs, path.join(systemDir, 'simulation-reviewers.json'), project.simulationReviewers);
  writeJson(fs, path.join(systemDir, 'simulation-runs.json'), project.simulationRuns);
  writeJson(fs, path.join(importsDir, 'jobs.json'), project.importJobs);
  project.importJobs.forEach((job) => {
    const jobDir = path.join(importStagingDir, job.id);
    ensureDir(fs, jobDir);
    writeJson(fs, path.join(jobDir, 'manifest.json'), job);
    writeJson(fs, path.join(jobDir, 'chapter_candidates.json'), job.chapterCandidates);
    writeJson(fs, path.join(jobDir, 'scene_candidates.json'), job.sceneCandidates);
    if (job.sourcePath) {
      const sourcePath = path.join(rootPath, job.sourcePath);
      ensureDir(fs, path.dirname(sourcePath));
      if (!fs.existsSync(sourcePath)) {
        const sourceBody = project.chapters.map((chapter) => `# ${chapter.title}`).join('\n\n');
        writeText(fs, sourcePath, sourceBody);
      }
    }
  });
  writeJson(fs, path.join(promptsDir, 'registry.json'), project.promptTemplates.map((template) => ({
    id: template.id,
    name: template.name,
    agentType: template.agentType,
    version: template.version,
    path: `system/prompts/templates/${template.id}.json`,
  })));
  project.promptTemplates.forEach((template) => {
    writeJson(fs, path.join(promptTemplatesDir, `${template.id}.json`), template);
  });
  writeJson(fs, path.join(ragDir, 'manifest.json'), project.ragManifest);
  writeJson(fs, path.join(ragDir, 'retrieval-history.json'), project.retrievalHistory);
  project.ragDocuments.forEach((document) => {
    writeJson(fs, path.join(ragDocsDir, `${document.id}.json`), document);
  });
  project.ragChunks.forEach((chunk) => {
    writeJson(fs, path.join(ragChunksDir, `${chunk.id}.json`), chunk);
  });
  writeJson(fs, path.join(ragIndexesDir, 'keyword-index.json'), {
    backend: project.ragManifest.activeBackend,
    documents: project.ragDocuments.map((document) => ({
      id: document.id,
      title: document.title,
      chunkIds: document.chunkIds,
    })),
    chunks: project.ragChunks.map((chunk) => ({
      id: chunk.id,
      documentId: chunk.documentId,
      keywords: chunk.keywords,
    })),
  });
  project.videoPackages.forEach((videoPackage) => {
    writeJson(fs, path.join(videoExportsDir, `${videoPackage.id}.json`), videoPackage);
    const manifestTargets = [
      videoPackage.promptPackagePath,
      videoPackage.providerPayloadPath,
      videoPackage.providerResponsePath,
      videoPackage.renderManifestPath,
    ].filter(Boolean) as string[];
    manifestTargets.forEach((target) => {
      const resolvedTarget = path.join(rootPath, target);
      ensureDir(fs, path.dirname(resolvedTarget));
      if (!fs.existsSync(resolvedTarget)) {
        writeJson(fs, resolvedTarget, {
          videoPackageId: videoPackage.id,
          status: videoPackage.status,
          provider: videoPackage.provider,
        });
      }
    });
  });
  writeJson(fs, path.join(systemDir, 'index-cache.json'), {
    unreadUpdates: project.unreadUpdates,
    archivedIds: project.archivedIds,
  });
};

const hydrateProjectMetadata = (
  project: NarrativeProject,
  rootPath: string,
  storageMode: StorageMode,
  locale?: Locale
): NarrativeProject => ({
  ...project,
  metadata: {
    ...project.metadata,
    schemaVersion: PROJECT_SCHEMA_VERSION,
    rootPath,
    storageMode,
    locale: locale || project.metadata.locale,
    capabilities: project.metadata.capabilities,
    storageBackends: project.metadata.storageBackends,
    futureBackends: project.metadata.futureBackends,
    updatedAt: new Date().toISOString(),
  },
});

const getDefaultProjectDir = (runtime: NodeRuntime, projectName: string) => {
  const baseDir = runtime.path.join(runtime.process.cwd(), 'data', 'projects');
  ensureDir(runtime.fs, baseDir);
  return runtime.path.join(baseDir, slugify(projectName));
};

export const projectService = {
  createProject(input: CreateProjectInput): NarrativeProject {
    const runtime = getNodeRuntime();
    const fallbackRoot = `memory://${slugify(input.name)}`;
    const rootPath = input.rootPath || (runtime ? getDefaultProjectDir(runtime, input.name) : fallbackRoot);
    const project = migrateProject(hydrateProjectMetadata(
      createProjectByTemplate(input.template, input.name, rootPath, input.locale, runtime ? 'nodefs' : 'memory'),
      rootPath,
      runtime ? 'nodefs' : 'memory',
      input.locale
    ), rootPath, runtime ? 'nodefs' : 'memory', input.locale);

    if (!runtime) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
      localStorage.setItem(LAST_PATH_KEY, project.metadata.rootPath);
      return project;
    }

    serializeProjectToFolder(project, runtime, rootPath);
    localStorage.setItem(LAST_PATH_KEY, rootPath);
    return project;
  },

  openProject(rootPath?: string | null): NarrativeProject {
    const runtime = getNodeRuntime();
    const resolvedPath = rootPath || localStorage.getItem(LAST_PATH_KEY);

    if (!runtime) {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return migrateProject(JSON.parse(stored) as NarrativeProject, resolvedPath || 'memory://starter-demo-project', 'memory');
      }
      const project = createStarterProject();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
      localStorage.setItem(LAST_PATH_KEY, project.metadata.rootPath);
      return project;
    }

    if (!resolvedPath || !runtime.fs.existsSync(resolvedPath)) {
      const project = this.createProject({
        name: 'Starter Demo Project',
        rootPath: getDefaultProjectDir(runtime, 'starter-demo-project'),
        template: 'starter-demo',
        locale: 'en',
      });
      return project;
    }

    const projectIndex = JSON.parse(runtime.fs.readFileSync(runtime.path.join(resolvedPath, 'project.json'), 'utf8'));
    const entitiesDir = runtime.path.join(resolvedPath, 'entities');
    const timelineDir = runtime.path.join(entitiesDir, 'timeline');
    const worldDir = runtime.path.join(entitiesDir, 'world');
    const graphDir = runtime.path.join(entitiesDir, 'graph');
    const scriptsDir = runtime.path.join(entitiesDir, 'scripts');
    const storyboardsDir = runtime.path.join(entitiesDir, 'storyboards');
    const chaptersDir = runtime.path.join(resolvedPath, 'writing', 'chapters');
    const scenesDir = runtime.path.join(resolvedPath, 'writing', 'scenes');
    const systemDir = runtime.path.join(resolvedPath, 'system');
    const tasksDir = runtime.path.join(systemDir, 'tasks');
    const runsDir = runtime.path.join(systemDir, 'runs');
    const promptsDir = runtime.path.join(systemDir, 'prompts');
    const promptTemplatesDir = runtime.path.join(promptsDir, 'templates');
    const importsDir = runtime.path.join(systemDir, 'imports');
    const ragDir = runtime.path.join(systemDir, 'rag');
    const ragDocsDir = runtime.path.join(ragDir, 'documents');
    const ragChunksDir = runtime.path.join(ragDir, 'chunks');
    const videoExportsDir = runtime.path.join(resolvedPath, 'exports', 'video');

    const sceneMetas = (runtime.fs.existsSync(scenesDir) ? runtime.fs.readdirSync(scenesDir) : [])
      .filter((fileName) => fileName.endsWith('.meta.json'))
      .map((fileName) => JSON.parse(runtime.fs.readFileSync(runtime.path.join(scenesDir, fileName), 'utf8')));

    const scriptMetas = readJsonFilesSafe<NarrativeProject['scripts'][number]>(runtime, scriptsDir);
    const folderFallback = createStarterProject(projectIndex.metadata?.name || 'Starter Demo Project', resolvedPath, projectIndex.metadata?.locale || 'en', 'nodefs');

    const exportsPath = runtime.path.join(systemDir, 'exports.json');
    const project = {
      metadata: projectIndex.metadata,
      characters: readJsonFilesSafe<NarrativeProject['characters'][number]>(runtime, runtime.path.join(entitiesDir, 'characters')),
      characterTags: safeReadJson(runtime.fs, runtime.path.join(entitiesDir, 'character-tags.json'), []),
      candidates: safeReadJson(runtime.fs, runtime.path.join(entitiesDir, 'candidates.json'), []),
      timelineBranches: safeReadJson(runtime.fs, runtime.path.join(timelineDir, 'branches.json'), []),
      timelineEvents: readJsonFilesSafe<NarrativeProject['timelineEvents'][number]>(runtime, timelineDir).filter((item) => item.id),
      relationships: safeReadJson(runtime.fs, runtime.path.join(entitiesDir, 'relationships.json'), []),
      chapters: readJsonFilesSafe<NarrativeProject['chapters'][number]>(runtime, chaptersDir),
      scenes: sceneMetas.map((meta) => ({
        ...meta,
        content: safeReadText(runtime.fs, runtime.path.join(scenesDir, `${meta.id}.md`), ''),
      })),
      worldContainers: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'containers.json'), []),
      worldSettings: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'settings.json'), folderFallback.worldSettings),
      worldMaps: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'maps.json'), folderFallback.worldMaps),
      worldItems: readJsonFilesSafe<NarrativeProject['worldItems'][number]>(runtime, worldDir)
        .filter((item) => item.id)
        .map(normalizeWorldItem),
      graphBoards: readJsonFilesSafe<NarrativeProject['graphBoards'][number]>(runtime, graphDir),
      scripts: scriptMetas.map((meta) => ({
        ...meta,
        content: safeReadText(runtime.fs, runtime.path.join(scriptsDir, `${meta.id}.fountain`), ''),
      })),
      storyboards: readJsonFilesSafe<NarrativeProject['storyboards'][number]>(runtime, storyboardsDir),
      proposals: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'inbox.json'), []),
      proposalHistory: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'history.json'), []),
      issues: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'issues.json'), []),
      exports: runtime.fs.existsSync(exportsPath)
        ? JSON.parse(runtime.fs.readFileSync(exportsPath, 'utf8'))
        : [],
      betaPersonas: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'beta-personas.json'), []),
      betaRuns: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'beta-runs.json'), []),
      simulationEngines: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'simulation-engines.json'), folderFallback.simulationEngines),
      simulationLabs: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'simulation-labs.json'), folderFallback.simulationLabs),
      simulationReviewers: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'simulation-reviewers.json'), folderFallback.simulationReviewers),
      simulationRuns: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'simulation-runs.json'), folderFallback.simulationRuns),
      taskRequests: safeReadJson(runtime.fs, runtime.path.join(tasksDir, 'requests.json'), []),
      taskRuns: safeReadJson(runtime.fs, runtime.path.join(runsDir, 'runs.json'), []),
      taskArtifacts: safeReadJson(runtime.fs, runtime.path.join(runsDir, 'artifacts.json'), []),
      taskRunLogs: safeReadJson(runtime.fs, runtime.path.join(runsDir, 'logs.json'), []),
      importJobs: safeReadJson(runtime.fs, runtime.path.join(importsDir, 'jobs.json'), []),
      promptTemplates: readJsonFilesSafe<NarrativeProject['promptTemplates'][number]>(runtime, promptTemplatesDir),
      ragDocuments: readJsonFilesSafe<NarrativeProject['ragDocuments'][number]>(runtime, ragDocsDir),
      ragChunks: readJsonFilesSafe<NarrativeProject['ragChunks'][number]>(runtime, ragChunksDir),
      ragManifest: safeReadJson<NarrativeProject['ragManifest']>(runtime.fs, runtime.path.join(ragDir, 'manifest.json'), {
        activeBackend: 'keyword',
        futureBackends: ['embedding'],
        storageBackend: 'project-folder-keyword-index',
      }),
      retrievalHistory: safeReadJson(runtime.fs, runtime.path.join(ragDir, 'retrieval-history.json'), []),
      videoPackages: readJsonFilesSafe<NarrativeProject['videoPackages'][number]>(runtime, videoExportsDir),
      uiState: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'ui-state.json'), undefined),
      ...safeReadJson(runtime.fs, runtime.path.join(systemDir, 'index-cache.json'), {
        unreadUpdates: { activities: {}, sections: {}, entities: {} },
        archivedIds: [],
      }),
    };

    localStorage.setItem(LAST_PATH_KEY, resolvedPath);
    const migrated = migrateProject(project, resolvedPath, 'nodefs', project.metadata.locale);
    serializeProjectToFolder(migrated, runtime, resolvedPath);
    return hydrateProjectMetadata(migrated, resolvedPath, 'nodefs', migrated.metadata.locale);
  },

  saveProject(project: NarrativeProject): NarrativeProject {
    const runtime = getNodeRuntime();
    const updatedProject = migrateProject(
      hydrateProjectMetadata(project, project.metadata.rootPath, runtime ? 'nodefs' : 'memory', project.metadata.locale),
      project.metadata.rootPath,
      runtime ? 'nodefs' : 'memory',
      project.metadata.locale
    );
    const isVirtualPath = !runtime || updatedProject.metadata.rootPath.startsWith('memory://');
    if (isVirtualPath) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedProject));
      localStorage.setItem(LAST_PATH_KEY, updatedProject.metadata.rootPath);
      return updatedProject;
    }

    serializeProjectToFolder(updatedProject, runtime, updatedProject.metadata.rootPath);
    localStorage.setItem(LAST_PATH_KEY, updatedProject.metadata.rootPath);
    return updatedProject;
  },

  async importAsset(file: File, assetKind: 'portraits' | 'maps' | 'world' | 'graph', projectRoot: string): Promise<string> {
    const runtime = getNodeRuntime();
    if (!runtime || projectRoot.startsWith('memory://')) {
      return await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
    }

    const safeName = `${Date.now()}-${file.name.replace(/[^a-zA-Z0-9._-]/g, '-')}`;
    const targetDir = runtime.path.join(projectRoot, 'assets', assetKind);
    ensureDir(runtime.fs, targetDir);
    const buffer = runtime.buffer.Buffer.from(await file.arrayBuffer());
    const targetPath = runtime.path.join(targetDir, safeName);
    runtime.fs.writeFileSync(targetPath, buffer);
    return targetPath;
  },

  exportProject(project: NarrativeProject, input: ExportProjectInput): ExportArtifact {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const baseName = slugify(project.metadata.name);
    const fileName = `${baseName}-${timestamp}.${input.format === 'markdown' ? 'md' : 'html'}`;
    const preview = this.renderExport(project, input);
    const runtime = getNodeRuntime();

    if (!runtime || project.metadata.rootPath.startsWith('memory://')) {
      return {
        id: `export_${timestamp}`,
        format: input.format,
        fileName,
        path: null,
        createdAt: new Date().toISOString(),
        preview,
        scope: input.scope || 'project',
        chapterIds: input.chapterIds || [],
      };
    }

    const exportDir = runtime.path.join(project.metadata.rootPath, 'exports', input.format === 'markdown' ? 'markdown' : 'html');
    ensureDir(runtime.fs, exportDir);
    const exportPath = runtime.path.join(exportDir, fileName);
    runtime.fs.writeFileSync(exportPath, preview, 'utf8');

    // Also export manuscript.json if it exists alongside the project
    const manuscriptSrc = runtime.path.join(project.metadata.rootPath, 'manuscript.json');
    if (runtime.fs.existsSync(manuscriptSrc)) {
      const manuscriptDest = runtime.path.join(exportDir, `${baseName}-${timestamp}-manuscript.json`);
      runtime.fs.copyFileSync(manuscriptSrc, manuscriptDest);
    }

    return {
      id: `export_${timestamp}`,
      format: input.format,
      fileName,
      path: exportPath,
      createdAt: new Date().toISOString(),
      preview,
      scope: input.scope || 'project',
      chapterIds: input.chapterIds || [],
    };
  },

  renderExport(project: NarrativeProject, input: ExportProjectInput): string {
    const chapters = project.chapters
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .filter((chapter) => input.scope !== 'chapter' || !input.chapterIds?.length || input.chapterIds.includes(chapter.id));
    const sceneBlocks = chapters
      .map((chapter) => {
        const scenes = project.scenes
          .filter((scene) => scene.chapterId === chapter.id)
          .sort((a, b) => a.orderIndex - b.orderIndex)
          .map((scene) => `## ${scene.title}\n\n${scene.content || scene.summary}`)
          .join('\n\n');
        return `# ${chapter.title}\n\n${chapter.summary}\n\n${scenes}`;
      })
      .join('\n\n');

    const appendices = input.includeAppendices
      ? `\n\n# Appendices\n\n## Characters\n${project.characters
          .map((character) => `- ${character.name}: ${character.summary}`)
          .join('\n')}\n\n## Timeline\n${project.timelineEvents
          .map((event) => `- ${event.title} (${event.time || 'n/a'})`)
          .join('\n')}`
      : '';

    if (input.format === 'markdown') {
      return `# ${project.metadata.name}\n\n${sceneBlocks}${appendices}`;
    }

    return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${project.metadata.name}</title><style>body{font-family:Georgia,serif;max-width:900px;margin:40px auto;line-height:1.7;color:#111}h1,h2{font-family:Arial,sans-serif}</style></head><body><h1>${project.metadata.name}</h1>${chapters
      .map((chapter) => {
        const scenes = project.scenes
          .filter((scene) => scene.chapterId === chapter.id)
          .sort((a, b) => a.orderIndex - b.orderIndex)
          .map((scene) => `<h2>${scene.title}</h2><p>${(scene.content || scene.summary).replace(/\n/g, '<br/>')}</p>`)
          .join('');
        return `<section><h1>${chapter.title}</h1><p>${chapter.summary}</p>${scenes}</section>`;
      })
      .join('')}${input.includeAppendices ? `<section><h1>Appendices</h1><h2>Characters</h2><ul>${project.characters
        .map((character) => `<li><strong>${character.name}</strong>: ${character.summary}</li>`)
        .join('')}</ul></section>` : ''}</body></html>`;
  },

  resolveProposal(project: NarrativeProject, proposalId: string, nextStatus: Proposal['status']): NarrativeProject {
    const target = project.proposals.find((proposal) => proposal.id === proposalId);
    if (!target) {
      return project;
    }

    const preparedProject = nextStatus === 'accepted' ? prepareProjectForImportApply(project, [target]) : project;
    const applyResult = nextStatus === 'accepted'
      ? applyProposalOperations(preparedProject, target)
      : { project, applied: false, blockedReason: null };
    if (nextStatus === 'accepted' && applyResult.blockedReason) {
      const annotatedProposal: Proposal = {
        ...target,
        lastBlockReason: applyResult.blockedReason,
        lastBlockedAt: new Date().toISOString(),
      };
      return {
        ...project,
        proposals: project.proposals.map((p) => p.id === proposalId ? annotatedProposal : p),
        issues: upsertProposalBlockedIssue(project.issues, target, applyResult.blockedReason),
        unreadUpdates: markProposalUnread(project.unreadUpdates, proposalId),
      };
    }

    const resolvedProposal: Proposal = {
      ...target,
      status: nextStatus,
      resolvedAt: new Date().toISOString(),
    };
    const remainingProposals = project.proposals.filter((proposal) => proposal.id !== proposalId);
    const hasUnreadInbox = remainingProposals.some((proposal) => proposal.status === 'pending' || !proposal.status);

    const withHistory: NarrativeProject = {
      ...applyResult.project,
      proposals: remainingProposals,
      proposalHistory: [resolvedProposal, ...project.proposalHistory],
      issues: applyResult.project.issues.map((issue) => {
        const relatesToProposal = issue.id === target.originIssueId || issue.suggestedProposalIds?.includes(proposalId);
        if (!relatesToProposal) {
          return issue;
        }
        const suggestedProposalIds = issue.suggestedProposalIds?.filter((id) => id !== proposalId);
        return {
          ...issue,
          status: nextStatus === 'accepted' ? 'resolved' : issue.status,
          visibility: nextStatus === 'accepted' ? 'history' : issue.visibility || 'default',
          dismissedAt: nextStatus === 'accepted' ? new Date().toISOString() : issue.dismissedAt || null,
          resolvedByProposalId: nextStatus === 'accepted' ? proposalId : issue.resolvedByProposalId || null,
          suggestedProposalIds,
        };
      }),
      unreadUpdates: {
        ...applyResult.project.unreadUpdates,
        entities: {
          ...applyResult.project.unreadUpdates.entities,
          [proposalId]: false,
          ...(nextStatus === 'accepted' ? buildResolvedProposalUnreadMap(target) : {}),
        },
        activities: {
          ...applyResult.project.unreadUpdates.activities,
          workbench: hasUnreadInbox,
        },
        sections: {
          ...applyResult.project.unreadUpdates.sections,
          'workbench.inbox': hasUnreadInbox,
        },
      },
    };

    return withHistory;
  },

  resolveProposals(project: NarrativeProject, proposalIds: string[], nextStatus: Proposal['status']): NarrativeProject {
    const idSet = new Set(proposalIds);
    const targets = project.proposals.filter((proposal) => idSet.has(proposal.id));
    if (!targets.length) return project;
    if (nextStatus !== 'accepted') {
      return targets.reduce((draft, proposal) => projectService.resolveProposal(draft, proposal.id, nextStatus), project);
    }
    return applyImportPackageBatches(project, targets);
  },
};

type ProposalApplyResult = { project: NarrativeProject; applied: boolean; blockedReason: string | null };
type RawProposalOperation = ProposalOperation & { entityType?: EntityKind | string; fields?: Record<string, unknown> };
type EntityCollectionKey =
  | 'characters'
  | 'candidates'
  | 'characterTags'
  | 'timelineEvents'
  | 'timelineBranches'
  | 'relationships'
  | 'chapters'
  | 'scenes'
  | 'worldContainers'
  | 'worldItems';

const proposalEntityCollections: Partial<Record<EntityKind, EntityCollectionKey>> = {
  character: 'characters',
  candidate: 'candidates',
  character_tag: 'characterTags',
  timeline_event: 'timelineEvents',
  timeline_branch: 'timelineBranches',
  relationship: 'relationships',
  chapter: 'chapters',
  scene: 'scenes',
  world_container: 'worldContainers',
  world_item: 'worldItems',
};

const proposalApplyPriority: Partial<Record<EntityKind, number>> = {
  world_container: 0,
  world_settings: 0,
  character_tag: 1,
  timeline_branch: 2,
  chapter: 3,
  scene: 4,
  world_item: 5,
  character: 6,
  timeline_event: 7,
  relationship: 8,
};

const importedProposalSource = (proposal: Proposal) => proposal.source === 'import';

const fallbackTimelineBranchId = (project: NarrativeProject) =>
  project.timelineBranches.find((branch) => branch.mode === 'root')?.id
  || project.timelineBranches[0]?.id
  || '';

const normalizeImportedProposalEntity = (
  project: NarrativeProject,
  proposal: Proposal,
  entityType: EntityKind,
  entity: Record<string, unknown>,
  referenceSets?: ReferenceSets,
): Record<string, unknown> => {
  if (!importedProposalSource(proposal)) return entity;

  const refs = referenceSets || collectReferenceSets(project);

  if (entityType === 'character') {
    return {
      ...entity,
      tagIds: uniqueStrings([entity.tagIds]).filter((id) => refs.tags.has(id)),
      linkedSceneIds: uniqueStrings([entity.linkedSceneIds]).filter((id) => refs.scenes.has(id)),
      linkedEventIds: uniqueStrings([entity.linkedEventIds]).filter((id) => refs.events.has(id)),
      linkedWorldItemIds: uniqueStrings([entity.linkedWorldItemIds]).filter((id) => refs.worldItems.has(id)),
    };
  }

  if (entityType !== 'timeline_event') return entity;

  const branchId = String(entity.branchId || '');
  if (!branchId || project.timelineBranches.some((branch) => branch.id === branchId)) return entity;

  const fallbackBranchId = fallbackTimelineBranchId(project);
  if (!fallbackBranchId) return entity;
  return { ...entity, branchId: fallbackBranchId };
};

type ReferenceSets = {
  characters: Set<string>;
  scenes: Set<string>;
  events: Set<string>;
  branches: Set<string>;
  worldItems: Set<string>;
  containers: Set<string>;
  tags: Set<string>;
  chapters: Set<string>;
};

const getProposalOperations = (proposal: Proposal): RawProposalOperation[] => {
  const sidecarOps = (proposal as unknown as { operations?: RawProposalOperation[] }).operations;
  if (Array.isArray(sidecarOps) && sidecarOps.length) return sidecarOps;
  if (Array.isArray(proposal.proposedOperations) && proposal.proposedOperations.length) return proposal.proposedOperations;
  if (proposal.entityType || proposal.data) {
    return [{
      op: proposal.targetEntityId ? 'update' : 'create',
      entityType: (proposal.entityType || proposal.targetEntityType) as EntityKind,
      entityId: proposal.targetEntityId,
      fields: proposal.data || {},
    }];
  }
  return [];
};

const rawProposalValue = (proposal: Proposal, key: string): unknown =>
  (proposal as Proposal & Record<string, unknown>)[key];

const extractImportRunFromPayloadPath = (payloadPath: string | null | undefined) => {
  const match = String(payloadPath || '').match(/system\/imports\/(?:staging\/)?([^/]+)/);
  return match?.[1] || '';
};

export const getProposalImportPackageKey = (proposal: Proposal): string | null => {
  const sourceWorkflow = String(rawProposalValue(proposal, 'source_workflow') || rawProposalValue(proposal, 'sourceWorkflow') || '');
  const isW1Import = proposal.source === 'import' || sourceWorkflow === 'W1_import';
  if (!isW1Import) return null;

  const explicitPackageId =
    rawProposalValue(proposal, 'importPackageId')
    || rawProposalValue(proposal, 'packageId')
    || rawProposalValue(proposal, 'importRunId')
    || rawProposalValue(proposal, 'import_run_id')
    || proposal.originTaskRunId
    || extractImportRunFromPayloadPath(proposal.payloadPath);
  const operationImportRunId = getProposalOperations(proposal)
    .map((operation) => operation.fields?.importRunId || operation.fields?.import_run_id)
    .find(Boolean);

  return `import:${String(explicitPackageId || operationImportRunId || sourceWorkflow || 'unscoped')}`;
};

const REVIEWER_SOURCES = new Set<string>(['quality_reviewer', 'fact_reviewer', 'consistency_reviewer', 'organizer']);

const getProposalReviewerPackageKey = (proposal: Proposal): string | null => {
  if (!REVIEWER_SOURCES.has(proposal.source)) return null;
  const runId =
    rawProposalValue(proposal, 'reviewerRunId') ||
    rawProposalValue(proposal, 'reviewer_run_id') ||
    proposal.originTaskRunId ||
    'unscoped';
  return `reviewer:${proposal.source}:${String(runId)}`;
};

export const getProposalPackageKey = (proposal: Proposal): string | null =>
  getProposalImportPackageKey(proposal) ?? getProposalReviewerPackageKey(proposal);

const ID_FIELDS: Record<string, string> = {
  branchId: 'branch',
  chapterId: 'chapter',
  povCharacterId: 'character',
  containerId: 'container',
  sourceId: 'source entity',
  targetId: 'target entity',
};
const ID_LIST_FIELDS: Record<string, string> = {
  participantCharacterIds: 'participant',
  linkedCharacterIds: 'character',
  linkedEventIds: 'event',
  linkedSceneIds: 'scene',
  linkedWorldItemIds: 'world item',
  locationIds: 'location',
  sceneIds: 'scene',
  tagIds: 'tag',
};

const extractIdRefs = (fields: Record<string, unknown>): Array<{ id: string; label: string }> => {
  const refs: Array<{ id: string; label: string }> = [];
  Object.entries(ID_FIELDS).forEach(([key, label]) => {
    const val = fields[key];
    if (typeof val === 'string' && val) refs.push({ id: val, label });
  });
  Object.entries(ID_LIST_FIELDS).forEach(([key, label]) => {
    const vals = fields[key];
    if (Array.isArray(vals)) {
      vals.forEach((v) => typeof v === 'string' && v && refs.push({ id: v, label }));
    }
  });
  return refs;
};

export const buildDependencyGraph = (proposals: Proposal[]): DependencyEdge[] => {
  const createdBy = new Map<string, string>();
  proposals.forEach((proposal) => {
    const ops = getProposalOperations(proposal);
    ops.forEach((op) => {
      if (op.op === 'create' && op.entityId) createdBy.set(String(op.entityId), proposal.id);
    });
    // Fall back to targetEntityId for proposals with no explicit create op
    if (proposal.targetEntityId && !ops.length) {
      createdBy.set(proposal.targetEntityId, proposal.id);
    }
  });

  const edges: DependencyEdge[] = [];
  const seen = new Set<string>();
  proposals.forEach((proposal) => {
    getProposalOperations(proposal).forEach((op) => {
      if (!op.fields) return;
      extractIdRefs(op.fields as Record<string, unknown>).forEach(({ id, label }) => {
        const creator = createdBy.get(id);
        if (creator && creator !== proposal.id) {
          const edgeKey = `${creator}|${proposal.id}`;
          if (!seen.has(edgeKey)) {
            seen.add(edgeKey);
            edges.push({ fromId: creator, toId: proposal.id, reason: `${label} referenced` });
          }
        }
      });
    });
  });
  return edges;
};

export const derivePackageRisk = (proposals: Proposal[]): 'low' | 'medium' | 'high' => {
  if (proposals.some((p) => p.lastBlockReason)) return 'high';
  if (proposals.some((p) => p.confidence !== undefined && p.confidence < 0.7)) return 'medium';
  return 'low';
};

const PACKAGE_SOURCE_LABELS: Record<PackageSource, string> = {
  w1_import: 'Import package',
  quality_reviewer: 'Quality reviewer repair',
  fact_reviewer: 'Fact reviewer repair',
  consistency_reviewer: 'Consistency reviewer repair',
  organizer: 'Organizer proposal',
};

const packageKeyToSource = (key: string): PackageSource => {
  if (key.startsWith('import:')) return 'w1_import';
  const m = key.match(/^reviewer:([^:]+):/);
  if (m && REVIEWER_SOURCES.has(m[1])) return m[1] as PackageSource;
  return 'w1_import';
};

export const buildProposalPackages = (proposals: Proposal[]): ProposalPackage[] => {
  const groups = new Map<string, Proposal[]>();
  proposals.forEach((proposal) => {
    const key = getProposalPackageKey(proposal);
    if (!key) return;
    groups.set(key, [...(groups.get(key) || []), proposal]);
  });

  return [...groups.entries()]
    .filter(([key, group]) => {
      if (group.length > 1) return true;
      // Single-proposal reviewer/organizer packages are valid user-facing units
      return REVIEWER_SOURCES.has(packageKeyToSource(key));
    })
    .map(([key, group]) => {
      const source = packageKeyToSource(key);
      const testId = key.replace(/[^a-zA-Z0-9_-]+/g, '-');
      const entityTypes = Array.from(new Set(group.map((p) => p.targetEntityType))).join(', ');
      return {
        id: testId,
        source,
        title: PACKAGE_SOURCE_LABELS[source],
        summary: `${group.length} proposals · ${entityTypes}`,
        risk: derivePackageRisk(group),
        proposals: group,
        dependencyGraph: buildDependencyGraph(group),
        blockedReason: group.find((p) => p.lastBlockReason)?.lastBlockReason,
      };
    });
};

const isFullImportPackageSelection = (
  project: NarrativeProject,
  targets: Proposal[],
  packageKey: string,
) => {
  const selectedIds = new Set(targets.map((proposal) => proposal.id));
  const pendingPackageIds = project.proposals
    .filter((proposal) => (proposal.status === 'pending' || !proposal.status) && getProposalPackageKey(proposal) === packageKey)
    .map((proposal) => proposal.id);
  return pendingPackageIds.length > 1 && pendingPackageIds.every((id) => selectedIds.has(id));
};

const groupFullImportPackageSelections = (project: NarrativeProject, targets: Proposal[]) => {
  const groups = new Map<string, Proposal[]>();
  targets.forEach((proposal) => {
    const packageKey = getProposalPackageKey(proposal);
    if (!packageKey) return;
    groups.set(packageKey, [...(groups.get(packageKey) || []), proposal]);
  });
  return [...groups.entries()]
    .filter(([packageKey]) => isFullImportPackageSelection(project, targets, packageKey))
    .map(([, proposals]) => proposals);
};

const proposalScopedId = (proposal: Proposal, entityType: string) =>
  `${entityType}_${proposal.id.replace(/^proposal_/, '').replace(/[^a-zA-Z0-9_]+/g, '_')}`;

const operationEntityId = (proposal: Proposal, operation: RawProposalOperation, entityType: EntityKind) =>
  String(operation.entityId || operation.fields?.id || proposal.targetEntityId || proposalScopedId(proposal, entityType));

const collectReferenceSets = (project: NarrativeProject, proposals: Proposal[] = []): ReferenceSets => {
  const refs: ReferenceSets = {
    characters: new Set(project.characters.map((item) => item.id)),
    scenes: new Set(project.scenes.map((item) => item.id)),
    events: new Set(project.timelineEvents.map((item) => item.id)),
    branches: new Set(project.timelineBranches.map((item) => item.id)),
    worldItems: new Set(project.worldItems.map((item) => item.id)),
    containers: new Set(project.worldContainers.map((item) => item.id)),
    tags: new Set(project.characterTags.map((item) => item.id)),
    chapters: new Set(project.chapters.map((item) => item.id)),
  };
  const adders: Partial<Record<EntityKind, Set<string>>> = {
    character: refs.characters,
    scene: refs.scenes,
    timeline_event: refs.events,
    timeline_branch: refs.branches,
    world_item: refs.worldItems,
    world_container: refs.containers,
    character_tag: refs.tags,
    chapter: refs.chapters,
  };
  proposals.forEach((proposal) => {
    getProposalOperations(proposal).forEach((operation) => {
      const entityType = operation.entityType as EntityKind | undefined;
      if (!entityType || operation.op === 'delete') return;
      adders[entityType]?.add(operationEntityId(proposal, operation, entityType));
    });
  });
  return refs;
};

const importProposalHasCanonicalWrites = (proposal: Proposal) =>
  proposal.source === 'import' && getProposalOperations(proposal).some((operation) => {
    const entityType = operation.entityType as EntityKind | undefined;
    return Boolean(entityType && proposalEntityCollections[entityType]);
  });

const prepareProjectForImportApply = (project: NarrativeProject, proposals: Proposal[]): NarrativeProject => {
  if (!proposals.some(importProposalHasCanonicalWrites)) return project;

  let draft = project;
  const hasOnlyStarterChapter =
    draft.chapters.length === 1 &&
    draft.chapters[0]?.id === 'chap_1' &&
    /^chapter 1$/i.test(draft.chapters[0]?.title || '') &&
    draft.scenes.length === 1 &&
    draft.scenes[0]?.id === 'scene_1' &&
    draft.scenes[0]?.chapterId === 'chap_1' &&
    !(draft.scenes[0]?.content || '').trim();
  if (hasOnlyStarterChapter) {
    draft = { ...draft, chapters: [], scenes: [] };
  }

  const hasOnlyStarterBranch =
    draft.timelineBranches.length === 1 &&
    draft.timelineBranches[0]?.id === 'branch_main' &&
    /^main branch$/i.test(draft.timelineBranches[0]?.name || '') &&
    draft.timelineEvents.length === 0;
  if (hasOnlyStarterBranch && proposals.some((proposal) => getProposalOperations(proposal).some((op) => op.entityType === 'timeline_branch'))) {
    draft = { ...draft, timelineBranches: [] };
  }

  const starterContainerIds = new Set(['cont_locations', 'cont_orgs', 'cont_items', 'cont_lore', 'cont_world_map', 'cont_notes']);
  if (proposals.some((proposal) => getProposalOperations(proposal).some((op) => op.entityType === 'world_container'))) {
    draft = {
      ...draft,
      worldContainers: draft.worldContainers.filter((container) => !starterContainerIds.has(container.id)),
      worldItems: draft.worldItems.filter((item) => !starterContainerIds.has(item.containerId)),
    };
  }

  return draft;
};

const applyProposalBatch = (project: NarrativeProject, proposals: Proposal[]): NarrativeProject => {
  const preparedProject = prepareProjectForImportApply(project, proposals);
  const references = collectReferenceSets(preparedProject, proposals);
  const sorted = [...proposals].sort((a, b) => {
    const aType = getProposalOperations(a)[0]?.entityType as EntityKind | undefined;
    const bType = getProposalOperations(b)[0]?.entityType as EntityKind | undefined;
    return (proposalApplyPriority[aType || 'proposal'] ?? 99) - (proposalApplyPriority[bType || 'proposal'] ?? 99);
  });

  let draft = preparedProject;
  const accepted: Proposal[] = [];
  const blocked: Proposal[] = [];

  sorted.forEach((proposal) => {
    const result = applyProposalOperations(draft, proposal, references);
    if (result.blockedReason) {
      blocked.push({
        ...proposal,
        lastBlockReason: result.blockedReason,
        lastBlockedAt: new Date().toISOString(),
      });
      draft = {
        ...draft,
        issues: upsertProposalBlockedIssue(draft.issues, proposal, result.blockedReason),
        unreadUpdates: markProposalUnread(draft.unreadUpdates, proposal.id),
      };
      return;
    }
    draft = result.project;
    accepted.push({ ...proposal, status: 'accepted', resolvedAt: new Date().toISOString() });
  });

  draft = pruneDanglingProposalReferences(draft);

  const acceptedIds = new Set(accepted.map((proposal) => proposal.id));
  const blockedById = new Map(blocked.map((proposal) => [proposal.id, proposal]));
  const remainingProposals = draft.proposals
    .filter((proposal) => !acceptedIds.has(proposal.id))
    .map((proposal) => blockedById.get(proposal.id) || proposal);
  const hasUnreadInbox = remainingProposals.some((proposal) => proposal.status === 'pending' || !proposal.status);
  const acceptedRefUpdates = Object.assign({}, ...accepted.map(buildResolvedProposalUnreadMap));

  return {
    ...draft,
    proposals: remainingProposals,
    proposalHistory: [...accepted, ...project.proposalHistory],
    issues: draft.issues.map((issue) => {
      const acceptedRelatedIds = issue.suggestedProposalIds?.filter((id) => acceptedIds.has(id)) || [];
      if (!acceptedRelatedIds.length) return issue;
      const suggestedProposalIds = issue.suggestedProposalIds?.filter((id) => !acceptedIds.has(id));
      return {
        ...issue,
        status: 'resolved',
        visibility: 'history',
        dismissedAt: new Date().toISOString(),
        resolvedByProposalId: acceptedRelatedIds[0] || issue.resolvedByProposalId || null,
        suggestedProposalIds,
      };
    }),
    unreadUpdates: {
      ...draft.unreadUpdates,
      entities: {
        ...draft.unreadUpdates.entities,
        ...Object.fromEntries(accepted.map((proposal) => [proposal.id, false])),
        ...acceptedRefUpdates,
      },
      activities: { ...draft.unreadUpdates.activities, workbench: hasUnreadInbox },
      sections: { ...draft.unreadUpdates.sections, 'workbench.inbox': hasUnreadInbox },
    },
  };
};

const applyImportPackageBatches = (project: NarrativeProject, targets: Proposal[]): NarrativeProject => {
  const packageGroups = groupFullImportPackageSelections(project, targets);
  const packageIds = new Set(packageGroups.flatMap((group) => group.map((proposal) => proposal.id)));
  const nonPackageTargets = targets.filter((proposal) => !packageIds.has(proposal.id));

  let draft = project;
  packageGroups.forEach((group) => {
    draft = applyProposalPackageTransaction(draft, group);
  });

  return nonPackageTargets.length ? applyProposalBatch(draft, nonPackageTargets) : draft;
};

const applyProposalPackageTransaction = (project: NarrativeProject, proposals: Proposal[]): NarrativeProject => {
  const preparedProject = prepareProjectForImportApply(project, proposals);
  const references = collectReferenceSets(preparedProject, proposals);
  const sorted = [...proposals].sort((a, b) => {
    const aType = getProposalOperations(a)[0]?.entityType as EntityKind | undefined;
    const bType = getProposalOperations(b)[0]?.entityType as EntityKind | undefined;
    return (proposalApplyPriority[aType || 'proposal'] ?? 99) - (proposalApplyPriority[bType || 'proposal'] ?? 99);
  });

  let draft = preparedProject;
  const accepted: Proposal[] = [];

  for (const proposal of sorted) {
    const result = applyProposalOperations(draft, proposal, references);
    if (result.blockedReason) {
      return blockImportPackage(project, proposals, proposal, result.blockedReason);
    }
    draft = result.project;
    accepted.push({ ...proposal, status: 'accepted', resolvedAt: new Date().toISOString() });
  }

  return finalizeAcceptedProposalBatch(project, pruneDanglingProposalReferences(draft), accepted);
};

const formatPackageBlockedReason = (proposal: Proposal, blockedReason: string) => {
  const edge = blockedReason.match(/^(.+?) references missing ([^:]+): (.+)$/);
  if (!edge) {
    return `Import package blocked by ${proposal.id}. Reason: ${blockedReason}`;
  }
  return `Import package blocked by ${proposal.id}. Blocking edge: ${edge[1]} -> ${edge[2]} ${edge[3]}. Reason: ${blockedReason}`;
};

const blockImportPackage = (
  project: NarrativeProject,
  proposals: Proposal[],
  culprit: Proposal,
  blockedReason: string,
): NarrativeProject => {
  const packageIds = new Set(proposals.map((proposal) => proposal.id));
  const reason = formatPackageBlockedReason(culprit, blockedReason);
  return {
    ...project,
    proposals: project.proposals.map((proposal) =>
      packageIds.has(proposal.id)
        ? { ...proposal, lastBlockReason: reason, lastBlockedAt: new Date().toISOString() }
        : proposal
    ),
    issues: upsertProposalBlockedIssue(project.issues, culprit, reason),
    unreadUpdates: proposals.reduce(
      (updates, proposal) => markProposalUnread(updates, proposal.id),
      project.unreadUpdates,
    ),
  };
};

const finalizeAcceptedProposalBatch = (
  baseProject: NarrativeProject,
  draft: NarrativeProject,
  accepted: Proposal[],
): NarrativeProject => {
  const acceptedIds = new Set(accepted.map((proposal) => proposal.id));
  const remainingProposals = draft.proposals.filter((proposal) => !acceptedIds.has(proposal.id));
  const hasUnreadInbox = remainingProposals.some((proposal) => proposal.status === 'pending' || !proposal.status);
  const acceptedRefUpdates = Object.assign({}, ...accepted.map(buildResolvedProposalUnreadMap));

  return {
    ...draft,
    proposals: remainingProposals,
    proposalHistory: [...accepted, ...baseProject.proposalHistory],
    issues: draft.issues.map((issue) => {
      const acceptedRelatedIds = issue.suggestedProposalIds?.filter((id) => acceptedIds.has(id)) || [];
      if (!acceptedRelatedIds.length) return issue;
      const suggestedProposalIds = issue.suggestedProposalIds?.filter((id) => !acceptedIds.has(id));
      return {
        ...issue,
        status: 'resolved',
        visibility: 'history',
        dismissedAt: new Date().toISOString(),
        resolvedByProposalId: acceptedRelatedIds[0] || issue.resolvedByProposalId || null,
        suggestedProposalIds,
      };
    }),
    unreadUpdates: {
      ...draft.unreadUpdates,
      entities: {
        ...draft.unreadUpdates.entities,
        ...Object.fromEntries(accepted.map((proposal) => [proposal.id, false])),
        ...acceptedRefUpdates,
      },
      activities: { ...draft.unreadUpdates.activities, workbench: hasUnreadInbox },
      sections: { ...draft.unreadUpdates.sections, 'workbench.inbox': hasUnreadInbox },
    },
  };
};

const pruneDanglingProposalReferences = (project: NarrativeProject): NarrativeProject => {
  const refs = collectReferenceSets(project);
  const firstBranchId = project.timelineBranches[0]?.id || '';
  const firstChapterId = project.chapters[0]?.id || '';
  return {
    ...project,
    chapters: project.chapters.map((chapter) => ({
      ...chapter,
      sceneIds: chapter.sceneIds.filter((id) => refs.scenes.has(id)),
    })),
    scenes: project.scenes.map((scene) => ({
      ...scene,
      chapterId: refs.chapters.has(scene.chapterId) ? scene.chapterId : firstChapterId,
      linkedCharacterIds: scene.linkedCharacterIds.filter((id) => refs.characters.has(id)),
      linkedEventIds: scene.linkedEventIds.filter((id) => refs.events.has(id)),
      linkedWorldItemIds: scene.linkedWorldItemIds.filter((id) => refs.worldItems.has(id)),
    })),
    characters: project.characters.map((character) => ({
      ...character,
      tagIds: character.tagIds.filter((id) => refs.tags.has(id)),
      linkedSceneIds: character.linkedSceneIds.filter((id) => refs.scenes.has(id)),
      linkedEventIds: character.linkedEventIds.filter((id) => refs.events.has(id)),
      linkedWorldItemIds: character.linkedWorldItemIds.filter((id) => refs.worldItems.has(id)),
    })),
    timelineEvents: project.timelineEvents.map((event) => ({
      ...event,
      branchId: refs.branches.has(event.branchId) ? event.branchId : firstBranchId,
      participantCharacterIds: event.participantCharacterIds.filter((id) => refs.characters.has(id)),
      linkedSceneIds: event.linkedSceneIds.filter((id) => refs.scenes.has(id)),
      linkedWorldItemIds: event.linkedWorldItemIds.filter((id) => refs.worldItems.has(id)),
      locationIds: event.locationIds.filter((id) => refs.worldItems.has(id)),
    })),
    worldItems: project.worldItems.map((item) => ({
      ...item,
      linkedCharacterIds: item.linkedCharacterIds.filter((id) => refs.characters.has(id)),
      linkedEventIds: item.linkedEventIds.filter((id) => refs.events.has(id)),
      linkedSceneIds: item.linkedSceneIds.filter((id) => refs.scenes.has(id)),
    })),
    relationships: project.relationships.filter((rel) => refs.characters.has(rel.sourceId) && refs.characters.has(rel.targetId)),
  };
};

const applyProposalOperations = (project: NarrativeProject, proposal: Proposal, referenceSets?: ReferenceSets): ProposalApplyResult => {
  const operations = getProposalOperations(proposal);
  if (!operations.length) return { project, applied: false, blockedReason: null };

  let draft = project;
  let applied = false;

  for (const operation of operations) {
    const entityType = operation.entityType as EntityKind | undefined;
    const collectionKey = entityType ? proposalEntityCollections[entityType] : undefined;
    if (!entityType) {
      continue;
    }

    if (entityType === 'world_settings') {
      const result = applyWorldSettingsProposalOperation(draft, proposal, operation);
      if (result.blockedReason) {
        return { project, applied: false, blockedReason: result.blockedReason };
      }
      draft = result.project;
      applied = applied || result.applied;
      continue;
    }

    if (!collectionKey) {
      continue;
    }

    const result = applyProposalOperation(draft, proposal, operation, entityType, collectionKey, referenceSets);
    if (result.blockedReason) {
      return { project, applied: false, blockedReason: result.blockedReason };
    }
    draft = result.project;
    applied = applied || result.applied;
  }

  if (!applied) {
    return { project, applied: false, blockedReason: 'Proposal did not contain a supported canonical change.' };
  }

  return { project: draft, applied, blockedReason: null };
};

const applyWorldSettingsProposalOperation = (
  project: NarrativeProject,
  proposal: Proposal,
  operation: RawProposalOperation,
): ProposalApplyResult => {
  if (operation.op === 'delete') {
    return { project, applied: false, blockedReason: 'World settings cannot be deleted from the Workbench safety applier.' };
  }
  if (operation.op === 'link' || operation.op === 'unlink') {
    return { project, applied: false, blockedReason: `Proposal operation ${operation.op} is not supported for world settings.` };
  }

  const fields = operation.fields || proposal.data || {};
  return {
    project: {
      ...project,
      worldSettings: {
        ...project.worldSettings,
        ...fields,
      },
    },
    applied: true,
    blockedReason: null,
  };
};

const characterIdentityKeys = (entity: Record<string, unknown>) =>
  new Set(
    uniqueStrings([entity.name, entity.aliases])
      .map(normalizeIdentityKey)
      .filter(Boolean)
  );

const findImportedCharacterDuplicate = (
  records: Array<Record<string, unknown>>,
  id: string,
  entity: Record<string, unknown>,
) => {
  const keys = characterIdentityKeys(entity);
  if (!keys.size) return undefined;
  return records.find((entry) => {
    if (entry.id === id) return false;
    for (const key of characterIdentityKeys(entry)) {
      if (keys.has(key)) return true;
    }
    return false;
  });
};

const richerText = (left: unknown, right: unknown) => {
  const a = String(left || '').trim();
  const b = String(right || '').trim();
  return b.length > a.length ? b : a;
};

const importanceRank: Record<string, number> = {
  core: 4,
  major: 3,
  supporting: 2,
  minor: 1,
  ungrouped: 0,
};

const mergeImportedCharacterEntity = (
  existing: Record<string, unknown>,
  incoming: Record<string, unknown>,
) => {
  const existingImportance = String(existing.importance || existing.importImportance || 'ungrouped');
  const incomingImportance = String(incoming.importance || incoming.importImportance || 'ungrouped');
  const importance = importanceRank[incomingImportance] > importanceRank[existingImportance] ? incomingImportance : existingImportance;
  return {
    ...existing,
    aliases: uniqueStrings([existing.aliases, incoming.aliases, incoming.name]).filter((alias) => normalizeIdentityKey(alias) !== normalizeIdentityKey(existing.name)),
    summary: richerText(existing.summary, incoming.summary),
    background: richerText(existing.background, incoming.background),
    traits: uniqueStrings([existing.traits, incoming.traits]),
    tagIds: uniqueStrings([existing.tagIds, incoming.tagIds]),
    organizationIds: uniqueStrings([existing.organizationIds, incoming.organizationIds]),
    linkedSceneIds: uniqueStrings([existing.linkedSceneIds, incoming.linkedSceneIds]),
    linkedEventIds: uniqueStrings([existing.linkedEventIds, incoming.linkedEventIds]),
    linkedWorldItemIds: uniqueStrings([existing.linkedWorldItemIds, incoming.linkedWorldItemIds]),
    roleInStory: richerText(existing.roleInStory, incoming.roleInStory),
    physicalDescription: richerText(existing.physicalDescription, incoming.physicalDescription),
    notes: uniqueStrings([existing.notes, incoming.notes]),
    importConfidence: Math.max(Number(existing.importConfidence || 0), Number(incoming.importConfidence || 0)),
    importance,
    importImportance: importance,
    enrichmentRecommended: Boolean(existing.enrichmentRecommended || incoming.enrichmentRecommended),
  };
};

const applyProposalOperation = (
  project: NarrativeProject,
  proposal: Proposal,
  operation: RawProposalOperation,
  entityType: EntityKind,
  collectionKey: EntityCollectionKey,
  referenceSets?: ReferenceSets,
): ProposalApplyResult => {
  const records = project[collectionKey] as unknown as Array<Record<string, unknown>>;
  const fields = operation.fields || {};
  const id = operationEntityId(proposal, operation, entityType);

  if (operation.op === 'delete') {
    if (hasEntityReferences(project, entityType, id)) {
      return { project, applied: false, blockedReason: `Cannot delete ${entityType} ${id}; references still exist.` };
    }
    return {
      project: { ...project, [collectionKey]: records.filter((entry) => entry.id !== id) } as NarrativeProject,
      applied: records.some((entry) => entry.id === id),
      blockedReason: null,
    };
  }

  if (operation.op === 'link' || operation.op === 'unlink') {
    return { project, applied: false, blockedReason: `Proposal operation ${operation.op} is not supported by the Workbench safety applier.` };
  }

  const existing = records.find((entry) => entry.id === id);
  const rawNextEntity = operation.op === 'update'
    ? { ...(existing || {}), ...fields, id }
    : buildProposalEntity(project, proposal, entityType, id, fields);
  const nextEntity = normalizeImportedProposalEntity(project, proposal, entityType, rawNextEntity, referenceSets);

  if (operation.op === 'create' && existing && importedProposalSource(proposal)) {
    return { project, applied: true, blockedReason: null };
  }

  if (operation.op === 'create' && entityType === 'character' && importedProposalSource(proposal)) {
    const duplicate = findImportedCharacterDuplicate(records, id, nextEntity);
    if (duplicate) {
      const merged = normalizeImportedProposalEntity(
        project,
        proposal,
        entityType,
        mergeImportedCharacterEntity(duplicate, nextEntity),
        referenceSets,
      );
      const validationError = validateProposalEntityReferences(project, entityType, merged, referenceSets);
      if (validationError) {
        return { project, applied: false, blockedReason: validationError };
      }
      return {
        project: { ...project, [collectionKey]: records.map((entry) => entry.id === duplicate.id ? merged : entry) } as NarrativeProject,
        applied: true,
        blockedReason: null,
      };
    }
  }

  const validationError = validateProposalEntityReferences(project, entityType, nextEntity, referenceSets);
  if (validationError) {
    return { project, applied: false, blockedReason: validationError };
  }

  if (operation.op === 'update') {
    if (!existing) {
      return { project, applied: false, blockedReason: `Cannot update missing ${entityType} ${id}.` };
    }
    const updatedProject = { ...project, [collectionKey]: records.map((entry) => entry.id === id ? nextEntity : entry) } as NarrativeProject;
    return {
      project: syncSceneChapterMembership(updatedProject, entityType, id, nextEntity),
      applied: true,
      blockedReason: null,
    };
  }

  if (existing) {
    return { project, applied: false, blockedReason: `Cannot create duplicate ${entityType} ${id}.` };
  }

  const createdProject = { ...project, [collectionKey]: [...records, nextEntity] } as NarrativeProject;
  return {
    project: syncSceneChapterMembership(createdProject, entityType, id, nextEntity),
    applied: true,
    blockedReason: null,
  };
};

const syncSceneChapterMembership = (
  project: NarrativeProject,
  entityType: EntityKind,
  sceneId: string,
  entity: Record<string, unknown>,
): NarrativeProject => {
  if (entityType !== 'scene' || !entity.chapterId) return project;
  const chapterId = String(entity.chapterId);
  return {
    ...project,
    chapters: project.chapters.map((chapter) => {
      if (chapter.id !== chapterId || chapter.sceneIds.includes(sceneId)) return chapter;
      return { ...chapter, sceneIds: [...chapter.sceneIds, sceneId] };
    }),
  };
};

const buildProposalEntity = (
  project: NarrativeProject,
  proposal: Proposal,
  entityType: EntityKind,
  id: string,
  fields: Record<string, unknown>,
): Record<string, unknown> => {
  const title = String(fields.title || fields.name || proposal.title);
  switch (entityType) {
    case 'character':
      return { id, name: title, summary: '', background: '', aliases: [], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {}, ...fields };
    case 'candidate':
      return { id, name: title, background: '', summary: '', ...fields };
    case 'character_tag':
      return { id, name: title, color: '#f59e0b', description: '', characterIds: [], ...fields };
    case 'timeline_event':
      return { id, title, summary: '', branchId: project.timelineBranches[0]?.id || '', orderIndex: project.timelineEvents.length, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [], ...fields };
    case 'timeline_branch':
      return { id, name: title, description: '', color: '#f59e0b', sortOrder: project.timelineBranches.length, collapsed: false, mode: project.timelineBranches.length ? 'independent' : 'root', ...fields };
    case 'relationship':
      return { id, sourceId: '', targetId: '', type: 'related', description: '', ...fields };
    case 'chapter': {
      const chapterFields = { ...fields };
      if (chapterFields.orderIndex == null) delete chapterFields.orderIndex;
      return { id, title, summary: '', goal: '', notes: '', sceneIds: [], orderIndex: project.chapters.length, status: 'draft', ...chapterFields };
    }
    case 'scene':
      return { id, chapterId: project.chapters[0]?.id || '', title, summary: '', content: '', orderIndex: project.scenes.length, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft', ...fields };
    case 'world_container':
      return { id, name: title, type: 'notebook', isDefault: false, sortOrder: project.worldContainers.length, ...fields };
    case 'world_item': {
      const worldItemFields = { ...fields };
      if (worldItemFields.containerId == null) delete worldItemFields.containerId;
      return { id, containerId: project.worldContainers[0]?.id || '', type: 'note', name: title, description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], ...worldItemFields };
    }
    default:
      return { id, ...fields };
  }
};

const missingIds = (ids: unknown, allowedIds: Set<string>) =>
  (Array.isArray(ids) ? ids.map(String) : []).filter((id) => id && !allowedIds.has(id));

const validateProposalEntityReferences = (
  project: NarrativeProject,
  entityType: EntityKind,
  entity: Record<string, unknown>,
  referenceSets?: ReferenceSets,
): string | null => {
  const refs = referenceSets || collectReferenceSets(project);
  const { characters, scenes, events, branches, worldItems, containers, tags, chapters } = refs;

  const fail = (label: string, ids: string[]) => ids.length ? `${entityType} ${entity.id} references missing ${label}: ${ids.join(', ')}` : null;

  if (entityType === 'timeline_event') {
    if (entity.branchId && !branches.has(String(entity.branchId))) return `${entityType} ${entity.id} references missing branch: ${String(entity.branchId)}`;
    return fail('characters', missingIds(entity.participantCharacterIds, characters))
      || fail('scenes', missingIds(entity.linkedSceneIds, scenes))
      || fail('world items', [...missingIds(entity.locationIds, worldItems), ...missingIds(entity.linkedWorldItemIds, worldItems)]);
  }
  if (entityType === 'scene') {
    if (entity.chapterId && !chapters.has(String(entity.chapterId))) return `${entityType} ${entity.id} references missing chapter: ${String(entity.chapterId)}`;
    if (entity.povCharacterId && !characters.has(String(entity.povCharacterId))) return `${entityType} ${entity.id} references missing POV character: ${String(entity.povCharacterId)}`;
    return fail('characters', missingIds(entity.linkedCharacterIds, characters))
      || fail('events', missingIds(entity.linkedEventIds, events))
      || fail('world items', missingIds(entity.linkedWorldItemIds, worldItems));
  }
  if (entityType === 'chapter') return fail('scenes', missingIds(entity.sceneIds, scenes));
  if (entityType === 'character') {
    return fail('tags', missingIds(entity.tagIds, tags))
      || fail('scenes', missingIds(entity.linkedSceneIds, scenes))
      || fail('events', missingIds(entity.linkedEventIds, events))
      || fail('world items', missingIds(entity.linkedWorldItemIds, worldItems));
  }
  if (entityType === 'relationship') {
    return fail('characters', [String(entity.sourceId || ''), String(entity.targetId || '')].filter((id) => id && !characters.has(id)));
  }
  if (entityType === 'world_item') {
    if (entity.containerId && !containers.has(String(entity.containerId))) return `${entityType} ${entity.id} references missing container: ${String(entity.containerId)}`;
    return fail('characters', missingIds(entity.linkedCharacterIds, characters))
      || fail('events', missingIds(entity.linkedEventIds, events))
      || fail('scenes', missingIds(entity.linkedSceneIds, scenes));
  }
  return null;
};

const hasEntityReferences = (project: NarrativeProject, entityType: EntityKind, id: string) => {
  if (entityType === 'character') {
    return project.scenes.some((scene) => scene.povCharacterId === id || scene.linkedCharacterIds.includes(id))
      || project.timelineEvents.some((event) => event.participantCharacterIds.includes(id))
      || project.worldItems.some((item) => item.linkedCharacterIds.includes(id))
      || project.relationships.some((rel) => rel.sourceId === id || rel.targetId === id);
  }
  if (entityType === 'timeline_event') {
    return project.characters.some((character) => character.linkedEventIds.includes(id))
      || project.scenes.some((scene) => scene.linkedEventIds.includes(id))
      || project.worldItems.some((item) => item.linkedEventIds.includes(id))
      || project.timelineBranches.some((branch) => branch.forkEventId === id || branch.mergeEventId === id || branch.startAnchor?.eventId === id || branch.endAnchor?.eventId === id);
  }
  if (entityType === 'scene') {
    return project.characters.some((character) => character.linkedSceneIds.includes(id))
      || project.chapters.some((chapter) => chapter.sceneIds.includes(id))
      || project.timelineEvents.some((event) => event.linkedSceneIds.includes(id))
      || project.worldItems.some((item) => item.linkedSceneIds.includes(id));
  }
  if (entityType === 'world_item') {
    return project.characters.some((character) => character.linkedWorldItemIds.includes(id))
      || project.scenes.some((scene) => scene.linkedWorldItemIds.includes(id))
      || project.timelineEvents.some((event) => event.locationIds.includes(id) || event.linkedWorldItemIds.includes(id));
  }
  return false;
};

const markProposalUnread = (unreadUpdates: NarrativeProject['unreadUpdates'], proposalId: string): NarrativeProject['unreadUpdates'] => ({
  ...unreadUpdates,
  activities: { ...unreadUpdates.activities, workbench: true },
  sections: { ...unreadUpdates.sections, 'workbench.inbox': true },
  entities: { ...unreadUpdates.entities, [proposalId]: true },
});

const buildResolvedProposalUnreadMap = (proposal: Proposal): Record<string, boolean> => {
  const ids = [
    proposal.originIssueId,
    proposal.targetEntityId,
    ...(proposal.targetEntityRefs || []).map((ref) => ref.id),
  ].filter(Boolean) as string[];
  return Object.fromEntries(ids.map((id) => [id, false]));
};

const upsertProposalBlockedIssue = (
  issues: NarrativeProject['issues'],
  proposal: Proposal,
  reason: string,
): NarrativeProject['issues'] => {
  const id = `issue_proposal_blocked_${proposal.id}`;
  const existing = issues.find((issue) => issue.id === id);
  const nextIssue = {
    id,
    title: `Proposal blocked: ${proposal.title}`,
    description: reason,
    severity: 'high' as const,
    status: 'open' as const,
    source: proposal.source === 'consistency' ? 'consistency' as const : 'agent' as const,
    referenceIds: proposal.targetEntityRefs || [],
    suggestedProposalIds: [proposal.id],
    fixSuggestion: 'Review the proposal payload before accepting.',
    visibility: 'default' as const,
    originTaskRunId: proposal.originTaskRunId || null,
    resolvedByProposalId: null,
    dismissedAt: null,
  };
  return existing
    ? issues.map((issue) => issue.id === id ? { ...issue, ...nextIssue } : issue)
    : [nextIssue, ...issues];
};
