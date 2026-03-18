import type {
  CreateProjectInput,
  ExportArtifact,
  ExportProjectInput,
  Locale,
  NarrativeProject,
  ProjectTemplate,
  Proposal,
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

const safeReadText = (fs: typeof import('fs'), filePath: string, fallback = '') => {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : fallback;
};

const readJsonFilesSafe = <T = Record<string, unknown>>(runtime: NodeRuntime, directory: string): T[] => {
  if (!runtime.fs.existsSync(directory)) {
    return [] as T[];
  }
  return runtime.fs
    .readdirSync(directory)
    .filter((fileName) => fileName.endsWith('.json'))
    .map((fileName) => JSON.parse(runtime.fs.readFileSync(runtime.path.join(directory, fileName), 'utf8')) as T);
};

const normalizeBranches = (branches: unknown): NarrativeProject['timelineBranches'] =>
  Array.isArray(branches)
    ? branches.map((branch, index) => {
        const value = branch as Record<string, unknown>;
        return {
          id: String(value.id || `branch_${index}`),
          name: String(value.name || `Branch ${index + 1}`),
          description: value.description ? String(value.description) : '',
          parentBranchId: value.parentBranchId ? String(value.parentBranchId) : null,
          forkEventId: value.forkEventId ? String(value.forkEventId) : null,
          mergeEventId: value.mergeEventId ? String(value.mergeEventId) : null,
          color: value.color ? String(value.color) : '#f59e0b',
          sortOrder: typeof value.sortOrder === 'number' ? value.sortOrder : index,
          collapsed: Boolean(value.collapsed),
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
    characters: rawProject.characters || fallbackProject.characters,
    characterTags: rawProject.characterTags || fallbackProject.characterTags,
    candidates: rawProject.candidates || fallbackProject.candidates,
    timelineBranches: normalizeBranches(rawProject.timelineBranches || fallbackProject.timelineBranches),
    timelineEvents: (rawProject.timelineEvents || fallbackProject.timelineEvents).map((event, index) => ({
      ...event,
      orderIndex: typeof event.orderIndex === 'number' ? event.orderIndex : index,
      sharedBranchIds: event.sharedBranchIds || [],
    })),
    relationships: rawProject.relationships || fallbackProject.relationships,
    chapters: rawProject.chapters || fallbackProject.chapters,
    scenes: rawProject.scenes || fallbackProject.scenes,
    worldContainers: rawProject.worldContainers || fallbackProject.worldContainers,
    worldItems: rawProject.worldItems || fallbackProject.worldItems,
    graphBoards: normalizeGraphBoards(rawProject.graphBoards || fallbackProject.graphBoards),
    betaPersonas: rawProject.betaPersonas || fallbackProject.betaPersonas,
    betaRuns: rawProject.betaRuns || fallbackProject.betaRuns,
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
    issues: rawProject.issues || fallbackProject.issues,
    exports: rawProject.exports || [],
    unreadUpdates: rawProject.unreadUpdates || fallbackProject.unreadUpdates,
    archivedIds: rawProject.archivedIds || [],
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

  return migrated;
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
  project.timelineEvents.forEach((event) => {
    writeJson(fs, path.join(timelineDir, `${event.id}.json`), event);
  });
  writeJson(fs, path.join(worldDir, 'containers.json'), project.worldContainers);
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
  writeJson(fs, path.join(systemDir, 'inbox.json'), project.proposals);
  writeJson(fs, path.join(systemDir, 'history.json'), project.proposalHistory);
  writeJson(fs, path.join(systemDir, 'issues.json'), project.issues);
  writeJson(fs, path.join(systemDir, 'exports.json'), project.exports);
  writeJson(fs, path.join(schemaDir, 'schema.json'), {
    schemaVersion: project.metadata.schemaVersion,
    updatedAt: project.metadata.updatedAt,
    capabilities: project.metadata.capabilities,
    storageBackends: project.metadata.storageBackends,
    futureBackends: project.metadata.futureBackends,
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
      worldItems: readJsonFilesSafe<NarrativeProject['worldItems'][number]>(runtime, worldDir).filter((item) => item.id),
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
    if (!runtime) {
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
      };
    }

    const exportDir = runtime.path.join(project.metadata.rootPath, 'exports', input.format === 'markdown' ? 'markdown' : 'html');
    ensureDir(runtime.fs, exportDir);
    const exportPath = runtime.path.join(exportDir, fileName);
    runtime.fs.writeFileSync(exportPath, preview, 'utf8');
    return {
      id: `export_${timestamp}`,
      format: input.format,
      fileName,
      path: exportPath,
      createdAt: new Date().toISOString(),
      preview,
    };
  },

  renderExport(project: NarrativeProject, input: ExportProjectInput): string {
    const sceneBlocks = project.chapters
      .sort((a, b) => a.orderIndex - b.orderIndex)
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

    return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${project.metadata.name}</title><style>body{font-family:Georgia,serif;max-width:900px;margin:40px auto;line-height:1.7;color:#111}h1,h2{font-family:Arial,sans-serif}</style></head><body><h1>${project.metadata.name}</h1>${project.chapters
      .sort((a, b) => a.orderIndex - b.orderIndex)
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

    const resolvedProposal: Proposal = {
      ...target,
      status: nextStatus,
      resolvedAt: new Date().toISOString(),
    };

    return {
      ...project,
      proposals: project.proposals.filter((proposal) => proposal.id !== proposalId),
      proposalHistory: [resolvedProposal, ...project.proposalHistory],
      unreadUpdates: {
        ...project.unreadUpdates,
        entities: {
          ...project.unreadUpdates.entities,
          [proposalId]: false,
        },
        activities: {
          ...project.unreadUpdates.activities,
          workbench: project.proposals.length > 1,
        },
        sections: {
          ...project.unreadUpdates.sections,
          'workbench.inbox': project.proposals.length > 1,
        },
      },
    };
  },
};
