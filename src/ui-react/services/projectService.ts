import type {
  CreateProjectInput,
  ArtifactRef,
  DependencyEdge,
  EntityKind,
  ExportArtifact,
  ExportProjectInput,
  Locale,
  ManuscriptNode,
  ManuscriptNodeType,
  NarrativeProject,
  PackageSource,
  ProjectTemplate,
  Proposal,
  ProposalAcceptanceIntent,
  ProposalOperation,
  ProposalPackage,
  SemanticCoveragePolicy,
  SemanticCoverageRef,
  StorageMode,
  WorldCategoryNode,
} from '../models/project';
import { PROJECT_SCHEMA_VERSION } from '../models/project';
import { createBlankProject, createStarterProject } from '../mock/seedProject';
import { electronApi } from './electronApi';
import { commitProjectTransaction, recoverProjectTransactions, sha256Text } from './projectTransaction';

const STORAGE_KEY = 'narrative-ide-project';
const LAST_PATH_KEY = 'narrative-ide-last-path';

type NodeRuntime = {
  fs: typeof import('fs');
  path: typeof import('path');
  process: NodeJS.Process;
  buffer: typeof import('buffer');
};

const getNodeRuntime = (): NodeRuntime | null => {
  const projectFiles = electronApi.projectFiles();
  if (projectFiles) {
    const normalize = (value: string) => {
      const absolute = value.startsWith('/');
      const segments: string[] = [];
      for (const segment of value.replace(/\\/g, '/').split('/')) {
        if (!segment || segment === '.') continue;
        if (segment === '..') segments.pop(); else segments.push(segment);
      }
      return `${absolute ? '/' : ''}${segments.join('/')}` || (absolute ? '/' : '.');
    };
    const pathAdapter = {
      sep: '/',
      join: (...parts: string[]) => normalize(parts.filter(Boolean).join('/')),
      resolve: (...parts: string[]) => {
        let resolved = '';
        for (const part of parts) resolved = part.startsWith('/') ? part : `${resolved}/${part}`;
        return normalize(resolved);
      },
      dirname: (value: string) => {
        const normalized = normalize(value);
        const index = normalized.lastIndexOf('/');
        return index <= 0 ? '/' : normalized.slice(0, index);
      },
      relative: (from: string, to: string) => {
        const left = normalize(from).split('/').filter(Boolean);
        const right = normalize(to).split('/').filter(Boolean);
        while (left.length && right.length && left[0] === right[0]) { left.shift(); right.shift(); }
        return [...left.map(() => '..'), ...right].join('/');
      },
      isAbsolute: (value: string) => value.startsWith('/'),
    };
    return {
      fs: projectFiles as unknown as typeof import('fs'),
      path: pathAdapter as unknown as typeof import('path'),
      process: { cwd: () => '/' } as NodeJS.Process,
      buffer: { Buffer: { from: (value: ArrayBuffer) => new Uint8Array(value) } } as unknown as typeof import('buffer'),
    };
  }
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

function buildDefaultWorldCategories(worldItems: NarrativeProject['worldItems']): WorldCategoryNode[] {
  const root: WorldCategoryNode = { id: 'wcat_root', name: '世界模型', parentId: null, sortOrder: 0, scope: 'world' };
  const subcategoryNames = new Set<string>();
  for (const item of worldItems) {
    const sub = item.categoryPath?.[1];
    if (sub) subcategoryNames.add(sub);
  }
  // Fall back to WORLD_CATEGORY_PATH_MAP values if no items present.
  if (subcategoryNames.size === 0) {
    for (const path of Object.values(WORLD_CATEGORY_PATH_MAP)) {
      if (path[1]) subcategoryNames.add(path[1]);
    }
  }
  const leaves: WorldCategoryNode[] = Array.from(subcategoryNames).map((name, idx) => ({
    id: `wcat_${name.replace(/\s+/g, '_')}`,
    name,
    parentId: root.id,
    sortOrder: idx + 1,
    scope: 'world' as const,
  }));
  return [root, ...leaves];
}

function normalizeWorldItem(item: NarrativeProject['worldItems'][number]): NarrativeProject['worldItems'][number] {
  const folderId = item.folderId || item.containerId;
  if (item.categoryPath && item.categoryPath.length > 0) {
    return { ...item, folderId };
  }
  const category = (item as unknown as Record<string, unknown>).category as string | undefined;
  const root = (category && WORLD_CATEGORY_PATH_MAP[category]) ?? WORLD_CATEGORY_PATH_MAP['concept'];
  return {
    ...item,
    folderId,
    categoryPath: [...root, item.name],
    parentId: item.parentId ?? null,
    importCategoryKey: item.importCategoryKey ?? category ?? '',
  };
}

const parseChapterOrdinal = (title: unknown): number | null => {
  const text = String(title || '').trim();
  const arabic = text.match(/(?:chapter|ch\.?|第)?\s*(\d+)\s*(?:章|回|节)?/i);
  if (arabic) return Number(arabic[1]);
  const digits: Record<string, number> = { 零: 0, 〇: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  const match = text.match(/第\s*([零〇一二两三四五六七八九十百千\d]+)\s*[章节回]/);
  if (!match) return null;
  const raw = match[1];
  if (/^\d+$/.test(raw)) return Number(raw);
  let total = 0;
  let current = 0;
  const units: Record<string, number> = { 十: 10, 百: 100, 千: 1000 };
  for (const char of raw) {
    if (digits[char] != null) {
      current = digits[char];
      continue;
    }
    if (units[char]) {
      total += (current || 1) * units[char];
      current = 0;
      continue;
    }
    return null;
  }
  return total + current || null;
};

const chapterDedupeKey = (chapter: NarrativeProject['chapters'][number]) => {
  const ordinal = parseChapterOrdinal(chapter.title);
  return ordinal != null ? `ordinal:${ordinal}` : `title:${normalizeIdentityKey(chapter.title)}`;
};

const isBlankStarterChapterForNormalize = (
  chapter: NarrativeProject['chapters'][number],
  scenes: NarrativeProject['scenes'],
) => {
  const sceneIds = chapter.sceneIds || [];
  const chapterScenes = scenes.filter((scene) => sceneIds.includes(scene.id) || scene.chapterId === chapter.id);
  return chapter.id === 'chap_1'
    && /^chapter 1$/i.test(chapter.title || '')
    && chapterScenes.length <= 1
    && chapterScenes.every((scene) => scene.id === 'scene_1' && !(scene.content || '').trim());
};

const normalizeWritingCollections = (
  chapters: NarrativeProject['chapters'],
  scenes: NarrativeProject['scenes'],
): Pick<NarrativeProject, 'chapters' | 'scenes'> => {
  const importedChapters = chapters.filter((chapter) => !isBlankStarterChapterForNormalize(chapter, scenes));
  const sourceChapters = importedChapters.length ? importedChapters : chapters;
  const chapterIdMap = new Map<string, string>();
  const byKey = new Map<string, NarrativeProject['chapters'][number]>();

  [...sourceChapters]
    .sort((a, b) => (a.orderIndex ?? 9999) - (b.orderIndex ?? 9999) || String(a.title).localeCompare(String(b.title)))
    .forEach((chapter) => {
      const key = chapterDedupeKey(chapter);
      const existing = byKey.get(key);
      if (!existing) {
        byKey.set(key, { ...chapter, sceneIds: [...(chapter.sceneIds || [])] });
        chapterIdMap.set(chapter.id, chapter.id);
        return;
      }
      chapterIdMap.set(chapter.id, existing.id);
      existing.sceneIds = uniqueStrings([existing.sceneIds, chapter.sceneIds]);
      existing.summary = existing.summary || chapter.summary;
      existing.goal = existing.goal || chapter.goal;
      existing.notes = existing.notes || chapter.notes;
    });

  const normalizedChapters = Array.from(byKey.values()).map((chapter, index) => ({
    ...chapter,
    orderIndex: index,
  }));
  const validChapterIds = new Set(normalizedChapters.map((chapter) => chapter.id));
  const sceneByKey = new Map<string, NarrativeProject['scenes'][number]>();
  scenes
    .filter((scene) => !(scene.id === 'scene_1' && !validChapterIds.has(scene.chapterId) && !(scene.content || '').trim()))
    .forEach((scene) => {
      const chapterId = chapterIdMap.get(scene.chapterId) || scene.chapterId;
      if (!validChapterIds.has(chapterId)) return;
      const contentKey = normalizeIdentityKey((scene.content || '').slice(0, 240));
      const key = `${chapterId}:${normalizeIdentityKey(scene.title)}:${contentKey}`;
      if (sceneByKey.has(key)) return;
      sceneByKey.set(key, { ...scene, chapterId });
    });
  const normalizedScenes = Array.from(sceneByKey.values()).map((scene, index) => ({
    ...scene,
    orderIndex: scene.orderIndex ?? index,
  }));
  const sceneIdsByChapter = normalizedScenes.reduce<Record<string, string[]>>((acc, scene) => {
    acc[scene.chapterId] = [...(acc[scene.chapterId] || []), scene.id];
    return acc;
  }, {});
  return {
    chapters: normalizedChapters.map((chapter) => ({
      ...chapter,
      sceneIds: uniqueStrings([chapter.sceneIds, sceneIdsByChapter[chapter.id]]),
    })),
    scenes: normalizedScenes,
  };
};

const normalizeTimelineCollections = (
  branches: NarrativeProject['timelineBranches'],
  events: NarrativeProject['timelineEvents'],
): Pick<NarrativeProject, 'timelineBranches' | 'timelineEvents'> => {
  const eventBranchIds = new Set(events.map((event) => event.branchId).filter(Boolean));
  const genericBranchNames = new Set(['main branch', 'main timeline', '主时间线']);
  const isGenericEmptyBranch = (branch: NarrativeProject['timelineBranches'][number]) =>
    eventBranchIds.size > 0
    && !eventBranchIds.has(branch.id)
    && genericBranchNames.has(String(branch.name || '').trim().toLowerCase());
  const sourceBranches = branches.filter((branch) => !isGenericEmptyBranch(branch));
  const branchIds = new Set(sourceBranches.map((branch) => branch.id));
  const fallbackBranchId = sourceBranches[0]?.id || '';
  return {
    timelineBranches: sourceBranches,
    timelineEvents: events.map((event) => ({
      ...event,
      branchId: branchIds.has(event.branchId) ? event.branchId : fallbackBranchId,
    })),
  };
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

const isBlankStarterChapter = (chapter: NarrativeProject['chapters'][number], scenes: NarrativeProject['scenes']) => {
  const sceneIds = chapter.sceneIds || [];
  const chapterScenes = scenes.filter((scene) => scene.chapterId === chapter.id || sceneIds.includes(scene.id));
  if (chapterScenes.length !== 1 || sceneIds.length > 1) return false;
  const scene = chapterScenes[0];
  const chapterSummary = (chapter.summary || '').trim();
  const chapterGoal = (chapter.goal || '').trim();
  const chapterNotes = (chapter.notes || '').trim();
  const sceneSummary = (scene.summary || '').trim();
  return /^chapter 1$/i.test(chapter.title || '')
    && (!chapterSummary || chapterSummary === 'Starting chapter.')
    && (!chapterGoal || chapterGoal === 'Draft the first scenes.')
    && (!chapterNotes || chapterNotes === 'Use this chapter as your entry point.')
    && chapter.status === 'draft'
    && scene.chapterId === chapter.id
    && (!sceneIds.length || sceneIds[0] === scene.id)
    && /^scene 1$/i.test(scene.title || '')
    && (!sceneSummary || ['Empty starter scene.', 'An empty starting scene.'].includes(sceneSummary))
    && !(scene.content || '').trim()
    && !scene.povCharacterId
    && !(scene.linkedCharacterIds || []).length
    && !(scene.linkedEventIds || []).length
    && !(scene.linkedWorldItemIds || []).length
    && scene.status === 'draft';
};

const cleanupImportedWritingArtifacts = (project: NarrativeProject): NarrativeProject => {
  const starterChapterIds = new Set(
    ['blank', 'starter-demo'].includes(project.metadata.template || '')
      ? project.chapters
      .filter((chapter) => isBlankStarterChapter(chapter, project.scenes))
      .map((chapter) => chapter.id)
      : []
  );
  const importedChapters = project.chapters.filter((chapter) => !starterChapterIds.has(chapter.id));
  if (!starterChapterIds.size || !importedChapters.length) return project;
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
    characterTags: (rawProject.characterTags || fallbackProject.characterTags).map((tag, idx) => ({
      ...tag,
      parentTagId: tag.parentTagId !== undefined ? tag.parentTagId : null,
      sortOrder: tag.sortOrder !== undefined ? tag.sortOrder : idx,
    })),
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
    worldCategories: rawProject.worldCategories?.length
      ? rawProject.worldCategories
      : buildDefaultWorldCategories(rawProject.worldItems || fallbackProject.worldItems),
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
  const manuscriptDir = path.join(writingDir, 'manuscript');
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
    manuscriptDir,
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
  writeJson(fs, path.join(worldDir, 'categories.json'), project.worldCategories ?? []);
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
  writeJson(fs, path.join(manuscriptDir, 'nodes.json'), project.manuscriptNodes || []);
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
          // anchorStartPos, anchorEndPos removed — runtime-only, always stripped by toCanonical()
        ],
      },
      timelineEvent: {
        required: ['id', 'title', 'summary', 'branchId', 'orderIndex', 'locationIds', 'participantCharacterIds', 'linkedSceneIds', 'linkedWorldItemIds', 'tags'],
        optional: [
          'time',
          'importance',
          'colorToken',
          'globalOrderIndex',
          'chapterNumber',
          'sourceChunkIds',
          'sourceOrder',
          // position, sharedBranchIds, layoutLock, modalStateHints removed — runtime-only
        ],
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

const jsonText = (payload: unknown) => JSON.stringify(payload, null, 2);

const packageCanonicalSnapshot = (project: NarrativeProject) => {
  const files = new Map<string, string>();
  files.set('project.json', jsonText({
    metadata: project.metadata,
    counts: {
      characters: project.characters.length, timelineBranches: project.timelineBranches.length,
      timelineEvents: project.timelineEvents.length, scenes: project.scenes.length,
      worldItems: project.worldItems.length, scripts: project.scripts.length,
      storyboards: project.storyboards.length, importJobs: project.importJobs.length,
      proposals: project.proposals.length, exports: project.exports.length,
    },
  }));
  project.characters.forEach((item) => files.set(`entities/characters/${item.id}.json`, jsonText(item)));
  files.set('entities/character-tags.json', jsonText(project.characterTags));
  files.set('entities/candidates.json', jsonText(project.candidates));
  files.set('entities/relationships.json', jsonText(project.relationships));
  files.set('entities/timeline/branches.json', jsonText(project.timelineBranches));
  project.timelineEvents.forEach((item) => files.set(`entities/timeline/${item.id}.json`, jsonText(item)));
  files.set('entities/world/containers.json', jsonText(project.worldContainers));
  files.set('entities/world/settings.json', jsonText(project.worldSettings));
  files.set('entities/world/maps.json', jsonText(project.worldMaps));
  files.set('entities/world/categories.json', jsonText(project.worldCategories ?? []));
  project.worldItems.forEach((item) => files.set(`entities/world/${item.id}.json`, jsonText(item)));
  project.chapters.forEach((item) => files.set(`writing/chapters/${item.id}.json`, jsonText(item)));
  project.scenes.forEach((item) => {
    files.set(`writing/scenes/${item.id}.md`, item.content);
    files.set(`writing/scenes/${item.id}.meta.json`, jsonText({ ...item, content: undefined }));
  });
  files.set('writing/manuscript/nodes.json', jsonText(project.manuscriptNodes || []));
  files.set('system/inbox.json', jsonText(project.proposals));
  files.set('system/history.json', jsonText(project.proposalHistory));
  files.set('system/issues.json', jsonText(project.issues));
  files.set('system/index-cache.json', jsonText({ unreadUpdates: project.unreadUpdates, archivedIds: project.archivedIds }));
  return files;
};

const ownedWritingTombstones = (
  fs: typeof import('fs'),
  rootPath: string,
  snapshot: Map<string, string>,
) => {
  const namespaces = [
    { relativeDirectory: 'writing/chapters', pattern: /^([^/]+)\.json$/ },
    { relativeDirectory: 'writing/scenes', pattern: /^([^/]+)\.(?:md|meta\.json)$/ },
  ];
  const tombstones = new Set<string>();
  for (const { relativeDirectory, pattern } of namespaces) {
    const directory = `${rootPath}/${relativeDirectory}`;
    if (!fs.existsSync(directory)) continue;
    for (const fileName of fs.readdirSync(directory)) {
      if (!pattern.test(fileName)) continue;
      const relativePath = `${relativeDirectory}/${fileName}`;
      if (!snapshot.has(relativePath)) tombstones.add(relativePath);
    }
  }
  return tombstones;
};

const durablyCommitAcceptedImportPackage = async (before: NarrativeProject, after: NarrativeProject, proposals: Proposal[]): Promise<void> => {
  const runtime = getNodeRuntime();
  if (!runtime || after.metadata.rootPath.startsWith('memory://')) return;
  const runIds = uniqueStrings(proposals.flatMap(getImportRunIds));
  if (runIds.length !== 1 || !isSafeArtifactSegment(runIds[0])) throw new Error('Import package cannot be assigned a durable transaction id.');
  const beforeFiles = packageCanonicalSnapshot(before);
  const afterFiles = packageCanonicalSnapshot(after);
  const rootPath = runtime.path.resolve(after.metadata.rootPath);
  const targets: Parameters<typeof commitProjectTransaction>[3] = Array.from(new Set([...beforeFiles.keys(), ...afterFiles.keys()]))
    .filter((relativePath) => beforeFiles.get(relativePath) !== afterFiles.get(relativePath))
    .map((relativePath) => {
      const postimage = afterFiles.get(relativePath);
      return postimage === undefined ? { relativePath, delete: true as const } : { relativePath, postimage };
    });
  for (const relativePath of ownedWritingTombstones(runtime.fs, rootPath, afterFiles)) {
    if (!targets.some((target) => target.relativePath === relativePath)) targets.push({ relativePath, delete: true });
  }
  if (!targets.length) return;
  await commitProjectTransaction(runtime.fs, rootPath, `package-${runIds[0]}`, targets);
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
    const usingProjectBridge = Boolean(electronApi.projectFiles());
    const rootPath = input.rootPath || (runtime && !usingProjectBridge ? getDefaultProjectDir(runtime, input.name) : fallbackRoot);
    const storageMode = runtime && !rootPath.startsWith('memory://') ? 'nodefs' : 'memory';
    const project = migrateProject(hydrateProjectMetadata(
      createProjectByTemplate(input.template, input.name, rootPath, input.locale, storageMode),
      rootPath,
      storageMode,
      input.locale
    ), rootPath, storageMode, input.locale);

    if (!runtime || storageMode === 'memory') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
      localStorage.setItem(LAST_PATH_KEY, project.metadata.rootPath);
      return project;
    }

    serializeProjectToFolder(project, runtime, rootPath);
    localStorage.setItem(LAST_PATH_KEY, rootPath);
    return project;
  },

  async openProject(rootPath?: string | null): Promise<NarrativeProject> {
    const runtime = getNodeRuntime();
    const usingProjectBridge = Boolean(electronApi.projectFiles());
    const resolvedPath = rootPath || (usingProjectBridge ? null : localStorage.getItem(LAST_PATH_KEY));

    if (!runtime || (usingProjectBridge && !resolvedPath)) {
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

    await recoverProjectTransactions(runtime.fs, runtime.path.resolve(resolvedPath));

    const projectIndex = JSON.parse(runtime.fs.readFileSync(runtime.path.join(resolvedPath, 'project.json'), 'utf8'));
    const entitiesDir = runtime.path.join(resolvedPath, 'entities');
    const timelineDir = runtime.path.join(entitiesDir, 'timeline');
    const worldDir = runtime.path.join(entitiesDir, 'world');
    const graphDir = runtime.path.join(entitiesDir, 'graph');
    const scriptsDir = runtime.path.join(entitiesDir, 'scripts');
    const storyboardsDir = runtime.path.join(entitiesDir, 'storyboards');
    const chaptersDir = runtime.path.join(resolvedPath, 'writing', 'chapters');
    const scenesDir = runtime.path.join(resolvedPath, 'writing', 'scenes');
    const manuscriptNodeDir = runtime.path.join(resolvedPath, 'writing', 'manuscript');
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
      timelineEvents: readJsonFilesSafe<NarrativeProject['timelineEvents'][number]>(runtime, timelineDir).filter((item) => item.id && !Array.isArray(item)),
      relationships: safeReadJson(runtime.fs, runtime.path.join(entitiesDir, 'relationships.json'), []),
      chapters: readJsonFilesSafe<NarrativeProject['chapters'][number]>(runtime, chaptersDir),
      scenes: sceneMetas.map((meta) => ({
        ...meta,
        content: safeReadText(runtime.fs, runtime.path.join(scenesDir, `${meta.id}.md`), ''),
      })),
      worldContainers: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'containers.json'), []),
      worldSettings: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'settings.json'), folderFallback.worldSettings),
      worldMaps: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'maps.json'), folderFallback.worldMaps),
      worldCategories: safeReadJson(runtime.fs, runtime.path.join(worldDir, 'categories.json'), []),
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
      manuscriptNodes: (() => {
        const raw = safeReadJson(runtime.fs, runtime.path.join(manuscriptNodeDir, 'nodes.json'), []);
        if (!Array.isArray(raw)) {
          console.warn('[openProject] nodes.json: expected array, got', typeof raw);
          return [];
        }
        const allowedTypes = new Set<ManuscriptNodeType>(['act', 'part', 'chapter_outline', 'scene_outline', 'note']);
        const seen = new Set<string>();
        return (raw as unknown[]).reduce<ManuscriptNode[]>((acc, n: unknown, i: number) => {
          const node = n as Record<string, unknown>;
          if (!node || typeof node !== 'object') return acc;
          const rawId = typeof node['id'] === 'string' ? node['id'] : '';
          const id = rawId || `mn_unknown_${i}`;
          if (seen.has(id)) return acc;
          seen.add(id);
          const rawType = node['type'] as string;
          const nodeType: ManuscriptNodeType = allowedTypes.has(rawType as ManuscriptNodeType)
            ? (rawType as ManuscriptNodeType)
            : 'note';
          acc.push({
            id,
            title: typeof node['title'] === 'string' ? node['title'] : '',
            type: nodeType,
            parentId: (node['parentId'] as string | null) ?? null,
            orderIndex: typeof node['orderIndex'] === 'number' ? (node['orderIndex'] as number) : 0,
            linkedChapterId: (node['linkedChapterId'] as string | null) ?? null,
            linkedSceneId: (node['linkedSceneId'] as string | null) ?? null,
            depth: typeof node['depth'] === 'number' ? (node['depth'] as number) : 0,
            collapsed: Boolean(node['collapsed']),
            wordCount: typeof node['wordCount'] === 'number' ? (node['wordCount'] as number) : 0,
          });
          return acc;
        }, []);
      })(),
      uiState: safeReadJson(runtime.fs, runtime.path.join(systemDir, 'ui-state.json'), undefined),
      ...safeReadJson(runtime.fs, runtime.path.join(systemDir, 'index-cache.json'), {
        unreadUpdates: { activities: {}, sections: {}, entities: {} },
        archivedIds: [],
      }),
    };

    localStorage.setItem(LAST_PATH_KEY, resolvedPath);
    const migratedBase = migrateProject(project, resolvedPath, 'nodefs', project.metadata.locale);
    const writingCollections = normalizeWritingCollections(migratedBase.chapters, migratedBase.scenes);
    const timelineCollections = normalizeTimelineCollections(migratedBase.timelineBranches, migratedBase.timelineEvents);
    const migrated = {
      ...migratedBase,
      ...writingCollections,
      ...timelineCollections,
    };
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
    const packageKey = getProposalPackageKey(target);
    if (nextStatus === 'accepted' && packageKey) {
      const blockedReason = `Proposal belongs to ${packageKey} and must be accepted through its complete package transaction.`;
      const annotatedProposal: Proposal = {
        ...target,
        lastBlockReason: blockedReason,
        lastBlockedAt: new Date().toISOString(),
      };
      return {
        ...project,
        proposals: project.proposals.map((proposal) => proposal.id === proposalId ? annotatedProposal : proposal),
        issues: upsertProposalBlockedIssue(project.issues, target, blockedReason),
        unreadUpdates: markProposalUnread(project.unreadUpdates, proposalId),
      };
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

  async resolveProposals(
    project: NarrativeProject,
    proposalIds: string[],
    nextStatus: Proposal['status'],
    acceptanceIntent: ProposalAcceptanceIntent = 'bulk',
  ): Promise<NarrativeProject> {
    const idSet = new Set(proposalIds);
    const targets = project.proposals.filter((proposal) => idSet.has(proposal.id));
    if (!targets.length) return project;
    if (nextStatus !== 'accepted') {
      return targets.reduce((draft, proposal) => projectService.resolveProposal(draft, proposal.id, nextStatus), project);
    }
    return await applyImportPackageBatches(project, targets, acceptanceIntent);
  },

  async repairImportPackage(project: NarrativeProject, proposalIds: string[]): Promise<NarrativeProject> {
    const idSet = new Set(proposalIds);
    const proposals = project.proposals.filter((proposal) => idSet.has(proposal.id));
    if (!proposals.length || !proposals.some((proposal) => proposal.lastBlockReason)) return project;

    const repair = await repairLegacyProjectionDescriptors(project, proposals);
    if (repair.blockedReason) {
      return blockImportPackage(project, proposals, repair.culprit, repair.blockedReason);
    }

    const projectionValidation = await validateStagedManuscriptProjections(repair.project, repair.proposals);
    if (projectionValidation.blockedReason) {
      return blockImportPackage(project, proposals, projectionValidation.culprit, projectionValidation.blockedReason);
    }

    const repairedIds = new Set(repair.proposals.map((proposal) => proposal.id));
    return {
      ...repair.project,
      proposals: repair.project.proposals.map((proposal) => repairedIds.has(proposal.id)
        ? { ...proposal, lastBlockReason: undefined, lastBlockedAt: undefined }
        : proposal),
    };
  },

  async retryImportPackage(project: NarrativeProject, proposalIds: string[]): Promise<NarrativeProject> {
    const idSet = new Set(proposalIds);
    const selected = project.proposals.filter((proposal) => idSet.has(proposal.id));
    if (!selected.length) return project;
    const hasLegacyProjection = selected.some((proposal) =>
      getStagedManuscriptProjectionDescriptors(proposal).some((descriptor) =>
        descriptor.artifactRef === undefined && typeof descriptor.artifact_path === 'string'
      )
    );
    const repaired = hasLegacyProjection
      ? await projectService.repairImportPackage(project, proposalIds)
      : {
          ...project,
          proposals: project.proposals.map((proposal) => idSet.has(proposal.id)
            ? { ...proposal, lastBlockReason: undefined, lastBlockedAt: undefined }
            : proposal),
        };
    const retryTargets = repaired.proposals.filter((proposal) => idSet.has(proposal.id));
    if (!retryTargets.length || retryTargets.some((proposal) => proposal.lastBlockReason)) return repaired;

    // A retry is a fresh package transaction, never a partial continuation.
    // applyImportPackageBatches re-runs reference, duplicate-ID, SourceSpan,
    // projection, and durability checks before it makes any canonical write.
    return applyImportPackageBatches(repaired, retryTargets, 'bulk');
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

const normalizeImportedProposalEntity = (
  _project: NarrativeProject,
  proposal: Proposal,
  entityType: EntityKind,
  entity: Record<string, unknown>,
  _referenceSets?: ReferenceSets,
): Record<string, unknown> => {
  if (!importedProposalSource(proposal)) return entity;

  if (entityType === 'character') {
    return {
      ...entity,
      tagIds: uniqueStrings([entity.tagIds]),
      linkedSceneIds: uniqueStrings([entity.linkedSceneIds]),
      linkedEventIds: uniqueStrings([entity.linkedEventIds]),
      linkedWorldItemIds: uniqueStrings([entity.linkedWorldItemIds]),
    };
  }
  return entity;
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
  parentBranchId: 'parent branch',
  forkEventId: 'fork event',
  mergeEventId: 'merge event',
  mergeTargetBranchId: 'merge target branch',
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
  sharedBranchIds: 'shared branch',
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
  for (const anchorKey of ['startAnchor', 'endAnchor']) {
    const anchor = fields[anchorKey];
    if (anchor && typeof anchor === 'object') {
      const eventId = (anchor as Record<string, unknown>).eventId;
      if (typeof eventId === 'string' && eventId) refs.push({ id: eventId, label: `${anchorKey} event` });
    }
  }
  return refs;
};

export const buildDependencyGraph = (proposals: Proposal[]): DependencyEdge[] => {
  const createdBy = new Map<string, Set<string>>();
  proposals.forEach((proposal) => {
    const ops = getProposalOperations(proposal);
    ops.forEach((op) => {
      if (op.op !== 'create') return;
      const entityType = op.entityType as EntityKind | undefined;
      if (!entityType) return;
      const entityId = operationEntityId(proposal, op, entityType);
      if (!entityId) return;
      createdBy.set(entityId, new Set([...(createdBy.get(entityId) || []), proposal.id]));
    });
    // Fall back to targetEntityId for proposals with no explicit create op
    if (proposal.targetEntityId && !ops.length) {
      createdBy.set(proposal.targetEntityId, new Set([...(createdBy.get(proposal.targetEntityId) || []), proposal.id]));
    }
  });

  const edges: DependencyEdge[] = [];
  const seen = new Set<string>();
  const addEdge = (creator: string, consumer: string, reason: string) => {
    if (creator === consumer) return;
    const edgeKey = `${creator}|${consumer}|${reason}`;
    if (seen.has(edgeKey)) return;
    seen.add(edgeKey);
    edges.push({ fromId: creator, toId: consumer, reason });
  };
  proposals.forEach((proposal) => {
    getProposalOperations(proposal).forEach((op) => {
      if (op.op !== 'create') {
        const entityType = op.entityType as EntityKind | undefined;
        if (entityType) {
          const targetId = operationEntityId(proposal, op, entityType);
          const producers = createdBy.get(targetId);
          if (producers?.size === 1) addEdge([...producers][0], proposal.id, `${op.op} target`);
        }
      }
      if (!op.fields) return;
      extractIdRefs(op.fields as Record<string, unknown>).forEach(({ id, label }) => {
        const producers = createdBy.get(id);
        if (producers?.size === 1) addEdge([...producers][0], proposal.id, `${label} referenced`);
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

const pendingPackageProposals = (project: NarrativeProject, packageKey: string) =>
  project.proposals.filter((proposal) =>
    (proposal.status === 'pending' || !proposal.status)
    && getProposalPackageKey(proposal) === packageKey
  );

const proposalScopedId = (proposal: Proposal, entityType: string) =>
  `${entityType}_${proposal.id.replace(/^proposal_/, '').replace(/[^a-zA-Z0-9_]+/g, '_')}`;

const operationEntityId = (proposal: Proposal, operation: RawProposalOperation, entityType: EntityKind) =>
  String(operation.entityId || operation.fields?.id || proposal.targetEntityId || proposalScopedId(proposal, entityType));

const proposalPriority = (proposal: Proposal) => {
  const entityType = getProposalOperations(proposal)[0]?.entityType as EntityKind | undefined;
  return proposalApplyPriority[entityType || 'proposal'] ?? 99;
};

const stableProposalOrder = (a: Proposal, b: Proposal) =>
  proposalPriority(a) - proposalPriority(b) || a.id.localeCompare(b.id);

const orderPackageProposals = (proposals: Proposal[]): Proposal[] => {
  const ids = new Set(proposals.map((proposal) => proposal.id));
  const compiled = proposals.map((proposal) => proposal.packageCompiler);
  const compiledIds = compiled[0]?.orderedProposalIds || [];
  const hasAuthoritativePlan =
    compiled.length === proposals.length
    && compiled.every((metadata, index) =>
      metadata?.contractVersion === 'w1-package-graph-v2'
      && metadata.proposalCount === proposals.length
      && metadata.orderedProposalIds.length === proposals.length
      && metadata.orderedProposalIds.every((id) => ids.has(id))
      && metadata.orderedProposalIds.join('\u0000') === compiledIds.join('\u0000')
      && metadata.order === compiledIds.indexOf(proposals[index].id)
    )
    && new Set(compiledIds).size === proposals.length;
  if (hasAuthoritativePlan) {
    const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
    return compiledIds.map((id) => byId.get(id)!).filter(Boolean);
  }

  // Compatibility compiler for packages created before package-graph-v2. The
  // persisted Python plan remains authoritative for every newly written W1
  // package; this fallback prevents legacy updates from running before their
  // same-package create producer.
  const edges = buildDependencyGraph(proposals);
  const outgoing = new Map<string, Set<string>>();
  const indegree = new Map(proposals.map((proposal) => [proposal.id, 0]));
  for (const edge of edges) {
    if (!ids.has(edge.fromId) || !ids.has(edge.toId) || edge.fromId === edge.toId) continue;
    const consumers = outgoing.get(edge.fromId) || new Set<string>();
    if (consumers.has(edge.toId)) continue;
    consumers.add(edge.toId);
    outgoing.set(edge.fromId, consumers);
    indegree.set(edge.toId, (indegree.get(edge.toId) || 0) + 1);
  }
  const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  const ready = proposals.filter((proposal) => indegree.get(proposal.id) === 0).sort(stableProposalOrder);
  const ordered: Proposal[] = [];
  while (ready.length) {
    const proposal = ready.shift()!;
    ordered.push(proposal);
    for (const consumerId of outgoing.get(proposal.id) || []) {
      const next = (indegree.get(consumerId) || 0) - 1;
      indegree.set(consumerId, next);
      if (next === 0) {
        ready.push(byId.get(consumerId)!);
        ready.sort(stableProposalOrder);
      }
    }
  }
  if (ordered.length < proposals.length) {
    const emitted = new Set(ordered.map((proposal) => proposal.id));
    ordered.push(...proposals.filter((proposal) => !emitted.has(proposal.id)).sort(stableProposalOrder));
  }
  return ordered;
};

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
      if (!entityType || operation.op !== 'create') return;
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
  const importsWritingTree = proposals.some((proposal) => getProposalOperations(proposal).some(
    (operation) => operation.op === 'create' && operation.entityType === 'chapter',
  ));
  // This exact pair is generated only by the blank/starter project template.  Do
  // not infer emptiness from a missing body alone: an author may intentionally
  // keep a short chapter or a placeholder scene in a real project.
  const hasOnlyStarterWriting =
    importsWritingTree &&
    ['blank', 'starter-demo'].includes(draft.metadata.template || '') &&
    draft.chapters.length === 1 &&
    draft.scenes.length === 1 &&
    isBlankStarterChapter(draft.chapters[0], draft.scenes);
  if (hasOnlyStarterWriting) {
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

const applyImportPackageBatches = async (
  project: NarrativeProject,
  targets: Proposal[],
  acceptanceIntent: ProposalAcceptanceIntent,
): Promise<NarrativeProject> => {
  const selectedIds = new Set(targets.map((proposal) => proposal.id));
  const packageKeys = uniqueStrings(targets.map(getProposalPackageKey));
  const packageGroups: Proposal[][] = [];
  for (const packageKey of packageKeys) {
    const completePackage = pendingPackageProposals(project, packageKey);
    const missing = completePackage.filter((proposal) => !selectedIds.has(proposal.id));
    if (missing.length) {
      const culprit = targets.find((proposal) => getProposalPackageKey(proposal) === packageKey) || completePackage[0];
      return blockImportPackage(
        project,
        completePackage,
        culprit,
        `Package selection is incomplete; missing proposals: ${missing.map((proposal) => proposal.id).join(', ')}.`,
      );
    }
    packageGroups.push(completePackage);
  }
  const nonPackageTargets = targets.filter((proposal) => !getProposalPackageKey(proposal));

  // Validate every selected package before applying the first one. A semantic
  // warning is a human decision for exactly one complete package, never a
  // cross-package or mixed bulk operation.
  const semanticChecks = await Promise.all(packageGroups.map(async (group) => ({
    group,
    validation: await validateSemanticCoveragePackage(project, group),
  })));
  const invalidSemanticCheck = semanticChecks.find(({ validation }) => validation.blockedReason);
  if (invalidSemanticCheck?.validation.blockedReason) {
    return blockImportPackage(
      project,
      invalidSemanticCheck.group,
      invalidSemanticCheck.validation.culprit,
      invalidSemanticCheck.validation.blockedReason,
    );
  }
  const warningSemanticCheck = semanticChecks.find(({ validation }) => validation.ref?.verdict === 'warning');
  if (warningSemanticCheck && (
    acceptanceIntent !== 'manual_package'
    || packageGroups.length !== 1
    || nonPackageTargets.length > 0
  )) {
    return blockImportPackage(
      project,
      warningSemanticCheck.group,
      warningSemanticCheck.validation.culprit,
      'W1 semantic coverage warning requires an explicit acceptance of this one complete package; bulk acceptance is blocked.',
    );
  }

  let draft = project;
  for (const group of packageGroups) draft = await applyProposalPackageTransaction(draft, group);

  return nonPackageTargets.length ? applyProposalBatch(draft, nonPackageTargets) : draft;
};

const validateProposalPackageOperations = (project: NarrativeProject, proposals: Proposal[]): ProposalApplyResult & { culprit: Proposal } => {
  const preparedProject = prepareProjectForImportApply(project, proposals);
  const references = collectReferenceSets(preparedProject, proposals);
  const sorted = orderPackageProposals(proposals);
  let draft = preparedProject;
  for (const proposal of sorted) {
    const result = applyProposalOperations(draft, proposal, references);
    if (result.blockedReason) return { ...result, culprit: proposal };
    draft = result.project;
  }
  return { project: draft, applied: true, blockedReason: null, culprit: proposals[0] };
};

const applyProposalPackageTransaction = async (project: NarrativeProject, proposals: Proposal[]): Promise<NarrativeProject> => {
  const initialOperationValidation = validateProposalPackageOperations(project, proposals);
  if (initialOperationValidation.blockedReason) {
    return blockImportPackage(project, proposals, initialOperationValidation.culprit, initialOperationValidation.blockedReason);
  }
  const semanticValidation = await validateSemanticCoveragePackage(project, proposals);
  if (semanticValidation.blockedReason) {
    return blockImportPackage(project, proposals, semanticValidation.culprit, semanticValidation.blockedReason);
  }
  const projectionValidation = await validateStagedManuscriptProjections(project, proposals);
  if (projectionValidation.blockedReason) {
    return blockImportPackage(project, proposals, projectionValidation.culprit, projectionValidation.blockedReason);
  }

  const preparedProject = prepareProjectForImportApply(project, proposals);
  const references = collectReferenceSets(preparedProject, proposals);
  const sorted = orderPackageProposals(proposals);

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

  const projectionResult = await applyStagedManuscriptProjections(draft, proposals);
  if (projectionResult.blockedReason) {
    return blockImportPackage(project, proposals, projectionResult.culprit, projectionResult.blockedReason);
  }

  const finalized = finalizeAcceptedProposalBatch(project, projectionResult.project, accepted);
  try {
    await durablyCommitAcceptedImportPackage(project, finalized, proposals);
    return finalized;
  } catch (error) {
    try {
      const runtime = getNodeRuntime();
      if (runtime && !project.metadata.rootPath.startsWith('memory://')) await recoverProjectTransactions(runtime.fs, runtime.path.resolve(project.metadata.rootPath));
    } catch { /* Recovery is best-effort; the next project open retries it. */ }
    return blockImportPackage(project, proposals, proposals[0], `Package durability transaction failed: ${String(error)}`);
  }
};

type StagedManuscriptProjectionDescriptor = {
  artifact_path?: unknown;
  artifactRef?: unknown;
  contract_version?: unknown;
  chapter_id?: unknown;
  scene_id?: unknown;
};

type StagedManuscriptProjectionArtifact = {
  contract_version?: unknown;
  import_run_id?: unknown;
  source_file_path?: unknown;
  source_ref?: unknown;
  acceptance_required?: unknown;
  chapters?: unknown;
  nodes?: unknown;
  scene_documents?: unknown;
};

type ProjectionApplyResult = {
  project: NarrativeProject;
  culprit: Proposal;
  blockedReason: string | null;
};

const getStagedManuscriptProjectionDescriptor = (proposal: Proposal): StagedManuscriptProjectionDescriptor | null => {
  const projection = getProposalOperations(proposal)
    .map((operation) => operation.fields?.stagedManuscriptProjection)
    .find((value) => value && typeof value === 'object')
    ?? proposal.data?.stagedManuscriptProjection;
  return projection && typeof projection === 'object' ? projection as StagedManuscriptProjectionDescriptor : null;
};

const getStagedManuscriptProjectionDescriptors = (proposal: Proposal): StagedManuscriptProjectionDescriptor[] => {
  const legacyProposal = proposal as Proposal & { operations?: RawProposalOperation[] };
  return [
    ...(legacyProposal.operations || []),
    ...(proposal.proposedOperations || []),
  ]
    .map((operation) => operation.fields?.stagedManuscriptProjection)
    .filter((value): value is StagedManuscriptProjectionDescriptor => Boolean(value && typeof value === 'object'));
};

type ProjectionRepairResult = {
  project: NarrativeProject;
  proposals: Proposal[];
  culprit: Proposal;
  blockedReason: string | null;
};

const repairLegacyProjectionDescriptors = async (project: NarrativeProject, proposals: Proposal[]): Promise<ProjectionRepairResult> => {
  const fail = (culprit: Proposal, blockedReason: string): ProjectionRepairResult => ({ project, proposals, culprit, blockedReason });
  const success = (nextProject: NarrativeProject, nextProposals: Proposal[]): ProjectionRepairResult => ({
    project: nextProject,
    proposals: nextProposals,
    culprit: nextProposals[0] || proposals[0],
    blockedReason: null,
  });
  const runtime = getNodeRuntime();
  if (!runtime || project.metadata.rootPath.startsWith('memory://')) return fail(proposals[0], 'Legacy projection repair requires a local project filesystem.');
  const runIds = uniqueStrings(proposals.flatMap(getImportRunIds));
  if (runIds.length !== 1) return fail(proposals[0], 'Import package has conflicting or missing importRunId values.');
  const runId = runIds[0];
  if (!isSafeArtifactSegment(runId)) return fail(proposals[0], 'Import package has an invalid importRunId.');
  const projectRoot = runtime.path.resolve(project.metadata.rootPath);
  const runDirectory = runtime.path.resolve(projectRoot, 'system', 'imports', runId);
  const legacy = proposals.flatMap((proposal) => getStagedManuscriptProjectionDescriptors(proposal)
    .filter((descriptor) => descriptor.artifactRef === undefined && typeof descriptor.artifact_path === 'string')
    .map((descriptor) => ({ proposal, descriptor })));
  if (!legacy.length) return fail(proposals[0], 'Package is blocked, but does not contain a repairable legacy projection descriptor.');
  try {
    const legacyPaths = uniqueStrings(legacy.map(({ descriptor }) => descriptor.artifact_path));
    const containedCandidates = legacyPaths
      .map((path) => runtime.path.resolve(path))
      .filter((path) =>
        isPathInside(runtime.path, runDirectory, path)
        && path.endsWith(`${runtime.path.sep}staged_manuscript_projection.json`)
        && runtime.fs.existsSync(path)
      );
    const relocatedCandidates = new Set<string>();
    relocatedCandidates.add(runtime.path.resolve(runDirectory, 'staged_manuscript_projection.json'));
    for (const legacyPath of legacyPaths) {
      const normalized = legacyPath.replaceAll('\\', '/');
      const attempt = normalized.match(/\/attempts\/([^/]+)\/staged_manuscript_projection\.json$/)?.[1];
      if (attempt && isSafeArtifactSegment(attempt)) {
        relocatedCandidates.add(runtime.path.resolve(runDirectory, 'attempts', attempt, 'staged_manuscript_projection.json'));
      }
    }
    const candidates = uniqueStrings(containedCandidates.length ? containedCandidates : [...relocatedCandidates])
      .filter((path) => runtime.fs.existsSync(path));
    if (candidates.length !== 1) {
      return fail(
        legacy[0].proposal,
        candidates.length
          ? 'Legacy projection repair found multiple possible staged artifacts; manual selection is required.'
          : 'Legacy projection repair is missing its staged artifact, manifest, or source file.',
      );
    }
    const artifactPath = candidates[0];
    const artifactDirectory = runtime.path.dirname(artifactPath);
    const manifestPath = runtime.path.resolve(artifactDirectory, 'manifest.json');
    const sourcePath = runtime.path.resolve(artifactDirectory, 'raw_source.txt');
    if (![artifactPath, manifestPath, sourcePath].every((path) => runtime.fs.existsSync(path))) return fail(legacy[0].proposal, 'Legacy projection repair is missing its staged artifact, manifest, or source file.');
    if ([artifactPath, manifestPath, sourcePath].some((path) => runtime.fs.realpathSync(path) !== path)) return fail(legacy[0].proposal, 'Legacy projection repair rejected a symlinked artifact or source file.');
    const artifactRelativeToRun = runtime.path.relative(runDirectory, artifactPath).split(runtime.path.sep).join('/');
    const attemptMatch = artifactRelativeToRun.match(/^attempts\/([^/]+)\/staged_manuscript_projection\.json$/);
    const attemptId = artifactRelativeToRun === 'staged_manuscript_projection.json'
      ? 'legacy'
      : attemptMatch?.[1];
    if (!attemptId || !isSafeArtifactSegment(attemptId)) {
      return fail(legacy[0].proposal, 'Legacy projection artifact is not in a supported import-run or attempt directory.');
    }
    const artifactRelativePath = runtime.path.relative(projectRoot, artifactPath).split(runtime.path.sep).join('/');
    const sourceRelativePath = runtime.path.relative(projectRoot, sourcePath).split(runtime.path.sep).join('/');
    const artifactText = runtime.fs.readFileSync(artifactPath, 'utf8');
    const artifact = JSON.parse(artifactText) as Record<string, unknown>;
    const manifest = JSON.parse(runtime.fs.readFileSync(manifestPath, 'utf8')) as Record<string, unknown>;
    const raw = runtime.fs.readFileSync(sourcePath, 'utf8');
    const sourceHash = await sha256Text(raw);
    if (
      artifact.import_run_id !== runId || manifest.import_run_id !== runId || sourceHash !== manifest.source_hash
      || artifact.acceptance_required !== true || !Array.isArray(artifact.chapters)
      || !Array.isArray(artifact.nodes) || !Array.isArray(artifact.scene_documents)
    ) return fail(legacy[0].proposal, 'Legacy projection artifact or source manifest failed validation.');
    const descriptorPairs = new Set(legacy.map(({ descriptor }) => projectionPairKey(String(descriptor.chapter_id || ''), String(descriptor.scene_id || ''))));
    const pairs = new Set<string>();
    const sourceByScene = new Map<string, string>();
    for (const rawChapter of artifact.chapters as Record<string, unknown>[]) {
      const pair = projectionPairKey(String(rawChapter.chapter_id || ''), String(rawChapter.scene_id || ''));
      const reconstructed = await reconstructProjectionSourceSpan(rawChapter.source_span, raw, sourceHash);
      if (!descriptorPairs.has(pair) || pairs.has(pair) || reconstructed.error) return fail(legacy[0].proposal, 'Legacy projection chapters do not match their source descriptors.');
      pairs.add(pair);
      sourceByScene.set(String(rawChapter.scene_id || ''), reconstructed.content);
    }
    if (pairs.size !== descriptorPairs.size) return fail(legacy[0].proposal, 'Legacy projection chapters do not exactly match their source descriptors.');
    const documentScenes = new Set<string>();
    for (const rawDocument of artifact.scene_documents as Record<string, unknown>[]) {
      const sceneId = String(rawDocument.scene_id || '');
      const reconstructed = await reconstructProjectionSourceSpan(rawDocument.source_span, raw, sourceHash);
      if (!sourceByScene.has(sceneId) || documentScenes.has(sceneId) || reconstructed.error || rawDocument.content !== reconstructed.content) return fail(legacy[0].proposal, 'Legacy projection scene documents do not match the verified source.');
      documentScenes.add(sceneId);
    }
    if (documentScenes.size !== sourceByScene.size) return fail(legacy[0].proposal, 'Legacy projection scene documents do not exactly match the staged chapters.');
    const sourceRef: ArtifactRef = {
      relativePath: sourceRelativePath, sha256: sourceHash,
      contractVersion: 'w1-raw-source-v1', lineageId: runId, attemptId,
    };
    const rewrittenArtifact = { ...artifact, source_file_path: undefined, source_ref: sourceRef };
    const replacementText = JSON.stringify(rewrittenArtifact, null, 2);
    const ref: ArtifactRef = { relativePath: artifactRelativePath, sha256: await sha256Text(replacementText), contractVersion: 'w1-staged-manuscript-v2', lineageId: runId, attemptId };
    await commitProjectTransaction(runtime.fs, projectRoot, `repair-package-${runId}-${attemptId}`, [{
      relativePath: artifactRelativePath,
      postimage: replacementText,
    }]);
    const legacyIds = new Set(legacy.map(({ proposal }) => proposal.id));
    const migrateOperations = (operations: RawProposalOperation[] | undefined) => operations?.map((operation) => ({
      ...operation,
      fields: operation.fields?.stagedManuscriptProjection ? {
        ...operation.fields,
        stagedManuscriptProjection: {
          ...(operation.fields.stagedManuscriptProjection as object),
          // ArtifactRef v2 is the sole path authority after repair; do not retain
          // the absolute path from any legacy descriptor shape.
          artifact_path: undefined,
          artifactRef: ref,
          contract_version: 'w1-staged-manuscript-v2',
        },
      } : operation.fields,
    })).map((operation) => {
      const descriptor = operation.fields?.stagedManuscriptProjection as Record<string, unknown> | undefined;
      if (!descriptor || !Object.hasOwn(descriptor, 'artifact_path')) return operation;
      const { artifact_path: _legacyArtifactPath, ...withoutLegacyPath } = descriptor;
      return {
        ...operation,
        fields: { ...operation.fields, stagedManuscriptProjection: withoutLegacyPath },
      };
    });
    const nextProject = {
      ...project,
      proposals: project.proposals.map((proposal) => {
        if (!legacyIds.has(proposal.id)) return proposal;
        const legacyProposal = proposal as Proposal & { operations?: RawProposalOperation[] };
        return {
          ...proposal,
          ...(legacyProposal.operations ? { operations: migrateOperations(legacyProposal.operations) } : {}),
          proposedOperations: migrateOperations(proposal.proposedOperations),
        };
      }),
    };
    return success(nextProject, nextProject.proposals.filter((proposal) => proposals.some((target) => target.id === proposal.id)));
  } catch (error) {
    return fail(legacy[0].proposal, `Legacy projection repair transaction failed: ${String(error)}`);
  }
};

const projectionBlockedResult = (project: NarrativeProject, culprit: Proposal, blockedReason: string): ProjectionApplyResult => ({
  project,
  culprit,
  blockedReason,
});

const isPathInside = (path: typeof import('path'), directory: string, filePath: string) => {
  const relative = path.relative(directory, filePath);
  return relative && !relative.startsWith('..') && !path.isAbsolute(relative);
};

const getImportRunIds = (proposal: Proposal) => uniqueStrings([
  rawProposalValue(proposal, 'importRunId'),
  rawProposalValue(proposal, 'import_run_id'),
  rawProposalValue(proposal, 'packageId'),
  rawProposalValue(proposal, 'importPackageId'),
  ...getProposalOperations(proposal).map((operation) => operation.fields?.importRunId || operation.fields?.import_run_id),
]);

const projectionPairKey = (chapterId: string, sceneId: string) => `${chapterId}\u0000${sceneId}`;

const isArtifactRef = (value: unknown): value is ArtifactRef => {
  if (!value || typeof value !== 'object') return false;
  const ref = value as Record<string, unknown>;
  return typeof ref.relativePath === 'string'
    && typeof ref.sha256 === 'string'
    && typeof ref.contractVersion === 'string'
    && typeof ref.lineageId === 'string'
    && typeof ref.attemptId === 'string';
};

const isSafeArtifactSegment = (value: string) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value)
  && value !== '.' && value !== '..';

type SemanticCoverageValidation = {
  policy: SemanticCoveragePolicy | null;
  ref: SemanticCoverageRef | null;
  culprit: Proposal;
  blockedReason: string | null;
};

const semanticCoverageRefKey = (ref: SemanticCoverageRef) => [
  ref.relativePath,
  ref.sha256,
  ref.verdict,
  ref.input_hash,
  ref.attempt_id,
].join('\u0000');

const isSemanticCoverageRef = (value: unknown): value is SemanticCoverageRef => {
  if (!value || typeof value !== 'object') return false;
  const ref = value as Record<string, unknown>;
  return typeof ref.relativePath === 'string'
    && typeof ref.sha256 === 'string'
    && (ref.verdict === 'pass' || ref.verdict === 'warning' || ref.verdict === 'blocked')
    && typeof ref.input_hash === 'string'
    && typeof ref.attempt_id === 'string';
};

const isProjectRootRelativeArtifactPath = (value: string) => {
  if (!value || value.includes('\\') || value.startsWith('/') || value.startsWith('\\')) return false;
  if (/^[A-Za-z]:[\\/]/.test(value)) return false;
  return value.split('/').every((segment) => segment && segment !== '.' && segment !== '..');
};

const semanticPolicyFrom = (value: unknown): SemanticCoveragePolicy | null => {
  if (!value || typeof value !== 'object') return null;
  const policy = value as SemanticCoveragePolicy;
  return policy.verdict === 'pass' || policy.verdict === 'warning' || policy.verdict === 'blocked'
    ? policy
    : null;
};

const semanticCoverageEntries = (proposal: Proposal) => {
  const operations = getProposalOperations(proposal);
  return {
    proposalRef: proposal.semanticCoverageRef,
    proposalPolicy: proposal.semanticCoverage,
    operationRefs: operations.map((operation) => operation.semanticCoverageRef),
    operationPolicies: operations.map((operation) => operation.semanticCoverage).filter((policy) => policy !== undefined),
    operations,
  };
};

const validateSemanticCoveragePackage = async (
  project: NarrativeProject,
  proposals: Proposal[],
): Promise<SemanticCoverageValidation> => {
  const culprit = proposals[0];
  const metadataPresent = proposals.some((proposal) => {
    const entries = semanticCoverageEntries(proposal);
    return entries.proposalRef !== undefined
      || entries.proposalPolicy !== undefined
      || entries.operationRefs.some((entry) => entry !== undefined)
      || entries.operationPolicies.length > 0;
  });
  if (!metadataPresent) return { policy: null, ref: null, culprit, blockedReason: null };

  const refs: SemanticCoverageRef[] = [];
  const policies: SemanticCoveragePolicy[] = [];
  for (const proposal of proposals) {
    const entries = semanticCoverageEntries(proposal);
    if (entries.proposalRef === undefined || entries.proposalPolicy === undefined) {
      return { policy: null, ref: null, culprit: proposal, blockedReason: 'W1 semantic coverage metadata is missing its immutable report reference or policy.' };
    }
    if (entries.operationRefs.length !== entries.operations.length || entries.operationRefs.some((ref) => ref === undefined)) {
      return { policy: null, ref: null, culprit: proposal, blockedReason: 'W1 semantic coverage reference must be present on every proposal operation in the package.' };
    }
    const rawProposalRefs: unknown[] = [entries.proposalRef, ...entries.operationRefs];
    const rawProposalPolicies: unknown[] = [entries.proposalPolicy, ...entries.operationPolicies];
    if (rawProposalRefs.some((ref) => !isSemanticCoverageRef(ref))) {
      return { policy: null, ref: null, culprit: proposal, blockedReason: 'W1 semantic coverage reference has an invalid shape.' };
    }
    if (rawProposalPolicies.some((policy) => !semanticPolicyFrom(policy))) {
      return { policy: null, ref: null, culprit: proposal, blockedReason: 'W1 semantic coverage policy has an invalid verdict.' };
    }
    const proposalRefs = rawProposalRefs.filter(isSemanticCoverageRef);
    const proposalPolicies = rawProposalPolicies.map(semanticPolicyFrom).filter((policy): policy is SemanticCoveragePolicy => policy !== null);
    refs.push(...proposalRefs);
    policies.push(...proposalPolicies);
  }

  const referenceKeys = new Set(refs.map(semanticCoverageRefKey));
  if (referenceKeys.size !== 1) {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage references disagree within this import package.' };
  }
  const policyVerdicts = new Set(policies.map((policy) => policy.verdict));
  const policyInputHashes = new Set(policies.map((policy) => String(policy.input_hash || '')));
  if (policyVerdicts.size !== 1 || policyInputHashes.size !== 1) {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage policies disagree within this import package.' };
  }

  const ref = refs[0];
  const policy = policies[0];
  if (
    !isProjectRootRelativeArtifactPath(ref.relativePath)
    || !isSafeArtifactSegment(ref.attempt_id)
    || !/^[a-f0-9]{64}$/i.test(ref.sha256)
    || !/^[a-f0-9]{64}$/i.test(ref.input_hash)
    || policy.verdict !== ref.verdict
    || String(policy.input_hash || '') !== ref.input_hash
    || (policy.ref !== undefined && (!isSemanticCoverageRef(policy.ref) || semanticCoverageRefKey(policy.ref) !== semanticCoverageRefKey(ref)))
  ) {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage policy and reference are inconsistent or unsafe.' };
  }

  const importRunIds = uniqueStrings(proposals.flatMap(getImportRunIds));
  if (importRunIds.length !== 1 || !isSafeArtifactSegment(importRunIds[0])) {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage validation requires one safe importRunId for the package.' };
  }
  const runtime = getNodeRuntime();
  if (!runtime || project.metadata.rootPath.startsWith('memory://') || typeof runtime.fs.realpathSync !== 'function') {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage validation requires a realpath-capable local project filesystem.' };
  }

  const projectRoot = runtime.path.resolve(project.metadata.rootPath);
  const reportPath = runtime.path.resolve(projectRoot, ref.relativePath);
  if (!isPathInside(runtime.path, projectRoot, reportPath) || !runtime.fs.existsSync(reportPath)) {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage report is not a project-root-contained artifact.' };
  }
  try {
    const resolvedProjectRoot = runtime.fs.realpathSync(projectRoot);
    const resolvedReportPath = runtime.fs.realpathSync(reportPath);
    if (resolvedProjectRoot !== projectRoot || resolvedReportPath !== reportPath || !isPathInside(runtime.path, resolvedProjectRoot, resolvedReportPath)) {
      return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage report resolves through a symlink or outside the project root.' };
    }
    const reportText = runtime.fs.readFileSync(reportPath, 'utf8');
    if ((await sha256Text(reportText)) !== ref.sha256) {
      return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage report hash does not match its reference.' };
    }
    const report = JSON.parse(reportText) as Record<string, unknown>;
    const expectedRelativePath = `system/imports/${importRunIds[0]}/attempts/${ref.attempt_id}/semantic_coverage_report.json`;
    const artifactPaths = report.artifact_paths as Record<string, unknown> | undefined;
    if (
      report.contract_version !== 'w1-semantic-coverage-report/v1'
      || report.import_run_id !== importRunIds[0]
      || report.lineage_id !== importRunIds[0]
      || report.attempt_id !== ref.attempt_id
      || report.input_hash !== ref.input_hash
      || report.verdict !== ref.verdict
      || ref.relativePath !== expectedRelativePath
      || artifactPaths?.report !== ref.relativePath
      || (typeof policy.report_path === 'string' && policy.report_path && policy.report_path !== ref.relativePath)
    ) {
      return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage report does not match this package, attempt, or immutable reference.' };
    }
  } catch {
    return { policy: null, ref: null, culprit, blockedReason: 'W1 semantic coverage report is unreadable.' };
  }

  if (ref.verdict === 'blocked') {
    return { policy, ref, culprit, blockedReason: 'W1 semantic coverage report is blocked; this package cannot be accepted.' };
  }
  if (ref.verdict === 'warning' && (policy.requires_human_review !== true || policy.automatic_acceptance === true)) {
    return { policy, ref, culprit, blockedReason: 'W1 semantic coverage warning is missing its required human-review policy.' };
  }
  return { policy, ref, culprit, blockedReason: null };
};

const resolveProjectionArtifactPath = (
  runtime: NodeRuntime,
  importsDirectory: string,
  importRunId: string,
  descriptor: StagedManuscriptProjectionDescriptor,
): { path: string | null; directory: string | null; blockedReason: string | null; artifactRef: ArtifactRef | null } => {
  const ref = descriptor.artifactRef;
  if (ref !== undefined) {
    if (!isArtifactRef(ref)) return { path: null, directory: null, artifactRef: null, blockedReason: 'Invalid ArtifactRef for staged manuscript projection.' };
    if (
      ref.contractVersion !== 'w1-staged-manuscript-v2'
      || ref.lineageId !== importRunId
      || !isSafeArtifactSegment(ref.lineageId)
      || !isSafeArtifactSegment(ref.attemptId)
      || ref.relativePath.includes('\\')
      || ref.relativePath.split('/').some((segment) => !segment || segment === '.' || segment === '..')
    ) return { path: null, directory: null, artifactRef: null, blockedReason: 'ArtifactRef is not a contained import-run projection reference.' };
    const attemptRelativePath = `system/imports/${ref.lineageId}/attempts/${ref.attemptId}/staged_manuscript_projection.json`;
    const legacyRelativePath = `system/imports/${ref.lineageId}/staged_manuscript_projection.json`;
    const isLegacyDirect = ref.attemptId === 'legacy' && ref.relativePath === legacyRelativePath;
    if (ref.relativePath !== attemptRelativePath && !isLegacyDirect) {
      return { path: null, directory: null, artifactRef: null, blockedReason: 'ArtifactRef does not identify the expected staged manuscript projection.' };
    }
    const directory = isLegacyDirect
      ? runtime.path.resolve(importsDirectory, ref.lineageId)
      : runtime.path.resolve(importsDirectory, ref.lineageId, 'attempts', ref.attemptId);
    return { path: runtime.path.resolve(directory, 'staged_manuscript_projection.json'), directory, artifactRef: ref, blockedReason: null };
  }
  if (descriptor.contract_version !== 'w1-staged-manuscript-v1' || typeof descriptor.artifact_path !== 'string') {
    return { path: null, directory: null, artifactRef: null, blockedReason: 'Invalid staged manuscript projection descriptor.' };
  }
  const directory = runtime.path.resolve(importsDirectory, importRunId);
  return { path: runtime.path.resolve(descriptor.artifact_path), directory, artifactRef: null, blockedReason: null };
};

const resolveProjectionSourcePath = (
  runtime: NodeRuntime,
  projectRoot: string,
  artifactDirectory: string,
  artifact: StagedManuscriptProjectionArtifact,
  projectionRef: ArtifactRef | null,
): { path: string | null; sha256: string | null; blockedReason: string | null } => {
  if (artifact.source_ref !== undefined) {
    if (!isArtifactRef(artifact.source_ref)) return { path: null, sha256: null, blockedReason: 'Invalid staged manuscript source ArtifactRef.' };
    const ref = artifact.source_ref;
    if (
      ref.contractVersion !== 'w1-raw-source-v1'
      || !isSafeArtifactSegment(ref.lineageId) || !isSafeArtifactSegment(ref.attemptId)
      || ref.relativePath.includes('\\') || ref.relativePath.split('/').some((segment) => !segment || segment === '.' || segment === '..')
      || (projectionRef && (ref.lineageId !== projectionRef.lineageId || ref.attemptId !== projectionRef.attemptId))
    ) {
      return { path: null, sha256: null, blockedReason: 'Staged manuscript source ArtifactRef is not project-root-contained.' };
    }
    const sourcePath = runtime.path.resolve(projectRoot, ref.relativePath);
    if (sourcePath !== runtime.path.resolve(artifactDirectory, 'raw_source.txt') || !isPathInside(runtime.path, projectRoot, sourcePath)) {
      return { path: null, sha256: null, blockedReason: 'Staged manuscript source ArtifactRef must identify raw_source.txt beside its projection.' };
    }
    return { path: sourcePath, sha256: ref.sha256, blockedReason: null };
  }
  if (typeof artifact.source_file_path !== 'string' || !artifact.source_file_path) {
    return { path: null, sha256: null, blockedReason: 'Staged manuscript projection requires readable raw source evidence; browser-only acceptance is blocked.' };
  }
  return { path: runtime.path.resolve(artifact.source_file_path), sha256: null, blockedReason: null };
};

const reconstructProjectionSourceSpan = async (
  sourceSpan: unknown,
  rawSource: string,
  sourceHash: string,
): Promise<{ content: string; error: string | null }> => {
  if (!sourceSpan || typeof sourceSpan !== 'object') return { content: '', error: 'is missing SourceSpan evidence' };
  const span = sourceSpan as Record<string, unknown>;
  const start = span.absolute_start;
  const end = span.absolute_end;
  if (
    span.raw_source_hash !== sourceHash
    || typeof start !== 'number'
    || typeof end !== 'number'
    || !Number.isInteger(start)
    || !Number.isInteger(end)
    || start < 0
    || end < start
    || end > Array.from(rawSource).length
  ) return { content: '', error: 'has an invalid SourceSpan' };
  // Python SourceSpan offsets count Unicode code points; JS string slicing counts UTF-16 code units.
  const content = Array.from(rawSource).slice(start, end).join('');
  if (span.substring_hash !== await sha256Text(content)) return { content: '', error: 'has unverifiable SourceSpan evidence' };
  return { content, error: null };
};

const validateStagedManuscriptProjections = async (project: NarrativeProject, proposals: Proposal[]): Promise<ProjectionApplyResult> => {
  const descriptors = proposals
    .map((proposal) => ({ proposal, descriptor: getStagedManuscriptProjectionDescriptor(proposal) }))
    .filter((entry): entry is { proposal: Proposal; descriptor: StagedManuscriptProjectionDescriptor } => Boolean(entry.descriptor));
  if (!descriptors.length) return { project, culprit: proposals[0], blockedReason: null };

  const runtime = getNodeRuntime();
  const culprit = descriptors[0].proposal;
  if (!runtime || project.metadata.rootPath.startsWith('memory://')) {
    return projectionBlockedResult(project, culprit, 'Staged manuscript projection requires a local project filesystem.');
  }
  if (typeof runtime.fs.realpathSync !== 'function') {
    return projectionBlockedResult(project, culprit, 'Staged manuscript projection requires realpath-capable local filesystem semantics.');
  }

  const runIds = uniqueStrings(proposals.flatMap(getImportRunIds));
  if (runIds.length !== 1) {
    return projectionBlockedResult(project, culprit, `Import package has conflicting or missing importRunId values: ${runIds.join(', ') || 'none'}.`);
  }
  const importRunId = runIds[0];
  const projectRoot = runtime.path.resolve(project.metadata.rootPath);
  const importsDirectory = runtime.path.resolve(projectRoot, 'system', 'imports');

  const proposalChapterIds = new Set<string>();
  const proposalSceneToChapter = new Map<string, string>();
  for (const proposal of proposals) {
    for (const operation of getProposalOperations(proposal)) {
      const entityType = operation.entityType as EntityKind | undefined;
      if (entityType !== 'chapter' && entityType !== 'scene') continue;
      const id = operationEntityId(proposal, operation, entityType);
      if (entityType === 'chapter') {
        if (proposalChapterIds.has(id)) return projectionBlockedResult(project, proposal, `Import package contains duplicate chapter target: ${id}.`);
        proposalChapterIds.add(id);
      } else {
        const chapterId = operation.fields?.chapterId;
        if (typeof chapterId !== 'string' || !chapterId) return projectionBlockedResult(project, proposal, `Scene proposal ${id} is missing its chapter reference.`);
        if (proposalSceneToChapter.has(id)) return projectionBlockedResult(project, proposal, `Import package contains duplicate scene target: ${id}.`);
        proposalSceneToChapter.set(id, chapterId);
      }
    }
  }

  const descriptorPairs = new Set<string>();
  const artifactPairs = new Set<string>();
  const seenArtifacts = new Set<string>();
  for (const { proposal, descriptor } of descriptors) {
    if (
      typeof descriptor.chapter_id !== 'string'
      || typeof descriptor.scene_id !== 'string'
    ) return projectionBlockedResult(project, proposal, 'Invalid staged manuscript projection descriptor.');

    const pair = projectionPairKey(descriptor.chapter_id, descriptor.scene_id);
    descriptorPairs.add(pair);
    if (proposalSceneToChapter.get(descriptor.scene_id) !== descriptor.chapter_id || !proposalChapterIds.has(descriptor.chapter_id)) {
      return projectionBlockedResult(project, proposal, `Staged manuscript projection descriptor does not match package chapter/scene proposals: ${descriptor.chapter_id}/${descriptor.scene_id}.`);
    }
    if (project.scenes.some((scene) => scene.id === descriptor.scene_id) || project.chapters.some((chapter) => chapter.id === descriptor.chapter_id)) {
      return projectionBlockedResult(project, proposal, `Staged manuscript projection may not overwrite existing chapter or scene: ${descriptor.chapter_id}/${descriptor.scene_id}.`);
    }

    const artifactResolution = resolveProjectionArtifactPath(runtime, importsDirectory, importRunId, descriptor);
    if (artifactResolution.blockedReason || !artifactResolution.path) {
      return projectionBlockedResult(project, proposal, artifactResolution.blockedReason || 'Invalid staged manuscript projection descriptor.');
    }
    const artifactPath = artifactResolution.path;
    const artifactDirectory = artifactResolution.directory!;
    if (artifactPath !== runtime.path.resolve(artifactDirectory, 'staged_manuscript_projection.json')) {
      return projectionBlockedResult(project, proposal, 'Staged manuscript projection path is outside the expected import run.');
    }
    if (seenArtifacts.has(artifactPath)) continue;
    seenArtifacts.add(artifactPath);
    try {
      const resolvedRunDirectory = runtime.fs.realpathSync(artifactDirectory);
      if (resolvedRunDirectory !== artifactDirectory || !isPathInside(runtime.path, importsDirectory, resolvedRunDirectory)) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection run directory resolves through a symlink or outside its import run.');
      }
      const resolvedArtifactPath = runtime.fs.realpathSync(artifactPath);
      const manifestPath = runtime.path.resolve(artifactDirectory, 'manifest.json');
      const resolvedManifestPath = runtime.fs.realpathSync(manifestPath);
      if (
        resolvedArtifactPath !== artifactPath || !isPathInside(runtime.path, resolvedRunDirectory, resolvedArtifactPath)
        || resolvedManifestPath !== manifestPath || !isPathInside(runtime.path, resolvedRunDirectory, resolvedManifestPath)
      ) return projectionBlockedResult(project, proposal, 'Staged manuscript projection or manifest resolves through a symlink or outside its import run.');

      const manifest = JSON.parse(runtime.fs.readFileSync(manifestPath, 'utf8')) as Record<string, unknown>;
      const artifactText = runtime.fs.readFileSync(artifactPath, 'utf8');
      if (artifactResolution.artifactRef && (await sha256Text(artifactText)) !== artifactResolution.artifactRef.sha256) {
        return projectionBlockedResult(project, proposal, 'ArtifactRef hash does not match the staged manuscript projection.');
      }
      const artifact = JSON.parse(artifactText) as StagedManuscriptProjectionArtifact;
      const sourceHash = manifest.source_hash;
      if (manifest.import_run_id !== importRunId || artifact.import_run_id !== importRunId || typeof sourceHash !== 'string' || !sourceHash) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection package, importRunId, or source hash does not match its manifest.');
      }
      if (!Array.isArray(artifact.chapters) || !Array.isArray(artifact.nodes) || !Array.isArray(artifact.scene_documents)) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection does not satisfy the W1 acceptance contract.');
      }
      const sourceResolution = resolveProjectionSourcePath(runtime, projectRoot, artifactDirectory, artifact, artifactResolution.artifactRef);
      if (sourceResolution.blockedReason || !sourceResolution.path) return projectionBlockedResult(project, proposal, sourceResolution.blockedReason || 'Invalid staged manuscript source reference.');
      const sourceEvidencePath = sourceResolution.path;
      const expectedSourceEvidencePath = runtime.path.resolve(artifactDirectory, 'raw_source.txt');
      if (sourceEvidencePath !== expectedSourceEvidencePath || !runtime.fs.existsSync(sourceEvidencePath)) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection raw source evidence must be raw_source.txt inside its import run.');
      }
      const resolvedSourceEvidencePath = runtime.fs.realpathSync(sourceEvidencePath);
      if (
        resolvedSourceEvidencePath !== sourceEvidencePath
        || !isPathInside(runtime.path, resolvedRunDirectory, resolvedSourceEvidencePath)
      ) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection raw source evidence resolves through a symlink or outside its import run.');
      }
      const rawSource = runtime.fs.readFileSync(resolvedSourceEvidencePath, 'utf8');
      const rawSourceHash = await sha256Text(rawSource);
      if (rawSourceHash !== sourceHash || (sourceResolution.sha256 && sourceResolution.sha256 !== rawSourceHash)) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection raw source does not match its manifest hash.');
      }
      const chapterIds = new Set<string>();
      const sceneIds = new Set<string>();
      const sourceBySceneId = new Map<string, string>();
      for (const rawChapter of artifact.chapters) {
        if (!rawChapter || typeof rawChapter !== 'object') return projectionBlockedResult(project, proposal, 'Staged manuscript projection contains an invalid chapter descriptor.');
        const chapter = rawChapter as Record<string, unknown>;
        const chapterId = chapter.chapter_id;
        const sceneId = chapter.scene_id;
        const sourceSpan = chapter.source_span as Record<string, unknown> | undefined;
        if (
          typeof chapterId !== 'string' || !chapterId || chapterIds.has(chapterId)
          || typeof sceneId !== 'string' || !sceneId || sceneIds.has(sceneId)
          || !sourceSpan
        ) return projectionBlockedResult(project, proposal, `Staged manuscript projection contains an invalid, duplicate, or source-mismatched chapter descriptor: ${String(chapterId || sceneId || 'unknown')}.`);
        const reconstructed = await reconstructProjectionSourceSpan(sourceSpan, rawSource, sourceHash);
        if (reconstructed.error) return projectionBlockedResult(project, proposal, `Staged manuscript projection chapter ${chapterId} ${reconstructed.error}.`);
        chapterIds.add(chapterId);
        sceneIds.add(sceneId);
        sourceBySceneId.set(sceneId, reconstructed.content);
        artifactPairs.add(projectionPairKey(chapterId, sceneId));
      }
      const documentSceneIds = new Set<string>();
      for (const rawDocument of artifact.scene_documents) {
        if (!rawDocument || typeof rawDocument !== 'object') return projectionBlockedResult(project, proposal, 'Staged manuscript projection contains an invalid scene document.');
        const document = rawDocument as Record<string, unknown>;
        const sceneId = document.scene_id;
        const reconstructed = await reconstructProjectionSourceSpan(document.source_span, rawSource, sourceHash);
        if (
          typeof sceneId !== 'string' || !sceneIds.has(sceneId) || documentSceneIds.has(sceneId) || typeof document.content !== 'string'
          || reconstructed.error || document.content !== sourceBySceneId.get(sceneId) || document.content !== reconstructed.content
        ) {
          return projectionBlockedResult(project, proposal, `Staged manuscript projection contains an invalid or unapproved scene document: ${String(sceneId || 'unknown')}.`);
        }
        documentSceneIds.add(sceneId);
      }
      if (documentSceneIds.size !== sceneIds.size) {
        return projectionBlockedResult(project, proposal, 'Staged manuscript projection is missing a scene document for an accepted descriptor.');
      }
      const nodeIds = new Set<string>();
      for (const rawNode of artifact.nodes) {
        if (!rawNode || typeof rawNode !== 'object') return projectionBlockedResult(project, proposal, 'Staged manuscript projection contains an invalid manuscript node.');
        const id = (rawNode as Record<string, unknown>).id;
        if (typeof id !== 'string' || !id || nodeIds.has(id)) return projectionBlockedResult(project, proposal, `Staged manuscript projection contains a duplicate or invalid node: ${String(id || 'unknown')}.`);
        nodeIds.add(id);
      }
      for (const rawNode of artifact.nodes) {
        const node = rawNode as Record<string, unknown>;
        const parentId = node.parentId;
        const linkedChapterId = node.linkedChapterId;
        const linkedSceneId = node.linkedSceneId;
        if (
          (parentId !== null && (typeof parentId !== 'string' || !nodeIds.has(parentId)))
          || (linkedChapterId !== null && (typeof linkedChapterId !== 'string' || !chapterIds.has(linkedChapterId)))
          || (linkedSceneId !== null && (typeof linkedSceneId !== 'string' || !sceneIds.has(linkedSceneId)))
          || (typeof linkedChapterId === 'string' && typeof linkedSceneId === 'string' && !artifactPairs.has(projectionPairKey(linkedChapterId, linkedSceneId)))
        ) return projectionBlockedResult(project, proposal, `Staged manuscript projection contains an invalid node reference: ${String(node.id || 'unknown')}.`);
      }
    } catch {
      return projectionBlockedResult(project, proposal, `Staged manuscript projection is unreadable: ${artifactPath}`);
    }
  }
  if (artifactPairs.size !== descriptorPairs.size || [...artifactPairs].some((pair) => !descriptorPairs.has(pair))) {
    return projectionBlockedResult(project, culprit, 'Staged manuscript projection chapters do not exactly match the accepted package descriptors.');
  }
  return { project, culprit, blockedReason: null };
};

const applyStagedManuscriptProjections = async (project: NarrativeProject, proposals: Proposal[]): Promise<ProjectionApplyResult> => {
  const descriptors = proposals
    .map((proposal) => ({ proposal, descriptor: getStagedManuscriptProjectionDescriptor(proposal) }))
    .filter((entry): entry is { proposal: Proposal; descriptor: StagedManuscriptProjectionDescriptor } => Boolean(entry.descriptor));
  if (!descriptors.length) return { project, culprit: proposals[0], blockedReason: null };

  const runtime = getNodeRuntime();
  const culprit = descriptors[0].proposal;
  if (!runtime || project.metadata.rootPath.startsWith('memory://')) {
    return projectionBlockedResult(project, culprit, 'Staged manuscript projection requires a local project filesystem.');
  }

  const projectRoot = runtime.path.resolve(project.metadata.rootPath);
  const importsDirectory = runtime.path.resolve(projectRoot, 'system', 'imports');
  const runIds = uniqueStrings(proposals.flatMap(getImportRunIds));
  if (runIds.length !== 1) return projectionBlockedResult(project, culprit, 'Import package has conflicting or missing importRunId values.');
  const artifacts = new Map<string, StagedManuscriptProjectionArtifact>();

  for (const { proposal, descriptor } of descriptors) {
    const artifactResolution = resolveProjectionArtifactPath(runtime, importsDirectory, runIds[0], descriptor);
    if (artifactResolution.blockedReason || !artifactResolution.path) return projectionBlockedResult(project, proposal, artifactResolution.blockedReason || 'Invalid staged manuscript projection descriptor.');
    const artifactPath = artifactResolution.path;
    if (!isPathInside(runtime.path, importsDirectory, artifactPath) || !artifactPath.endsWith('/staged_manuscript_projection.json')) {
      return projectionBlockedResult(project, proposal, 'Staged manuscript projection path is outside the import artifact directory.');
    }
    if (artifacts.has(artifactPath)) continue;
    if (!runtime.fs.existsSync(artifactPath)) {
      return projectionBlockedResult(project, proposal, `Staged manuscript projection is unavailable: ${artifactPath}`);
    }
    try {
      const artifactText = runtime.fs.readFileSync(artifactPath, 'utf8');
      if (artifactResolution.artifactRef && (await sha256Text(artifactText)) !== artifactResolution.artifactRef.sha256) {
        return projectionBlockedResult(project, proposal, 'ArtifactRef hash does not match the staged manuscript projection.');
      }
      artifacts.set(artifactPath, JSON.parse(artifactText) as StagedManuscriptProjectionArtifact);
    } catch {
      return projectionBlockedResult(project, proposal, `Staged manuscript projection is unreadable: ${artifactPath}`);
    }
  }

  let draft = project;
  const knownNodeIds = new Set((draft.manuscriptNodes || []).map((node) => node.id));
  for (const artifact of artifacts.values()) {
    if (
      artifact.contract_version !== 'w1-staged-manuscript-v1'
      || artifact.acceptance_required !== true
      || !Array.isArray(artifact.chapters)
      || !Array.isArray(artifact.nodes)
      || !Array.isArray(artifact.scene_documents)
    ) {
      return projectionBlockedResult(project, culprit, 'Staged manuscript projection does not satisfy the W1 acceptance contract.');
    }

    const sceneDocuments = new Map<string, string>();
    for (const document of artifact.scene_documents) {
      if (!document || typeof document !== 'object') return projectionBlockedResult(project, culprit, 'Staged manuscript projection contains an invalid scene document.');
      const sceneId = (document as Record<string, unknown>).scene_id;
      const content = (document as Record<string, unknown>).content;
      if (typeof sceneId !== 'string' || !sceneId || typeof content !== 'string' || sceneDocuments.has(sceneId)) {
        return projectionBlockedResult(project, culprit, 'Staged manuscript projection contains an invalid or duplicate scene document.');
      }
      if (!draft.scenes.some((scene) => scene.id === sceneId)) {
        return projectionBlockedResult(project, culprit, `Staged manuscript projection references missing scene: ${sceneId}`);
      }
      sceneDocuments.set(sceneId, content);
    }

    const nodes: ManuscriptNode[] = [];
    for (const rawNode of artifact.nodes) {
      if (!rawNode || typeof rawNode !== 'object') return projectionBlockedResult(project, culprit, 'Staged manuscript projection contains an invalid manuscript node.');
      const node = rawNode as Record<string, unknown>;
      const type = node.type;
      const id = node.id;
      const linkedChapterId = node.linkedChapterId;
      const linkedSceneId = node.linkedSceneId;
      if (
        typeof id !== 'string' || !id || knownNodeIds.has(id)
        || !['act', 'part', 'chapter_outline', 'scene_outline', 'note'].includes(String(type))
        || (linkedChapterId !== null && (typeof linkedChapterId !== 'string' || !draft.chapters.some((chapter) => chapter.id === linkedChapterId)))
        || (linkedSceneId !== null && (typeof linkedSceneId !== 'string' || !draft.scenes.some((scene) => scene.id === linkedSceneId)))
      ) {
        return projectionBlockedResult(project, culprit, `Staged manuscript projection contains an invalid or conflicting node: ${String(id || 'unknown')}.`);
      }
      knownNodeIds.add(id);
      nodes.push({
        id,
        title: typeof node.title === 'string' ? node.title : '',
        type: type as ManuscriptNodeType,
        parentId: typeof node.parentId === 'string' ? node.parentId : null,
        orderIndex: typeof node.orderIndex === 'number' ? node.orderIndex : 0,
        linkedChapterId: linkedChapterId as string | null,
        linkedSceneId: linkedSceneId as string | null,
        depth: typeof node.depth === 'number' ? node.depth : 0,
        collapsed: Boolean(node.collapsed),
        wordCount: typeof node.wordCount === 'number' ? node.wordCount : 0,
      });
    }

    draft = {
      ...draft,
      scenes: draft.scenes.map((scene) => sceneDocuments.has(scene.id) ? { ...scene, content: sceneDocuments.get(scene.id)! } : scene),
      manuscriptNodes: [...(draft.manuscriptNodes || []), ...nodes],
    };
  }

  return { project: draft, culprit, blockedReason: null };
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

const applyProposalOperations = (project: NarrativeProject, proposal: Proposal, referenceSets?: ReferenceSets): ProposalApplyResult => {
  const operations = getProposalOperations(proposal);
  if (!operations.length) return { project, applied: false, blockedReason: null };

  let draft = project;
  let applied = false;

  for (const operation of operations) {
    if (operation.op === 'relocate_world_item_to_character' || operation.op === 'relocate_world_item') {
      const result = applyWorldItemRelocationOperation(draft, operation);
      if (result.blockedReason) return { project, applied: false, blockedReason: result.blockedReason };
      draft = result.project;
      applied = applied || result.applied;
      continue;
    }
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

const relocationAttributes = (value: unknown, idPrefix: string) => {
  if (Array.isArray(value)) {
    return value.flatMap((entry, index) => {
      if (!entry || typeof entry !== 'object') return [];
      const record = entry as Record<string, unknown>;
      const label = String(record.label || record.key || '').trim();
      const attributeValue = String(record.value || '').trim();
      return label ? [{ id: String(record.id || `${idPrefix}_${index}`), label, value: attributeValue }] : [];
    });
  }
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([label]) => label.trim())
      .map(([label, attributeValue], index) => ({ id: `${idPrefix}_${index}`, label, value: String(attributeValue ?? '') }));
  }
  return [];
};

const applyWorldItemRelocationOperation = (
  project: NarrativeProject,
  operation: RawProposalOperation,
): ProposalApplyResult => {
  const relocationPlan = operation.relocation_plan && typeof operation.relocation_plan === 'object'
    ? operation.relocation_plan
    : {};
  const mergePlan = relocationPlan.field_merge_plan && typeof relocationPlan.field_merge_plan === 'object'
    ? relocationPlan.field_merge_plan as Record<string, unknown>
    : {};
  const fields: Record<string, unknown> = {
    ...mergePlan,
    ...(operation.fields || {}),
    sourceWorldItemId:
      operation.fields?.sourceWorldItemId
      || operation.fields?.source_world_item_id
      || relocationPlan.source_candidate_id,
    targetCharacterId:
      operation.fields?.targetCharacterId
      || operation.fields?.target_character_id
      || operation.fields?.targetEntityId
      || relocationPlan.target_entity_id,
  };
  const sourceId = String(fields.sourceWorldItemId || fields.source_world_item_id || operation.entityId || '');
  const targetId = String(fields.targetCharacterId || fields.target_character_id || fields.targetEntityId || '');
  if (!sourceId) return { project, applied: false, blockedReason: 'relocate_world_item_to_character is missing sourceWorldItemId.' };
  if (!targetId) return { project, applied: false, blockedReason: `relocate_world_item_to_character ${sourceId} is missing targetCharacterId.` };
  const source = project.worldItems.find((item) => item.id === sourceId);
  if (!source) return { project, applied: false, blockedReason: `Cannot relocate missing world item ${sourceId}.` };
  const target = project.characters.find((character) => character.id === targetId);
  if (!target) return { project, applied: false, blockedReason: `Cannot relocate world item ${sourceId}: target character ${targetId} does not exist.` };
  if (project.worldItems.some((item) => item.id !== sourceId && item.parentId === sourceId)) {
    return { project, applied: false, blockedReason: `Cannot relocate world item ${sourceId}: child world items must be moved first.` };
  }

  const reciprocalEventIds = project.timelineEvents
    .filter((event) => event.locationIds.includes(sourceId) || event.linkedWorldItemIds.includes(sourceId))
    .map((event) => event.id);
  const reciprocalSceneIds = project.scenes
    .filter((scene) => scene.linkedWorldItemIds.includes(sourceId))
    .map((scene) => scene.id);
  const sourceAttributes = source.attributes
    .filter((attribute) => attribute.key.trim())
    .map((attribute, index) => ({ id: `relocation_${sourceId}_${index}`, label: attribute.key, value: attribute.value }));
  const incomingAliases = Array.isArray(fields.aliases) ? fields.aliases.map(String) : [];
  const incomingEvidence = Array.isArray(fields.evidenceRefs) ? fields.evidenceRefs.map(String) : (Array.isArray(fields.evidence_refs) ? fields.evidence_refs.map(String) : []);
  const incomingAttributes = relocationAttributes(fields.customAttributes, `relocation_input_${sourceId}`);
  const role = typeof fields.role === 'string' && fields.role.trim() ? fields.role.trim() : undefined;
  const existingEvidence = target.evidenceRefs || [];
  const customAttributesByLabel = new Map((target.customAttributes || []).map((attribute) => [attribute.label, attribute]));
  [...sourceAttributes, ...incomingAttributes].forEach((attribute) => customAttributesByLabel.set(attribute.label, attribute));
  const updatedTarget = {
    ...target,
    aliases: uniqueStrings([...target.aliases, source.name, ...incomingAliases]).filter((alias) => alias !== target.name),
    linkedEventIds: uniqueStrings([...target.linkedEventIds, ...source.linkedEventIds, ...reciprocalEventIds]),
    linkedSceneIds: uniqueStrings([...target.linkedSceneIds, ...source.linkedSceneIds, ...reciprocalSceneIds]),
    linkedWorldItemIds: target.linkedWorldItemIds.filter((id) => id !== sourceId),
    ...(role ? { role } : {}),
    evidenceRefs: uniqueStrings([...existingEvidence, ...incomingEvidence]),
    customAttributes: Array.from(customAttributesByLabel.values()),
  };

  const relocated: NarrativeProject = {
    ...project,
    characters: project.characters.map((character) => character.id === targetId
      ? updatedTarget
      : { ...character, linkedWorldItemIds: character.linkedWorldItemIds.filter((id) => id !== sourceId) }),
    timelineEvents: project.timelineEvents.map((event) => ({
      ...event,
      locationIds: event.locationIds.filter((id) => id !== sourceId),
      linkedWorldItemIds: event.linkedWorldItemIds.filter((id) => id !== sourceId),
    })),
    scenes: project.scenes.map((scene) => ({ ...scene, linkedWorldItemIds: scene.linkedWorldItemIds.filter((id) => id !== sourceId) })),
    worldItems: project.worldItems.filter((item) => item.id !== sourceId),
  };
  const dangling = hasEntityReferences(relocated, 'world_item', sourceId);
  if (dangling) return { project, applied: false, blockedReason: `Cannot relocate world item ${sourceId}: relocation would leave dangling references.` };
  return { project: relocated, applied: true, blockedReason: null };
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

const mergeDecisionPayloadFields: Record<string, string[]> = {
  aliases: ['aliases'],
  background: ['background'],
  experience: ['experience'],
  experiences: ['experiences'],
  traits: ['traits', 'personality_traits'],
  personalityTraits: ['personality_traits', 'traits'],
  notes: ['notes'],
  physicalDescription: ['physical_description'],
  speechStyle: ['speech_style'],
  arcNotes: ['arc_notes'],
  importConfidence: ['confidence'],
};

const mergeValuesEqual = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

const validateEntityMergeDecision = (
  existing: Record<string, unknown> | undefined,
  fields: Record<string, unknown>,
): string | null => {
  const mergeEvidence = fields.mergeEvidence;
  if (!mergeEvidence || typeof mergeEvidence !== 'object') return 'Imported character update is missing EntityMergeDecision/v1.';
  const evidence = mergeEvidence as Record<string, unknown>;
  const decision = evidence.entityMergeDecision;
  if (!decision || typeof decision !== 'object') return 'Imported character merge evidence is missing EntityMergeDecision/v1.';
  const merge = decision as Record<string, unknown>;
  if (merge.contract !== 'EntityMergeDecision/v1' || merge.existing_id !== existing?.id || !merge.fields || typeof merge.fields !== 'object') {
    return `Imported character merge evidence does not validate for canonical character ${String(existing?.id || 'unknown')}.`;
  }
  if (typeof merge.import_id !== 'string' || !merge.import_id || evidence.importCharacterId !== merge.import_id) {
    return 'Imported character merge evidence has a missing or mismatched import character ID.';
  }
  if (evidence.semanticConflicts !== undefined && !Array.isArray(evidence.semanticConflicts)) {
    return 'Imported character merge evidence has invalid semantic conflict diagnostics.';
  }
  if (fields.id !== existing?.id) {
    return `Imported character merge update targets a mismatched canonical character ID ${String(fields.id || 'unknown')}.`;
  }

  const decisionFields = merge.fields as Record<string, unknown>;
  const permittedMetadata = new Set(['id', 'mergeEvidence', 'importRunId', 'import_run_id']);
  for (const [field, value] of Object.entries(fields)) {
    if (permittedMetadata.has(field)) continue;
    const decisionFieldName = mergeDecisionPayloadFields[field]?.find((name) => Object.prototype.hasOwnProperty.call(decisionFields, name));
    const decisionField = decisionFieldName ? decisionFields[decisionFieldName] as Record<string, unknown> : null;
    if (!decisionField || typeof decisionField !== 'object') {
      return `Imported character merge update contains undeclared field ${field}.`;
    }
    if (!['union', 'preserve_existing', 'evidence_append', 'max'].includes(String(decisionField.action)) || !Object.prototype.hasOwnProperty.call(decisionField, 'value')) {
      return `Imported character merge decision has an invalid action for field ${field}.`;
    }
    if (!mergeValuesEqual(value, decisionField.value)) {
      return `Imported character merge update value for ${field} does not match EntityMergeDecision/v1.`;
    }
    const existingField = field === 'importConfidence' ? (existing?.importConfidence ?? existing?.confidence ?? 0) : existing?.[field];
    if (decisionField.action === 'preserve_existing' && !mergeValuesEqual(decisionField.value, existingField)) {
      return `Imported character merge decision is stale for preserved field ${field}.`;
    }
    if (decisionField.action === 'union' && Array.isArray(existingField) && (!Array.isArray(decisionField.value) || existingField.some((entry) => !(decisionField.value as unknown[]).some((candidate) => mergeValuesEqual(candidate, entry))))) {
      return `Imported character merge decision is stale for union field ${field}.`;
    }
    if (decisionField.action === 'evidence_append' && typeof existingField === 'string' && existingField && (typeof decisionField.value !== 'string' || !decisionField.value.startsWith(existingField))) {
      return `Imported character merge decision is stale for appended field ${field}.`;
    }
    if (decisionField.action === 'max' && typeof existingField === 'number' && (typeof decisionField.value !== 'number' || decisionField.value < existingField)) {
      return `Imported character merge decision is stale for maximum field ${field}.`;
    }
  }
  return null;
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
    return { project, applied: false, blockedReason: `Cannot create duplicate ${entityType} ${id}; imported create must be reconciled as an explicit update.` };
  }

  if (operation.op === 'create' && entityType === 'character' && importedProposalSource(proposal)) {
    const duplicate = findImportedCharacterDuplicate(records, id, nextEntity);
    if (duplicate) {
      return { project, applied: false, blockedReason: `Imported character ${id} conflicts with canonical character ${duplicate.id} by name or alias; submit an explicit update with EntityMergeDecision/v1.` };
    }
  }

  if (operation.op === 'update' && entityType === 'character' && importedProposalSource(proposal)) {
    const mergeDecisionError = validateEntityMergeDecision(existing, fields);
    if (mergeDecisionError) return { project, applied: false, blockedReason: mergeDecisionError };
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
      return { id, title, summary: '', branchId: importedProposalSource(proposal) ? '' : project.timelineBranches[0]?.id || '', orderIndex: project.timelineEvents.length, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [], ...fields };
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
      return { id, chapterId: importedProposalSource(proposal) ? '' : project.chapters[0]?.id || '', title, summary: '', content: '', orderIndex: project.scenes.length, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft', ...fields };
    case 'world_container':
      return { id, name: title, type: 'notebook', isDefault: false, sortOrder: project.worldContainers.length, ...fields };
    case 'world_item': {
      const worldItemFields = { ...fields };
      if (worldItemFields.containerId == null) delete worldItemFields.containerId;
      return { id, containerId: importedProposalSource(proposal) ? '' : project.worldContainers[0]?.id || '', type: 'note', name: title, description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], ...worldItemFields };
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
    if (typeof entity.branchId !== 'string' || !entity.branchId) return `${entityType} ${entity.id} is missing required branchId.`;
    if (!branches.has(entity.branchId)) return `${entityType} ${entity.id} references missing branch: ${entity.branchId}`;
    return fail('characters', missingIds(entity.participantCharacterIds, characters))
      || fail('scenes', missingIds(entity.linkedSceneIds, scenes))
      || fail('shared branches', missingIds(entity.sharedBranchIds, branches))
      || fail('world items', [...missingIds(entity.locationIds, worldItems), ...missingIds(entity.linkedWorldItemIds, worldItems)]);
  }
  if (entityType === 'timeline_branch') {
    const missingParent = entity.parentBranchId && !branches.has(String(entity.parentBranchId))
      ? [String(entity.parentBranchId)] : [];
    const missingMergeTarget = entity.mergeTargetBranchId && !branches.has(String(entity.mergeTargetBranchId))
      ? [String(entity.mergeTargetBranchId)] : [];
    const eventIds = [
      entity.forkEventId,
      entity.mergeEventId,
      (entity.startAnchor as Record<string, unknown> | null | undefined)?.eventId,
      (entity.endAnchor as Record<string, unknown> | null | undefined)?.eventId,
    ].filter(Boolean).map(String);
    return fail('parent branches', missingParent)
      || fail('merge target branches', missingMergeTarget)
      || fail('anchor events', eventIds.filter((id) => !events.has(id)));
  }
  if (entityType === 'scene') {
    if (typeof entity.chapterId !== 'string' || !entity.chapterId) return `${entityType} ${entity.id} is missing required chapterId.`;
    if (!chapters.has(entity.chapterId)) return `${entityType} ${entity.id} references missing chapter: ${entity.chapterId}`;
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
    if (!entity.sourceId || !entity.targetId) return `${entityType} ${entity.id} is missing required sourceId or targetId.`;
    return fail('characters', [String(entity.sourceId || ''), String(entity.targetId || '')].filter((id) => id && !characters.has(id)));
  }
  if (entityType === 'world_item') {
    if (typeof entity.containerId !== 'string' || !entity.containerId) return `${entityType} ${entity.id} is missing required containerId.`;
    if (!containers.has(entity.containerId)) return `${entityType} ${entity.id} references missing container: ${entity.containerId}`;
    if (entity.parentId && !containers.has(String(entity.parentId)) && !worldItems.has(String(entity.parentId))) {
      return `${entityType} ${entity.id} references missing parent: ${String(entity.parentId)}`;
    }
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
