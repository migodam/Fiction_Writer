import { create } from 'zustand';
import type {
  BetaFeedbackItem,
  BetaPersona,
  BetaRun,
  Candidate,
  Chapter,
  Character,
  CharacterPovInsights,
  CharacterTag,
  ConsistencyIssue,
  CreateProjectInput,
  EntityKind,
  ExportArtifact,
  GraphBoard,
  GraphNode,
  ImportJob,
  Locale,
  ManuscriptNode,
  MetadataFile,
  NarrativeProject,
  PromptTemplate,
  Proposal,
  RagChunk,
  RagDocument,
  Relationship,
  SaveStatus,
  Scene,
  SimulationEngine,
  SimulationLab,
  SimulationReviewer,
  SimulationRun,
  SearchResult,
  Selection,
  StoryboardPlan,
  ScriptDocument,
  TaskArtifact,
  TaskRequest,
  TaskRun,
  TaskRunLogRef,
  TimelineBranch,
  TimelineEvent,
  TodoItem,
  VideoGenerationPackage,
  WorldMapDocument,
  WorldSettings,
  WorldContainer,
  WorldItem,
  AppSettings,
} from './models/project';
import { buildBranchControlPoints, cubicBezierPoint, nearestTOnCurve, tFromOrderIndex } from './components/timeline/bezierMath';
import { createStarterProject } from './mock/seedProject';
import { projectService } from './services/projectService';
import { appSettingsService, defaultAppSettings } from './services/appSettingsService';
import * as metadataService from './services/metadataService';
import { electronApi } from './services/electronApi';

const UI_SETTINGS_KEY = 'narrative-ide-ui-settings';

type PanelKind = 'sidebar' | 'inspector' | 'agentDock' | 'writingOutline' | 'writingContext';
type ContextMenuItem = { id: string; label: string; action: () => void; destructive?: boolean };
type ContextMenuState = { x: number; y: number; items: ContextMenuItem[] } | null;

interface UIState {
  currentActivity: string;
  sidebarSection: string;
  locale: Locale;
  density: 'comfortable' | 'compact';
  editorWidth: 'focused' | 'wide';
  motionLevel: 'full' | 'reduced';
  isCommandPaletteOpen: boolean;
  isAgentDockOpen: boolean;
  isSidebarCollapsed: boolean;
  isSettingsOpen: boolean;
  sidebarWidth: number;
  inspectorWidth: number;
  agentDockWidth: number;
  writingOutlineWidth: number;
  writingContextWidth: number;
  isWritingOutlineCollapsed: boolean;
  isWritingContextCollapsed: boolean;
  appSettings: AppSettings;
  lastActionStatus: string | null;
  contextMenu: ContextMenuState;
  agentChatMode: 'writing' | 'consistency' | 'simulation' | 'retrieval' | 'general';
  agentChatMessages: Array<{ id: string; role: 'user' | 'assistant'; content: string; timestamp: string; taskRunId?: string }>;
  setAgentChatMode: (mode: 'writing' | 'consistency' | 'simulation' | 'retrieval' | 'general') => void;
  addAgentChatMessage: (msg: { id: string; role: 'user' | 'assistant'; content: string; timestamp: string; taskRunId?: string }) => void;
  setActivity: (id: string) => void;
  setSidebarSection: (section: string) => void;
  setLocale: (locale: Locale) => void;
  setDensity: (density: UIState['density']) => void;
  setEditorWidth: (width: UIState['editorWidth']) => void;
  setMotionLevel: (level: UIState['motionLevel']) => void;
  toggleCommandPalette: (open?: boolean) => void;
  toggleAgentDock: (open?: boolean) => void;
  toggleSidebar: (open?: boolean) => void;
  toggleSettings: (open?: boolean) => void;
  toggleWritingPane: (panel: 'outline' | 'context', open?: boolean) => void;
  setPanelWidth: (panel: PanelKind, width: number) => void;
  resetLayout: () => void;
  setLastActionStatus: (status: string | null) => void;
  openContextMenu: (menu: ContextMenuState) => void;
  closeContextMenu: () => void;
  loadAppSettings: () => Promise<void>;
  saveAppSettings: (partial: Partial<AppSettings>) => Promise<void>;
  hydrateFromProjectUiState: (uiState: NarrativeProject['uiState']) => void;
}

interface ProjectState {
  projectName: string;
  projectRoot: string;
  saveStatus: SaveStatus;
  selectedEntity: Selection;
  characters: Character[];
  characterTags: CharacterTag[];
  candidates: Candidate[];
  timelineEvents: TimelineEvent[];
  timelineBranches: TimelineBranch[];
  relationships: NarrativeProject['relationships'];
  chapters: Chapter[];
  scenes: Scene[];
  currentSceneContent: string;
  worldContainers: WorldContainer[];
  worldItems: WorldItem[];
  worldSettings: WorldSettings;
  worldMaps: WorldMapDocument[];
  graphBoards: GraphBoard[];
  activeGraphBoardId: string | null;
  betaPersonas: BetaPersona[];
  betaRuns: BetaRun[];
  simulationEngines: SimulationEngine[];
  simulationLabs: SimulationLab[];
  simulationReviewers: SimulationReviewer[];
  simulationRuns: SimulationRun[];
  taskRequests: TaskRequest[];
  taskRuns: TaskRun[];
  taskArtifacts: TaskArtifact[];
  taskRunLogs: TaskRunLogRef[];
  importJobs: ImportJob[];
  promptTemplates: PromptTemplate[];
  ragDocuments: RagDocument[];
  ragChunks: RagChunk[];
  scripts: ScriptDocument[];
  storyboards: StoryboardPlan[];
  videoPackages: VideoGenerationPackage[];
  proposals: Proposal[];
  proposalHistory: Proposal[];
  issues: ConsistencyIssue[];
  exports: ExportArtifact[];
  archivedIds: string[];
  unreadUpdates: NarrativeProject['unreadUpdates'];
  currentProject: NarrativeProject | null;
  setSelectedEntity: (type: EntityKind | null, id: string | null) => void;
  createProject: (input?: Partial<CreateProjectInput>) => Promise<void>;
  openProject: (rootPath?: string | null) => Promise<void>;
  saveProject: () => Promise<void>;
  loadProject: (project: NarrativeProject) => void;
  setProjectLocale: (locale: Locale) => void;
  syncProjectUiState: () => void;
  addCharacter: (character: Character) => void;
  updateCharacter: (character: Character) => void;
  deleteCharacter: (id: string) => void;
  addCharacterTag: (tag: CharacterTag) => void;
  updateCharacterTag: (tag: CharacterTag) => void;
  deleteCharacterTag: (tagId: string) => void;
  toggleCharacterTagMembership: (tagId: string, characterId: string) => void;
  confirmCandidate: (candidateId: string) => string | null;
  rejectCandidate: (candidateId: string) => void;
  addTimelineEvent: (event: TimelineEvent) => void;
  updateTimelineEvent: (event: TimelineEvent) => void;
  deleteTimelineEvent: (id: string) => void;
  addTimelineBranch: (branch: TimelineBranch) => void;
  updateTimelineBranch: (branch: TimelineBranch) => void;
  deleteTimelineBranch: (branchId: string) => void;
  createTimelineBranch: (mode: TimelineBranch['mode'], anchor?: { branchId: string; eventId: string } | null) => string | null;
  moveTimelineEvent: (eventId: string, targetBranchId: string, targetSlot: number) => void;
  setTimelineBranchGeometry: (branchId: string, geometry: TimelineBranch['geometry']) => void;
  setTimelineBranchAnchors: (
    branchId: string,
    startPos: { x: number; y: number },
    endPos: { x: number; y: number },
    anchors?: { startAnchor?: TimelineBranch['startAnchor']; endAnchor?: TimelineBranch['endAnchor'] },
  ) => void;
  updateTimelineEventPosition: (eventId: string, position: { x: number; y: number }) => void;
  addRelationship: (relationship: Relationship) => void;
  updateRelationship: (relationship: Relationship) => void;
  deleteRelationship: (id: string) => void;
  addChapter: (chapter: Chapter) => void;
  updateChapter: (chapter: Chapter) => void;
  deleteChapter: (id: string) => void;
  addScene: (scene: Scene) => void;
  updateScene: (scene: Scene) => void;
  deleteScene: (id: string) => void;
  updateScript: (script: ScriptDocument) => void;
  addScript: (script: ScriptDocument) => void;
  addStoryboard: (storyboard: StoryboardPlan) => void;
  updateStoryboard: (storyboard: StoryboardPlan) => void;
  addWorldContainer: (container: WorldContainer) => void;
  updateWorldContainer: (container: WorldContainer) => void;
  deleteWorldContainer: (id: string) => void;
  addWorldItem: (item: WorldItem) => void;
  updateWorldItem: (item: WorldItem) => void;
  deleteWorldItem: (id: string) => void;
  updateWorldSettings: (settings: WorldSettings) => void;
  createWorldMap: (map: WorldMapDocument) => void;
  updateWorldMap: (map: WorldMapDocument) => void;
  addGraphBoard: (board: GraphBoard) => void;
  updateGraphBoard: (board: GraphBoard) => void;
  deleteGraphBoard: (boardId: string) => void;
  setActiveGraphBoard: (boardId: string) => void;
  addGraphNode: (boardId: string, node: GraphNode) => void;
  updateGraphNode: (boardId: string, node: GraphNode) => void;
  deleteGraphNode: (boardId: string, nodeId: string) => void;
  addGraphEdge: (boardId: string, edge: GraphBoard['edges'][number]) => void;
  deleteGraphEdge: (boardId: string, edgeId: string) => void;
  updateGraphEdge: (boardId: string, edge: Partial<GraphBoard['edges'][number]> & { id: string }) => void;
  setGraphBoardView: (boardId: string, view: GraphBoard['view']) => void;
  resolveProposal: (proposalId: string, status: Proposal['status']) => void;
  resolveIssue: (issueId: string, resolution: 'resolved' | 'ignored') => void;
  dismissIssue: (issueId: string) => void;
  addProposal: (proposal: Proposal) => void;
  addGraphSyncProposal: (title: string, preview: string) => void;
  addExportArtifact: (artifact: ExportArtifact) => void;
  addBetaPersona: (persona: BetaPersona) => void;
  updateBetaPersona: (persona: BetaPersona) => void;
  deleteBetaPersona: (personaId: string) => void;
  runBetaPersona: (personaId: string) => void;
  addSimulationEngine: (engine: SimulationEngine) => void;
  updateSimulationEngine: (engine: SimulationEngine) => void;
  createSimulationLab: (lab: SimulationLab) => void;
  updateSimulationLab: (lab: SimulationLab) => void;
  runSimulationLab: (labId: string) => void;
  createSimulationReviewer: (reviewer: SimulationReviewer) => void;
  updateSimulationReviewer: (reviewer: SimulationReviewer) => void;
  runSimulationReviewer: (reviewerId: string) => void;
  runSimulationEngine: (engineId: string, context: { entityId: string; entityType: 'lab' | 'reviewer' }) => void;
  addTaskRequest: (task: TaskRequest) => void;
  addTaskRun: (run: TaskRun, artifact?: TaskArtifact) => void;
  updateTaskRun: (id: string, patch: Partial<Pick<TaskRun, 'status' | 'summary' | 'heartbeatAt' | 'finishedAt'>>) => void;
  addImportJob: (job: ImportJob) => void;
  updateImportJob: (job: ImportJob) => void;
  upsertCharacterPovInsights: (characterId: string, insights: CharacterPovInsights) => void;
  clearUnreadEntity: (entityId: string) => void;
  clearUnreadActivity: (activityId: string) => void;
  searchEntities: (query: string) => SearchResult[];
  dbSearchEntities: (query: string) => Promise<Array<{ entity_type: string; entity_id: string; title: string }>>;
  metadataFiles: MetadataFile[];
  loadMetadata: (projectRoot: string) => void;
  importMetadataFile: (projectRoot: string, filePath: string, meta: Pick<MetadataFile, 'type' | 'tags' | 'description'>) => void;
  deleteMetadataFile: (projectRoot: string, fileId: string) => void;
  todos: TodoItem[];
  createTodo: (item: Omit<TodoItem, 'id' | 'createdAt' | 'updatedAt'>) => void;
  updateTodo: (id: string, patch: Partial<Pick<TodoItem, 'title' | 'description' | 'status' | 'priority' | 'relatedEntityType' | 'relatedEntityId'>>) => void;
  deleteTodo: (id: string) => void;
  manuscriptNodes: ManuscriptNode[];
  addManuscriptNode: (node: Omit<ManuscriptNode, 'id'>) => ManuscriptNode;
  updateManuscriptNode: (id: string, updates: Partial<ManuscriptNode>) => void;
  deleteManuscriptNode: (id: string) => void;
  moveManuscriptNode: (id: string, newParentId: string | null, newOrderIndex: number) => void;
  loadManuscriptNodeContent: (projectRoot: string, nodeId: string) => Promise<string>;
  saveManuscriptNodeContent: (projectRoot: string, nodeId: string, content: string) => Promise<void>;
  // W3 Writing Assistant state
  w3Status: 'idle' | 'running' | 'waiting_selection' | 'done' | 'error';
  w3Options: string[];
  w3Output: string;
  w3SessionId: string | null;
  w3Progress: number;
  w3Error: string | null;
  startW3: (payload: { scene_id: string; task: string; hitl_mode: 'direct_output' | 'three_options'; metadata_file_id?: string }) => Promise<void>;
  selectW3Option: (index: number) => Promise<void>;
  resetW3: () => void;

  // W1 Import state
  w1Status: 'idle' | 'running' | 'done' | 'error' | 'cancelled';
  w1Progress: number;
  w1CompletedChunks: number;
  w1TotalChunks: number;
  w1Errors: string[];
  w1SessionId: string | null;
  w1ImportMode: 'import_content_only' | 'import_all';
  setW1ImportMode: (mode: 'import_content_only' | 'import_all') => void;
  startImport: (payload: { projectRoot: string; sourceFilePath: string; importMode?: 'import_content_only' | 'import_all' }) => Promise<void>;
  cancelImport: () => Promise<void>;
  resetImport: () => void;

  // W2 Manuscript Sync state
  w2Status: 'idle' | 'running' | 'done' | 'error';
  w2Progress: number;
  w2ProposalCount: number;
  startManuscriptSync: (payload: { projectRoot: string; mode: string; target_chapter_id?: string }) => Promise<void>;

  // Entity focus (navigates sidebar to entity)
  focusEntity: (entityType: string, entityId: string) => void;

  // W4 Consistency Check state
  w4Status: 'idle' | 'running' | 'done' | 'error';
  w4Issues: any[];
  w4SeverityCounts: Record<string, number>;
  w4Progress: number;
  runConsistencyCheck: (payload: { projectRoot: string; scope: string; target_id: string }) => Promise<void>;

  // W5 Simulation Engine state
  w5Status: 'idle' | 'running' | 'done' | 'error';
  w5Progress: number;
  w5ReportMarkdown: string;
  w5EngineResults: Record<string, any>;
  runSimulation: (payload: { projectRoot: string; scenario_variable: string; affected_chapter_ids: string[]; engines_selected: string[] }) => Promise<void>;

  // W6 Beta Reader state
  w6Status: 'idle' | 'running' | 'done' | 'error';
  w6Progress: number;
  w6ReportMarkdown: string;
  w6FeedbackItems: any[];
  runBetaReader: (payload: { projectRoot: string; persona_id: string; target_chapter_ids: string[] }) => Promise<void>;

  // W7 Metadata Ingestion state
  w7Status: 'idle' | 'running' | 'done' | 'error';
  w7Progress: number;
  w7CurrentFileId: string | null;
  ingestMetadata: (payload: { projectRoot: string; source_file_path: string; file_type: string }) => Promise<void>;

  // Orchestrator state
  orchestratorStatus: 'idle' | 'planning' | 'executing' | 'waiting_permission' | 'done' | 'error';
  orchestratorProgress: number;
  orchestratorPlan: any[];
  orchestratorCurrentStep: number;
  orchestratorPendingPermission: any | null;
  orchestratorSessionId: string | null;
  startOrchestrator: (payload: { projectRoot: string; goal: string; auto_apply_threshold?: number }) => Promise<void>;
  grantPermission: (projectRoot: string, stepId: string) => Promise<void>;
  denyPermission: (projectRoot: string, stepId: string, reason: string) => Promise<void>;
  resetOrchestrator: () => void;
}

const now = () => new Date().toISOString();
const defaultProject = createStarterProject();
const TIMELINE_CANVAS_WIDTH = 2000;
const readUiSettings = () => (typeof window === 'undefined' ? null : JSON.parse(window.localStorage.getItem(UI_SETTINGS_KEY) || 'null'));
const persistUiSettings = (settings: object) => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(UI_SETTINGS_KEY, JSON.stringify({ ...(readUiSettings() || {}), ...settings }));
};

const buildStoredBranchControlPoints = (branch: TimelineBranch) =>
  buildBranchControlPoints(
    branch.anchorStartPos,
    branch.anchorEndPos,
    branch.geometry?.laneOffset ?? branch.sortOrder * 90,
    branch.geometry?.bend ?? 0.25,
    TIMELINE_CANVAS_WIDTH,
  );

const pointsMatch = (
  left?: { x: number; y: number } | null,
  right?: { x: number; y: number } | null,
  epsilon = 0.5,
) => {
  if (!left && !right) return true;
  if (!left || !right) return false;
  return Math.abs(left.x - right.x) <= epsilon && Math.abs(left.y - right.y) <= epsilon;
};

const resolveEndAnchor = (branch: TimelineBranch): TimelineBranch['endAnchor'] =>
  branch.endAnchor ??
  (branch.mergeEventId && branch.mergeTargetBranchId
    ? { branchId: branch.mergeTargetBranchId, eventId: branch.mergeEventId }
    : null);

const withResolvedBranchAnchors = (
  branch: TimelineBranch,
  updates?: { startAnchor?: TimelineBranch['startAnchor']; endAnchor?: TimelineBranch['endAnchor'] },
): TimelineBranch => {
  const hasStartAnchor = updates && Object.prototype.hasOwnProperty.call(updates, 'startAnchor');
  const hasEndAnchor = updates && Object.prototype.hasOwnProperty.call(updates, 'endAnchor');
  const nextStartAnchor = hasStartAnchor ? updates?.startAnchor ?? null : branch.startAnchor ?? null;
  const nextEndAnchor = hasEndAnchor ? updates?.endAnchor ?? null : resolveEndAnchor(branch);

  return {
    ...branch,
    startAnchor: nextStartAnchor,
    endAnchor: nextEndAnchor,
    mergeEventId: nextEndAnchor?.eventId ?? null,
    mergeTargetBranchId: nextEndAnchor?.branchId ?? null,
    endMode: nextEndAnchor ? 'merge' : branch.endMode === 'merge' ? 'open' : branch.endMode ?? 'open',
  };
};

const buildTimelineEventPositionMap = (
  branches: TimelineBranch[],
  events: TimelineEvent[],
) => {
  const positions = new Map<string, { x: number; y: number }>();
  const branchMap = new Map(branches.map((branch) => [branch.id, branch]));
  const eventsByBranch = new Map<string, TimelineEvent[]>();

  for (const event of events) {
    const bucket = eventsByBranch.get(event.branchId) || [];
    bucket.push(event);
    eventsByBranch.set(event.branchId, bucket);
  }

  for (const [branchId, branchEvents] of eventsByBranch) {
    const branch = branchMap.get(branchId);
    if (!branch) continue;

    const controlPoints = buildStoredBranchControlPoints(branch);
    branchEvents
      .slice()
      .sort((left, right) => left.orderIndex - right.orderIndex)
      .forEach((event, index, orderedBranchEvents) => {
        positions.set(
          event.id,
          event.position ??
            cubicBezierPoint(
              controlPoints.p0,
              controlPoints.p1,
              controlPoints.p2,
              controlPoints.p3,
              tFromOrderIndex(orderedBranchEvents.length, index),
            ),
        );
      });
  }

  return positions;
};

const propagateTimelineAnchorDependencies = (
  branches: TimelineBranch[],
  events: TimelineEvent[],
) => {
  let nextBranches = branches;
  let nextEvents = events;
  const maxPasses = Math.max(1, branches.length * 3);

  for (let pass = 0; pass < maxPasses; pass += 1) {
    const eventPositions = buildTimelineEventPositionMap(nextBranches, nextEvents);
    let mutated = false;

    for (const branch of nextBranches) {
      const startAnchor = branch.startAnchor ?? null;
      const endAnchor = resolveEndAnchor(branch);
      const nextStartPos = startAnchor ? eventPositions.get(startAnchor.eventId) : undefined;
      const nextEndPos = endAnchor ? eventPositions.get(endAnchor.eventId) : undefined;

      if (
        (nextStartPos && !pointsMatch(branch.anchorStartPos, nextStartPos)) ||
        (nextEndPos && !pointsMatch(branch.anchorEndPos, nextEndPos))
      ) {
        const updatedBranch: TimelineBranch = {
          ...branch,
          anchorStartPos: nextStartPos ?? branch.anchorStartPos,
          anchorEndPos: nextEndPos ?? branch.anchorEndPos,
        };

        nextBranches = nextBranches.map((entry) => (entry.id === branch.id ? updatedBranch : entry));
        nextEvents = remapBranchEventPositions(nextEvents, branch.id, branch, updatedBranch);
        mutated = true;
      }
    }

    if (!mutated) {
      break;
    }
  }

  return { timelineBranches: nextBranches, timelineEvents: nextEvents };
};

const remapBranchEventPositions = (
  events: TimelineEvent[],
  branchId: string,
  previousBranch: TimelineBranch,
  nextBranch: TimelineBranch,
) => {
  const prevControlPoints = buildStoredBranchControlPoints(previousBranch);
  const nextControlPoints = buildStoredBranchControlPoints(nextBranch);

  return events.map((event) => {
    if (event.branchId !== branchId || !event.position) {
      return event;
    }

    const { t } = nearestTOnCurve(prevControlPoints, event.position, 100);
    return {
      ...event,
      position: cubicBezierPoint(
        nextControlPoints.p0,
        nextControlPoints.p1,
        nextControlPoints.p2,
        nextControlPoints.p3,
        t,
      ),
    };
  });
};

const deriveState = (project: NarrativeProject) => {
  const propagatedTimeline = propagateTimelineAnchorDependencies(project.timelineBranches, project.timelineEvents);
  const hydratedProject: NarrativeProject = {
    ...project,
    timelineBranches: propagatedTimeline.timelineBranches,
    timelineEvents: propagatedTimeline.timelineEvents,
  };

  return {
    projectName: hydratedProject.metadata.name,
    projectRoot: hydratedProject.metadata.rootPath,
    characters: hydratedProject.characters,
    characterTags: hydratedProject.characterTags,
    candidates: hydratedProject.candidates,
    timelineEvents: hydratedProject.timelineEvents,
    timelineBranches: hydratedProject.timelineBranches,
    relationships: hydratedProject.relationships,
    chapters: hydratedProject.chapters,
    scenes: hydratedProject.scenes,
    currentSceneContent: hydratedProject.scenes[0]?.content || '',
    worldContainers: hydratedProject.worldContainers,
    worldItems: hydratedProject.worldItems,
    worldSettings: hydratedProject.worldSettings,
    worldMaps: hydratedProject.worldMaps,
    graphBoards: hydratedProject.graphBoards,
    activeGraphBoardId:
      hydratedProject.uiState.view.activeGraphBoardId ||
      hydratedProject.metadata.lastOpenedBoardId ||
      hydratedProject.graphBoards[0]?.id ||
      null,
    betaPersonas: hydratedProject.betaPersonas,
    betaRuns: hydratedProject.betaRuns,
    simulationEngines: hydratedProject.simulationEngines,
    simulationLabs: hydratedProject.simulationLabs,
    simulationReviewers: hydratedProject.simulationReviewers,
    simulationRuns: hydratedProject.simulationRuns,
    taskRequests: hydratedProject.taskRequests,
    taskRuns: hydratedProject.taskRuns,
    taskArtifacts: hydratedProject.taskArtifacts,
    taskRunLogs: hydratedProject.taskRunLogs,
    importJobs: hydratedProject.importJobs,
    promptTemplates: hydratedProject.promptTemplates,
    ragDocuments: hydratedProject.ragDocuments,
    ragChunks: hydratedProject.ragChunks,
    scripts: hydratedProject.scripts,
    storyboards: hydratedProject.storyboards,
    videoPackages: hydratedProject.videoPackages,
    proposals: hydratedProject.proposals,
    proposalHistory: hydratedProject.proposalHistory,
    issues: hydratedProject.issues,
    exports: hydratedProject.exports,
    archivedIds: hydratedProject.archivedIds,
    unreadUpdates: hydratedProject.unreadUpdates,
    metadataFiles: hydratedProject.metadataFiles || [],
    todos: hydratedProject.todos ?? [],
    manuscriptNodes: hydratedProject.manuscriptNodes ?? [],
    currentProject: hydratedProject,
  };
};

const cloneProject = (state: ProjectState, locale?: Locale): NarrativeProject => ({
  metadata: {
    ...(state.currentProject?.metadata || defaultProject.metadata),
    name: state.projectName,
    rootPath: state.projectRoot,
    locale: locale || state.currentProject?.metadata.locale || 'en',
    lastOpenedSceneId: state.selectedEntity.type === 'scene' ? state.selectedEntity.id : state.currentProject?.metadata.lastOpenedSceneId || null,
    lastOpenedBoardId: state.activeGraphBoardId,
    updatedAt: now(),
  },
  characters: state.characters,
  characterTags: state.characterTags,
  candidates: state.candidates,
  timelineBranches: state.timelineBranches,
  timelineEvents: state.timelineEvents,
  relationships: state.relationships,
  chapters: state.chapters,
  scenes: state.scenes,
  worldContainers: state.worldContainers,
  worldItems: state.worldItems,
  worldSettings: state.worldSettings,
  worldMaps: state.worldMaps,
  graphBoards: state.graphBoards,
  betaPersonas: state.betaPersonas,
  betaRuns: state.betaRuns,
  simulationEngines: state.simulationEngines,
  simulationLabs: state.simulationLabs,
  simulationReviewers: state.simulationReviewers,
  simulationRuns: state.simulationRuns,
  taskRequests: state.taskRequests,
  taskRuns: state.taskRuns,
  taskArtifacts: state.taskArtifacts,
  taskRunLogs: state.taskRunLogs,
  importJobs: state.importJobs,
  promptTemplates: state.promptTemplates,
  ragDocuments: state.ragDocuments,
  ragChunks: state.ragChunks,
  ragManifest: state.currentProject?.ragManifest || defaultProject.ragManifest,
  retrievalHistory: state.currentProject?.retrievalHistory || defaultProject.retrievalHistory,
  scripts: state.scripts,
  storyboards: state.storyboards,
  videoPackages: state.videoPackages,
  proposals: state.proposals,
  proposalHistory: state.proposalHistory,
  issues: state.issues,
  exports: state.exports,
  unreadUpdates: state.unreadUpdates,
  archivedIds: state.archivedIds,
  metadataFiles: state.metadataFiles,
  todos: state.todos,
  manuscriptNodes: state.manuscriptNodes,
  uiState: {
    panes: {
      sidebarWidth: useUIStore.getState().sidebarWidth,
      inspectorWidth: useUIStore.getState().inspectorWidth,
      agentDockWidth: useUIStore.getState().agentDockWidth,
      writingOutlineWidth: useUIStore.getState().writingOutlineWidth,
      writingContextWidth: useUIStore.getState().writingContextWidth,
      isSidebarCollapsed: useUIStore.getState().isSidebarCollapsed,
      isAgentDockOpen: useUIStore.getState().isAgentDockOpen,
      isWritingOutlineCollapsed: useUIStore.getState().isWritingOutlineCollapsed,
      isWritingContextCollapsed: useUIStore.getState().isWritingContextCollapsed,
    },
    view: {
      activeGraphBoardId: state.activeGraphBoardId,
      activeTimelineBranchId: state.currentProject?.uiState.view.activeTimelineBranchId || state.timelineBranches[0]?.id || null,
      lastOpenedSceneId: state.selectedEntity.type === 'scene' ? state.selectedEntity.id : state.currentProject?.uiState.view.lastOpenedSceneId || state.scenes[0]?.id || null,
    },
    density: useUIStore.getState().density,
    editorWidth: useUIStore.getState().editorWidth,
    motionLevel: useUIStore.getState().motionLevel,
    experimentalFlags: state.currentProject?.uiState.experimentalFlags || defaultProject.uiState.experimentalFlags,
  },
});

const withDirtyState = <T extends object>(partial: T) => ({ ...partial, saveStatus: 'Unsaved changes' as SaveStatus });
const defaultUi = readUiSettings() || {};
const defaultPaneState = defaultProject.uiState.panes;

export const useUIStore = create<UIState>((set) => ({
  currentActivity: 'workbench',
  sidebarSection: 'inbox',
  locale: defaultUi.locale || 'en',
  density: defaultUi.density || defaultProject.uiState.density,
  editorWidth: defaultUi.editorWidth || defaultProject.uiState.editorWidth,
  motionLevel: defaultUi.motionLevel || defaultProject.uiState.motionLevel,
  isCommandPaletteOpen: false,
  isAgentDockOpen: defaultUi.isAgentDockOpen ?? defaultPaneState.isAgentDockOpen,
  isSidebarCollapsed: defaultUi.isSidebarCollapsed ?? defaultPaneState.isSidebarCollapsed,
  isSettingsOpen: false,
  sidebarWidth: defaultUi.sidebarWidth || defaultPaneState.sidebarWidth,
  inspectorWidth: defaultUi.inspectorWidth || defaultPaneState.inspectorWidth,
  agentDockWidth: defaultUi.agentDockWidth || defaultPaneState.agentDockWidth,
  writingOutlineWidth: defaultUi.writingOutlineWidth || defaultPaneState.writingOutlineWidth,
  writingContextWidth: defaultUi.writingContextWidth || defaultPaneState.writingContextWidth,
  isWritingOutlineCollapsed: defaultUi.isWritingOutlineCollapsed ?? defaultPaneState.isWritingOutlineCollapsed,
  isWritingContextCollapsed: defaultUi.isWritingContextCollapsed ?? defaultPaneState.isWritingContextCollapsed,
  appSettings: defaultAppSettings,
  lastActionStatus: null,
  contextMenu: null,
  agentChatMode: 'general',
  agentChatMessages: [{ id: 'welcome', role: 'assistant' as const, content: 'Hello! I\'m your narrative AI assistant. How can I help with your story today?', timestamp: new Date().toISOString() }],
  setAgentChatMode: (mode) => set({ agentChatMode: mode }),
  addAgentChatMessage: (msg) => set((state) => ({ agentChatMessages: [...state.agentChatMessages, msg] })),
  setActivity: (id) => set({ currentActivity: id }),
  setSidebarSection: (section) => set({ sidebarSection: section }),
  setLocale: (locale) => { persistUiSettings({ locale }); set({ locale }); },
  setDensity: (density) => { persistUiSettings({ density }); set({ density }); },
  setEditorWidth: (editorWidth) => { persistUiSettings({ editorWidth }); set({ editorWidth }); },
  setMotionLevel: (motionLevel) => { persistUiSettings({ motionLevel }); set({ motionLevel }); },
  toggleCommandPalette: (open) => set((state) => ({ isCommandPaletteOpen: typeof open === 'boolean' ? open : !state.isCommandPaletteOpen })),
  toggleAgentDock: (open) => set((state) => { const next = typeof open === 'boolean' ? open : !state.isAgentDockOpen; persistUiSettings({ isAgentDockOpen: next }); return { isAgentDockOpen: next }; }),
  toggleSidebar: (open) => set((state) => { const next = typeof open === 'boolean' ? open : !state.isSidebarCollapsed; persistUiSettings({ isSidebarCollapsed: next }); return { isSidebarCollapsed: next }; }),
  toggleSettings: (open) => set((state) => ({ isSettingsOpen: typeof open === 'boolean' ? open : !state.isSettingsOpen })),
  toggleWritingPane: (panel, open) => set((state) => {
    const key = panel === 'outline' ? 'isWritingOutlineCollapsed' : 'isWritingContextCollapsed';
    const nextCollapsed = typeof open === 'boolean' ? !open : !state[key];
    persistUiSettings({ [key]: nextCollapsed });
    return { [key]: nextCollapsed } as Partial<UIState>;
  }),
  setPanelWidth: (panel, width) => set(() => {
    const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);
    const next =
      panel === 'sidebar' ? { sidebarWidth: clamp(width, 96, 480) } :
      panel === 'inspector' ? { inspectorWidth: clamp(width, 180, 640) } :
      panel === 'agentDock' ? { agentDockWidth: clamp(width, 140, 560) } :
      panel === 'writingOutline' ? { writingOutlineWidth: clamp(width, 120, 560) } :
      { writingContextWidth: clamp(width, 140, 560) };
    persistUiSettings(next);
    return next as Partial<UIState>;
  }),
  resetLayout: () => {
    persistUiSettings(defaultPaneState);
    set({
      ...defaultPaneState,
      density: defaultProject.uiState.density,
      editorWidth: defaultProject.uiState.editorWidth,
      motionLevel: defaultProject.uiState.motionLevel,
    });
  },
  setLastActionStatus: (status) => {
    set({ lastActionStatus: status });
    if (status) setTimeout(() => set({ lastActionStatus: null }), 2600);
  },
  openContextMenu: (contextMenu) => set({ contextMenu }),
  closeContextMenu: () => set({ contextMenu: null }),
  loadAppSettings: async () => {
    const settings = await appSettingsService.load();
    persistUiSettings({
      locale: settings.locale,
      density: settings.density,
      editorWidth: settings.editorWidth,
      motionLevel: settings.motionLevel,
    });
    set({
      appSettings: settings,
      locale: settings.locale,
      density: settings.density,
      editorWidth: settings.editorWidth,
      motionLevel: settings.motionLevel,
    });
  },
  saveAppSettings: async (partial) => {
    const next = await appSettingsService.save({ ...useUIStore.getState().appSettings, ...partial });
    persistUiSettings({
      locale: next.locale,
      density: next.density,
      editorWidth: next.editorWidth,
      motionLevel: next.motionLevel,
    });
    set({
      appSettings: next,
      locale: next.locale,
      density: next.density,
      editorWidth: next.editorWidth,
      motionLevel: next.motionLevel,
    });
  },
  hydrateFromProjectUiState: (uiState) => {
    const next = {
      ...uiState.panes,
      density: uiState.density,
      editorWidth: uiState.editorWidth,
      motionLevel: uiState.motionLevel,
    };
    persistUiSettings(next);
    set(next);
  },
}));

export const useProjectStore = create<ProjectState>((set, get) => ({
  ...deriveState(defaultProject),
  saveStatus: 'Idle',
  selectedEntity: { type: null, id: null },
  setSelectedEntity: (type, id) => set((state) => ({
    selectedEntity: { type, id },
    unreadUpdates: id ? { ...state.unreadUpdates, entities: { ...state.unreadUpdates.entities, [id]: false } } : state.unreadUpdates,
  })),
  createProject: async (input) => {
    const uiLocale = useUIStore.getState().locale;
    set({ saveStatus: 'Saving' });
    const project = projectService.createProject({ name: input?.name || 'Starter Demo Project', rootPath: input?.rootPath, template: input?.template || 'starter-demo', locale: input?.locale || uiLocale });
    useUIStore.getState().hydrateFromProjectUiState(project.uiState);
    set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Saved' });
    useUIStore.getState().setLocale(project.metadata.locale);
    setTimeout(() => get().saveStatus === 'Saved' && set({ saveStatus: 'Idle' }), 1200);
  },
  openProject: async (rootPath) => {
    // Close previous DB if switching projects
    const prevRoot = get().projectRoot;
    if (prevRoot && prevRoot !== rootPath) {
      electronApi.dbClose(prevRoot).catch(() => {});
    }
    set({ saveStatus: 'Saving' });
    const project = projectService.openProject(rootPath);
    useUIStore.getState().hydrateFromProjectUiState(project.uiState);
    set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Saved' });
    useUIStore.getState().setLocale(project.metadata.locale);
    if (rootPath) get().loadMetadata(rootPath);
    // Open/migrate SQLite DB (fire-and-forget; JSON store still drives memory)
    electronApi.dbOpen(rootPath ?? project.metadata.rootPath, project).catch(() => {});
    setTimeout(() => get().saveStatus === 'Saved' && set({ saveStatus: 'Idle' }), 1200);
  },
  saveProject: async () => {
    set({ saveStatus: 'Saving' });
    const savedProject = projectService.saveProject(cloneProject(get(), useUIStore.getState().locale));
    set({ ...deriveState(savedProject), saveStatus: 'Saved' });
    setTimeout(() => get().saveStatus === 'Saved' && set({ saveStatus: 'Idle' }), 1200);
  },
  loadProject: (project) => { useUIStore.getState().hydrateFromProjectUiState(project.uiState); set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Idle' }); },
  setProjectLocale: (locale) => set((state) => ({ currentProject: cloneProject(state, locale), saveStatus: 'Unsaved changes' })),
  syncProjectUiState: () => set((state) => ({ currentProject: cloneProject(state, useUIStore.getState().locale), saveStatus: state.saveStatus === 'Idle' ? 'Unsaved changes' : state.saveStatus })),
  addCharacter: (character) => {
    set((state) => withDirtyState({ characters: [...state.characters, character] }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'characters', character.id, character).catch(() => {});
  },
  updateCharacter: (character) => {
    set((state) => withDirtyState({ characters: state.characters.map((entry) => entry.id === character.id ? character : entry) }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'characters', character.id, character).catch(() => {});
  },
  deleteCharacter: (id) => {
    set((state) => withDirtyState({
      characters: state.characters
        .filter((entry) => entry.id !== id)
        .map((entry) => ({
          ...entry,
          relationshipIds: (entry.relationshipIds ?? []).filter(
            (rid) => !state.relationships.some(
              (rel) => rel.id === rid && (rel.sourceId === id || rel.targetId === id)
            )
          ),
        })),
      relationships: state.relationships.filter(
        (entry) => entry.sourceId !== id && entry.targetId !== id
      ),
    }));
    const { projectRoot } = get();
    if (projectRoot) {
      electronApi.dbDelete(projectRoot, 'characters', id).catch(() => {});
    }
  },
  addCharacterTag: (tag) => set((state) => withDirtyState({ characterTags: [...state.characterTags, tag] })),
  updateCharacterTag: (tag) => set((state) => withDirtyState({ characterTags: state.characterTags.map((entry) => entry.id === tag.id ? tag : entry) })),
  deleteCharacterTag: (tagId) => set((state) => withDirtyState({
    characterTags: state.characterTags.filter((tag) => tag.id !== tagId),
    characters: state.characters.map((character) => ({ ...character, tagIds: character.tagIds.filter((id) => id !== tagId) })),
  })),
  toggleCharacterTagMembership: (tagId, characterId) => set((state) => withDirtyState({
    characterTags: state.characterTags.map((tag) => tag.id !== tagId ? tag : { ...tag, characterIds: tag.characterIds.includes(characterId) ? tag.characterIds.filter((id) => id !== characterId) : [...tag.characterIds, characterId] }),
    characters: state.characters.map((character) => character.id !== characterId ? character : { ...character, tagIds: character.tagIds.includes(tagId) ? character.tagIds.filter((id) => id !== tagId) : [...character.tagIds, tagId] }),
  })),
  confirmCandidate: (candidateId) => {
    let confirmedId: string | null = null;
    set((state) => {
      const candidate = state.candidates.find((entry) => entry.id === candidateId);
      if (!candidate) return state;
      const promoted: Character = { id: candidate.id, name: candidate.name, summary: candidate.summary, background: candidate.background, aliases: [], birthdayText: '', portraitAssetId: null, traits: '', goals: '', fears: '', secrets: '', speechStyle: '', arc: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], importance: 'supporting', groupKey: 'supporting', relationshipIds: [], povInsights: null, statusFlags: { alive: true } };
      confirmedId = promoted.id;
      return withDirtyState({ candidates: state.candidates.filter((entry) => entry.id !== candidateId), characters: [...state.characters, promoted] });
    });
    return confirmedId;
  },
  rejectCandidate: (candidateId) => set((state) => withDirtyState({ candidates: state.candidates.filter((entry) => entry.id !== candidateId) })),
  addTimelineEvent: (event) => set((state) => withDirtyState({ timelineEvents: [...state.timelineEvents, event] })),
  updateTimelineEvent: (event) => set((state) => withDirtyState({ timelineEvents: state.timelineEvents.map((entry) => entry.id === event.id ? event : entry) })),
  deleteTimelineEvent: (id) => set((state) => withDirtyState({
    timelineEvents: state.timelineEvents.filter((entry) => entry.id !== id),
    timelineBranches: state.timelineBranches.map((branch) => {
      const endAnchor = resolveEndAnchor(branch);
      return withResolvedBranchAnchors(
        {
          ...branch,
          forkEventId: branch.forkEventId === id ? null : branch.forkEventId,
          mergeEventId: branch.mergeEventId === id ? null : branch.mergeEventId,
        },
        {
          startAnchor: branch.startAnchor?.eventId === id ? null : branch.startAnchor ?? null,
          endAnchor: endAnchor?.eventId === id ? null : endAnchor,
        },
      );
    }),
  })),
  addTimelineBranch: (branch) => set((state) => withDirtyState({ timelineBranches: [...state.timelineBranches, branch] })),
  updateTimelineBranch: (branch) => set((state) => withDirtyState({ timelineBranches: state.timelineBranches.map((entry) => entry.id === branch.id ? branch : entry) })),
  deleteTimelineBranch: (branchId) => set((state) => {
    const branchEventCount = state.timelineEvents.filter((entry) => entry.branchId === branchId).length;
    // Safer than orphaning: `TimelineEvent.branchId` is currently required across the model, canvas,
    // and persistence layer, so we block deletion until the timeline is empty instead of silently
    // rewriting events into an invalid or hidden state.
    if (branchEventCount > 0) {
      return state;
    }

    const nextBranches = state.timelineBranches
      .filter((entry) => entry.id !== branchId)
      .map((entry, index) =>
        withResolvedBranchAnchors(
          {
            ...entry,
            sortOrder: index,
            parentBranchId: entry.parentBranchId === branchId ? null : entry.parentBranchId,
          },
          {
            startAnchor: entry.startAnchor?.branchId === branchId ? null : entry.startAnchor ?? null,
            endAnchor: resolveEndAnchor(entry)?.branchId === branchId ? null : resolveEndAnchor(entry),
          },
        ),
      );

    return withDirtyState({
      timelineBranches: nextBranches,
      timelineEvents: state.timelineEvents
        .map((entry) => ({
          ...entry,
          sharedBranchIds: (entry.sharedBranchIds || []).filter((sharedBranchId) => sharedBranchId !== branchId),
        })),
    });
  }),
  createTimelineBranch: (mode, anchor) => {
    const state = get();
    const parentBranchId = mode === 'forked' ? anchor?.branchId || state.timelineBranches[0]?.id || null : null;
    const branchId = `branch_${Date.now()}`;
    const anchorStartPos = mode === 'forked' && anchor
      ? buildTimelineEventPositionMap(state.timelineBranches, state.timelineEvents).get(anchor.eventId)
      : undefined;
    const branch: TimelineBranch = {
      id: branchId,
      name: mode === 'independent' ? `Independent Branch ${state.timelineBranches.length + 1}` : `Branch ${state.timelineBranches.length + 1}`,
      description: mode === 'independent' ? 'Independent branch start.' : 'Forked branch.',
      parentBranchId,
      forkEventId: mode === 'forked' ? anchor?.eventId || null : null,
      mergeEventId: null,
      color: ['#f59e0b', '#38bdf8', '#22c55e', '#ef4444', '#a855f7'][state.timelineBranches.length % 5],
      sortOrder: state.timelineBranches.length,
      collapsed: false,
      mode: mode || 'independent',
      startAnchor: mode === 'forked' && anchor ? anchor : null,
      endAnchor: null,
      endMode: 'open',
      mergeTargetBranchId: null,
      anchorStartPos,
      geometry: {
        laneOffset: state.timelineBranches.length * 90,
        bend: 0.25,
        thickness: 1,
      },
    };
    set((current) => withDirtyState({ timelineBranches: [...current.timelineBranches, branch] }));
    return branchId;
  },
  moveTimelineEvent: (eventId, targetBranchId, targetSlot) => set((state) => {
    const moving = state.timelineEvents.find((entry) => entry.id === eventId);
    if (!moving) return state;
    const otherEvents = state.timelineEvents.filter((entry) => entry.id !== eventId);
    const targetEvents = otherEvents
      .filter((entry) => entry.branchId === targetBranchId)
      .sort((a, b) => a.orderIndex - b.orderIndex);
    const insertAt = Math.min(Math.max(targetSlot, 0), targetEvents.length);
    const reorderedTarget = [...targetEvents.slice(0, insertAt), { ...moving, branchId: targetBranchId }, ...targetEvents.slice(insertAt)]
      .map((entry, index) => ({ ...entry, orderIndex: index }));
    const untouched = otherEvents
      .filter((entry) => entry.branchId !== targetBranchId && entry.branchId !== moving.branchId)
      .map((entry) => entry);
    const sourceRemainder = otherEvents
      .filter((entry) => entry.branchId === moving.branchId && moving.branchId !== targetBranchId)
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((entry, index) => ({ ...entry, orderIndex: index }));
    return withDirtyState(
      propagateTimelineAnchorDependencies(
        state.timelineBranches,
        [...untouched, ...sourceRemainder, ...reorderedTarget],
      ),
    );
  }),
  setTimelineBranchGeometry: (branchId, geometry) => set((state) => withDirtyState({
    timelineBranches: state.timelineBranches.map((entry) => entry.id === branchId ? {
      ...entry,
      geometry: {
        laneOffset: geometry?.laneOffset ?? entry.geometry?.laneOffset ?? 0,
        bend: geometry?.bend ?? entry.geometry?.bend ?? 0.25,
        thickness: geometry?.thickness ?? entry.geometry?.thickness ?? 1,
      },
    } : entry),
  })),
  setTimelineBranchAnchors: (branchId, startPos, endPos, anchors) => set((state) => {
    const previousBranch = state.timelineBranches.find((entry) => entry.id === branchId);
    if (!previousBranch) {
      return state;
    }

    const nextBranch = withResolvedBranchAnchors({
      ...previousBranch,
      anchorStartPos: startPos,
      anchorEndPos: endPos,
    }, anchors);

    const nextBranches = state.timelineBranches.map((branch) =>
      branch.id === branchId ? nextBranch : branch
    );
    const nextEvents = remapBranchEventPositions(state.timelineEvents, branchId, previousBranch, nextBranch);

    return withDirtyState(propagateTimelineAnchorDependencies(nextBranches, nextEvents));
  }),
  updateTimelineEventPosition: (eventId, position) => set((state) => withDirtyState(
    propagateTimelineAnchorDependencies(
      state.timelineBranches,
      state.timelineEvents.map((entry) => (entry.id === eventId ? { ...entry, position } : entry)),
    ),
  )),
  addRelationship: (relationship) => set((state) => withDirtyState({
    relationships: [...state.relationships, relationship],
    characters: state.characters.map((character) => character.id === relationship.sourceId || character.id === relationship.targetId ? { ...character, relationshipIds: Array.from(new Set([...(character.relationshipIds || []), relationship.id])) } : character),
  })),
  updateRelationship: (relationship) => set((state) => withDirtyState({ relationships: state.relationships.map((entry) => entry.id === relationship.id ? relationship : entry) })),
  deleteRelationship: (id) => set((state) => withDirtyState({
    relationships: state.relationships.filter((entry) => entry.id !== id),
    characters: state.characters.map((character) => ({ ...character, relationshipIds: (character.relationshipIds || []).filter((entry) => entry !== id) })),
  })),
  addChapter: (chapter) => {
    set((state) => withDirtyState({ chapters: [...state.chapters, chapter] }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'chapters', chapter.id, chapter).catch(() => {});
  },
  updateChapter: (chapter) => {
    set((state) => withDirtyState({ chapters: state.chapters.map((entry) => entry.id === chapter.id ? chapter : entry) }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'chapters', chapter.id, chapter).catch(() => {});
  },
  deleteChapter: (id) => {
    set((state) => withDirtyState({ chapters: state.chapters.filter((entry) => entry.id !== id) }));
    const { projectRoot } = get();
    if (projectRoot) {
      electronApi.dbDelete(projectRoot, 'chapters', id).catch(() => {});
    }
  },
  addScene: (scene) => {
    set((state) => withDirtyState({ scenes: [...state.scenes, scene] }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'scenes', scene.id, scene).catch(() => {});
  },
  updateScene: (scene) => {
    set((state) => withDirtyState({ scenes: state.scenes.map((entry) => entry.id === scene.id ? scene : entry), currentSceneContent: scene.content }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'scenes', scene.id, scene).catch(() => {});
  },
  deleteScene: (id) => {
    set((state) => withDirtyState({
      scenes: state.scenes.filter((entry) => entry.id !== id),
      chapters: state.chapters.map((ch) => ({ ...ch, sceneIds: ch.sceneIds.filter((sid) => sid !== id) })),
    }));
    const { projectRoot } = get();
    if (projectRoot) {
      electronApi.dbDelete(projectRoot, 'scenes', id).catch(() => {});
    }
  },
  updateScript: (script) => set((state) => withDirtyState({ scripts: state.scripts.map((entry) => entry.id === script.id ? script : entry) })),
  addScript: (script) => set((state) => withDirtyState({ scripts: [...state.scripts, script] })),
  addStoryboard: (storyboard) => set((state) => withDirtyState({ storyboards: [...state.storyboards, storyboard] })),
  updateStoryboard: (storyboard) => set((state) => withDirtyState({ storyboards: state.storyboards.map((entry) => entry.id === storyboard.id ? storyboard : entry) })),
  addWorldContainer: (container) => set((state) => withDirtyState({ worldContainers: [...state.worldContainers, container] })),
  updateWorldContainer: (container) => set((state) => withDirtyState({ worldContainers: state.worldContainers.map((entry) => entry.id === container.id ? container : entry) })),
  deleteWorldContainer: (id) => set((state) => withDirtyState({ worldContainers: state.worldContainers.filter((entry) => entry.id !== id), worldItems: state.worldItems.filter((entry) => entry.containerId !== id) })),
  addWorldItem: (item) => set((state) => withDirtyState({ worldItems: [...state.worldItems, item] })),
  updateWorldItem: (item) => set((state) => withDirtyState({ worldItems: state.worldItems.map((entry) => entry.id === item.id ? item : entry) })),
  deleteWorldItem: (id) => set((state) => withDirtyState({ worldItems: state.worldItems.filter((entry) => entry.id !== id) })),
  updateWorldSettings: (worldSettings) => set(() => withDirtyState({ worldSettings })),
  createWorldMap: (map) => set((state) => withDirtyState({ worldMaps: [...state.worldMaps, map] })),
  updateWorldMap: (map) => set((state) => withDirtyState({ worldMaps: state.worldMaps.map((entry) => entry.id === map.id ? map : entry) })),
  addGraphBoard: (board) => set((state) => withDirtyState({ graphBoards: [...state.graphBoards, board], activeGraphBoardId: board.id })),
  updateGraphBoard: (board) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((entry) => entry.id === board.id ? board : entry) })),
  deleteGraphBoard: (boardId) => set((state) => {
    const nextBoards = state.graphBoards.filter((entry) => entry.id !== boardId);
    return withDirtyState({ graphBoards: nextBoards, activeGraphBoardId: nextBoards[0]?.id || null });
  }),
  setActiveGraphBoard: (boardId) => set((state) => withDirtyState({ activeGraphBoardId: boardId, currentProject: state.currentProject ? { ...cloneProject(state), uiState: { ...cloneProject(state).uiState, view: { ...cloneProject(state).uiState.view, activeGraphBoardId: boardId } } } : state.currentProject })),
  addGraphNode: (boardId, node) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, nodes: [...board.nodes, node], selectedNodeIds: [node.id] } : board) })),
  updateGraphNode: (boardId, node) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, nodes: board.nodes.map((entry) => entry.id === node.id ? node : entry) } : board) })),
  addGraphEdge: (boardId, edge) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, edges: [...board.edges, edge] } : board) })),
  deleteGraphNode: (boardId, nodeId) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, nodes: board.nodes.filter((n) => n.id !== nodeId), edges: board.edges.filter((e) => e.sourceId !== nodeId && e.targetId !== nodeId), selectedNodeIds: board.selectedNodeIds.filter((id) => id !== nodeId) } : board) })),
  deleteGraphEdge: (boardId, edgeId) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, edges: board.edges.filter((e) => e.id !== edgeId) } : board) })),
  updateGraphEdge: (boardId, edge) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, edges: board.edges.map((e) => e.id === edge.id ? { ...e, ...edge } : e) } : board) })),
  setGraphBoardView: (boardId, view) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, view } : board) })),
  resolveProposal: (proposalId, status) => set((state) => withDirtyState(projectService.resolveProposal(cloneProject(state, useUIStore.getState().locale), proposalId, status))),
  resolveIssue: (issueId, resolution) => set((state) => withDirtyState({
    issues: state.issues.map((issue) => issue.id === issueId ? { ...issue, status: resolution, visibility: 'history', dismissedAt: new Date().toISOString() } : issue),
  })),
  dismissIssue: (issueId) => set((state) => withDirtyState({
    issues: state.issues.map((issue) => issue.id === issueId ? { ...issue, status: 'ignored', visibility: 'hidden', dismissedAt: new Date().toISOString() } : issue),
  })),
  addProposal: (proposal) => set((state) => withDirtyState({ proposals: [proposal, ...state.proposals], unreadUpdates: { ...state.unreadUpdates, activities: { ...state.unreadUpdates.activities, workbench: true }, sections: { ...state.unreadUpdates.sections, 'workbench.inbox': true }, entities: { ...state.unreadUpdates.entities, [proposal.id]: true } } })),
  addGraphSyncProposal: (title, preview) => set((state) => {
    const proposal: Proposal = {
      id: `proposal_${Date.now()}`,
      title,
      source: 'graph',
      kind: 'entity_update',
      description: 'Generated from graph selection and routed into Workbench.',
      targetEntityType: 'proposal',
      targetEntityId: null,
      targetEntityRefs: [],
      preview,
      reviewPolicy: 'manual_workbench',
      status: 'pending',
      createdAt: now(),
    };
    return withDirtyState({ proposals: [proposal, ...state.proposals], unreadUpdates: { ...state.unreadUpdates, activities: { ...state.unreadUpdates.activities, workbench: true, graph: true }, sections: { ...state.unreadUpdates.sections, 'workbench.inbox': true }, entities: { ...state.unreadUpdates.entities, [proposal.id]: true } } });
  }),
  addExportArtifact: (artifact) => set((state) => withDirtyState({ exports: [artifact, ...state.exports] })),
  addBetaPersona: (persona) => set((state) => withDirtyState({ betaPersonas: [...state.betaPersonas, persona] })),
  updateBetaPersona: (persona) => set((state) => withDirtyState({ betaPersonas: state.betaPersonas.map((entry) => entry.id === persona.id ? persona : entry) })),
  deleteBetaPersona: (personaId) => set((state) => withDirtyState({ betaPersonas: state.betaPersonas.filter((entry) => entry.id !== personaId), betaRuns: state.betaRuns.filter((entry) => entry.personaId !== personaId) })),
  runBetaPersona: (personaId) => set((state) => {
    const persona = state.betaPersonas.find((entry) => entry.id === personaId);
    if (!persona) return state;
    const chapterCount = state.chapters.length || 1;
    const sceneCount = state.scenes.length || 1;
    const eventCount = state.timelineEvents.length || 1;
    const aggregate = {
      engagement: Math.min(96, Math.round(persona.weights.engagement * 0.65 + sceneCount * 2)),
      retention: Math.min(95, Math.round(persona.weights.retention * 0.7 + chapterCount * 4)),
      resonance: Math.min(98, Math.round(persona.weights.resonance * 0.72 + state.characters.length * 3)),
      pacing: Math.min(94, Math.round(persona.weights.pacing * 0.7 + eventCount * 2)),
      consistency: Math.min(97, Math.round(persona.weights.consistency * 0.75 + Math.max(0, 12 - state.issues.length) * 2)),
      highlights: [
        `${persona.name} highlights the strongest tension in ${state.timelineEvents[0]?.title || 'the current outline'}.`,
        `${persona.name} wants tighter payoff around ${state.characters[0]?.name || 'the lead character'}.`,
        `${persona.name} rates the current draft as beta-ready but still hungry for one more aftermath beat.`,
      ],
    };
    const feedback: BetaFeedbackItem[] = [
      { id: `beta_feedback_${Date.now()}_1`, title: `${state.chapters[0]?.title || 'Opening'} pacing`, text: `${persona.name} thinks the transition into the investigative core could breathe for one more paragraph.`, tag: 'Pacing', type: 'constructive' },
      { id: `beta_feedback_${Date.now()}_2`, title: `${state.characters[0]?.name || 'Lead'} emotional beat`, text: `${persona.name} wants clearer emotional consequence after the most visible branch collision.`, tag: 'Resonance', type: 'critical' },
      { id: `beta_feedback_${Date.now()}_3`, title: 'Voice consistency', text: `${persona.name} notes that the dialogue texture is memorable and distinct across the main cast.`, tag: 'Voice', type: 'positive' },
    ];
    const run: BetaRun = { id: `beta_run_${Date.now()}`, personaId, createdAt: now(), aggregate, feedback };
    return withDirtyState({ betaRuns: [run, ...state.betaRuns] });
  }),
  addSimulationEngine: (engine) => set((state) => withDirtyState({ simulationEngines: [...state.simulationEngines, engine] })),
  updateSimulationEngine: (engine) => set((state) => withDirtyState({ simulationEngines: state.simulationEngines.map((entry) => entry.id === engine.id ? engine : entry) })),
  createSimulationLab: (lab) => set((state) => withDirtyState({ simulationLabs: [...state.simulationLabs, lab] })),
  updateSimulationLab: (lab) => set((state) => withDirtyState({ simulationLabs: state.simulationLabs.map((entry) => entry.id === lab.id ? lab : entry) })),
  runSimulationLab: (labId) => set((state) => {
    const lab = state.simulationLabs.find((entry) => entry.id === labId);
    if (!lab) return state;
    const run: SimulationRun = {
      id: `sim_run_${Date.now()}`,
      entityId: labId,
      entityType: 'lab',
      createdAt: now(),
      status: 'completed',
      output: lab.engineIds.map((engineId) => {
        const engine = state.simulationEngines.find((entry) => entry.id === engineId);
        return `${engine?.name || engineId}: placeholder analysis generated.`;
      }).join('\n'),
    };
    return withDirtyState({ simulationRuns: [run, ...state.simulationRuns] });
  }),
  createSimulationReviewer: (reviewer) => set((state) => withDirtyState({ simulationReviewers: [...state.simulationReviewers, reviewer] })),
  updateSimulationReviewer: (reviewer) => set((state) => withDirtyState({ simulationReviewers: state.simulationReviewers.map((entry) => entry.id === reviewer.id ? reviewer : entry) })),
  runSimulationReviewer: (reviewerId) => set((state) => {
    const reviewer = state.simulationReviewers.find((entry) => entry.id === reviewerId);
    if (!reviewer) return state;
    const run: SimulationRun = {
      id: `sim_run_${Date.now()}`,
      entityId: reviewerId,
      entityType: 'reviewer',
      createdAt: now(),
      status: 'completed',
      output: reviewer.engineIds.map((engineId) => {
        const engine = state.simulationEngines.find((entry) => entry.id === engineId);
        return `${engine?.name || engineId}: reviewer output placeholder with scores and issues.`;
      }).join('\n'),
    };
    return withDirtyState({ simulationRuns: [run, ...state.simulationRuns] });
  }),
  runSimulationEngine: (engineId, context) => set((state) => {
    const engine = state.simulationEngines.find((entry) => entry.id === engineId);
    if (!engine) return state;
    const run: SimulationRun = {
      id: `sim_run_${Date.now()}`,
      entityId: context.entityId,
      entityType: context.entityType,
      engineId,
      createdAt: now(),
      status: 'completed',
      output: `${engine.name}: placeholder result for ${context.entityType} ${context.entityId}.`,
    };
    return withDirtyState({ simulationRuns: [run, ...state.simulationRuns] });
  }),
  addTaskRequest: (task) => set((state) => withDirtyState({ taskRequests: [task, ...state.taskRequests] })),
  addTaskRun: (run, artifact) => set((state) => withDirtyState({ taskRuns: [run, ...state.taskRuns], taskArtifacts: artifact ? [artifact, ...state.taskArtifacts] : state.taskArtifacts })),
  updateTaskRun: (id, patch) => set((state) => withDirtyState({ taskRuns: state.taskRuns.map((r) => r.id === id ? { ...r, ...patch } : r) })),
  addImportJob: (job) => set((state) => withDirtyState({ importJobs: [job, ...state.importJobs] })),
  updateImportJob: (job) => set((state) => withDirtyState({ importJobs: state.importJobs.map((entry) => entry.id === job.id ? job : entry) })),
  upsertCharacterPovInsights: (characterId, insights) => set((state) => withDirtyState({
    characters: state.characters.map((character) => character.id === characterId ? { ...character, povInsights: insights } : character),
  })),
  clearUnreadEntity: (entityId) => set((state) => ({ unreadUpdates: { ...state.unreadUpdates, entities: { ...state.unreadUpdates.entities, [entityId]: false } } })),
  clearUnreadActivity: (activityId) => set((state) => ({ unreadUpdates: { ...state.unreadUpdates, activities: { ...state.unreadUpdates.activities, [activityId]: false } } })),
  metadataFiles: [],
  loadMetadata: (projectRoot) => {
    const files = metadataService.loadMetadataIndex(projectRoot);
    set({ metadataFiles: files });
  },
  importMetadataFile: (projectRoot, filePath, meta) => {
    try {
      const file = metadataService.importFile(projectRoot, filePath, meta);
      set((state) => ({ metadataFiles: [...state.metadataFiles, file] }));
    } catch (err) {
      console.error('[metadataService] importFile failed:', err);
    }
  },
  deleteMetadataFile: (projectRoot, fileId) => {
    metadataService.deleteFile(projectRoot, fileId);
    set((state) => ({ metadataFiles: state.metadataFiles.filter((f) => f.id !== fileId) }));
  },
  todos: [],
  createTodo: (item) =>
    set((state) =>
      withDirtyState({
        todos: [
          ...state.todos,
          {
            ...item,
            id: `todo_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
        ],
      })
    ),
  updateTodo: (id, patch) =>
    set((state) =>
      withDirtyState({
        todos: state.todos.map((t) =>
          t.id === id ? { ...t, ...patch, updatedAt: new Date().toISOString() } : t
        ),
      })
    ),
  deleteTodo: (id) =>
    set((state) => withDirtyState({ todos: state.todos.filter((t) => t.id !== id) })),
  manuscriptNodes: [],
  addManuscriptNode: (node) => {
    const id = crypto.randomUUID();
    const newNode: ManuscriptNode = { ...node, id };
    set((state) => withDirtyState({ manuscriptNodes: [...state.manuscriptNodes, newNode] }));
    return newNode;
  },
  updateManuscriptNode: (id, updates) =>
    set((state) =>
      withDirtyState({
        manuscriptNodes: state.manuscriptNodes.map((n) => (n.id === id ? { ...n, ...updates } : n)),
      })
    ),
  deleteManuscriptNode: (id) =>
    set((state) =>
      withDirtyState({
        manuscriptNodes: (() => {
          // Collect all ids to delete (node + all descendants)
          const toDelete = new Set<string>();
          const queue = [id];
          while (queue.length > 0) {
            const current = queue.shift()!;
            toDelete.add(current);
            state.manuscriptNodes
              .filter(n => n.parentId === current)
              .forEach(n => queue.push(n.id));
          }
          return state.manuscriptNodes.filter(n => !toDelete.has(n.id));
        })(),
      })
    ),
  moveManuscriptNode: (id, newParentId, newOrderIndex) => {
    // Guard: newParentId must not be a descendant of id
    if (newParentId !== null) {
      const isDescendant = (ancestorId: string, targetId: string, nodes: ManuscriptNode[]): boolean => {
        let current: string | null = targetId;
        const visited = new Set<string>();
        while (current) {
          if (visited.has(current)) return false; // cycle in existing data — bail
          if (current === ancestorId) return true;
          visited.add(current);
          const node = nodes.find(n => n.id === current);
          if (!node || node.parentId === null) return false;
          current = node.parentId;
        }
        return false;
      };
      const currentNodes = get().manuscriptNodes;
      if (isDescendant(id, newParentId, currentNodes)) {
        console.warn('moveManuscriptNode: cannot move node into its own descendant');
        return;
      }
    }
    set((state) => {
      const node = state.manuscriptNodes.find((n) => n.id === id);
      if (!node) return state;
      const siblings = state.manuscriptNodes
        .filter((n) => n.parentId === newParentId && n.id !== id)
        .sort((a, b) => a.orderIndex - b.orderIndex);
      const insertAt = Math.min(Math.max(newOrderIndex, 0), siblings.length);
      const reordered = [
        ...siblings.slice(0, insertAt),
        { ...node, parentId: newParentId, orderIndex: insertAt },
        ...siblings.slice(insertAt),
      ].map((n, i) => ({ ...n, orderIndex: i }));
      const untouched = state.manuscriptNodes.filter(
        (n) => n.id !== id && n.parentId !== newParentId
      );

      // First pass: combine all nodes with updated parentId/orderIndex
      let nodes = [...untouched, ...reordered];

      // Recalculate depth for the moved subtree
      const calcDepth = (nodeId: string, nodeList: typeof state.manuscriptNodes): number => {
        const n = nodeList.find(x => x.id === nodeId);
        if (!n || n.parentId === null) return 0;
        return calcDepth(n.parentId, nodeList) + 1;
      };

      // Collect all ids in the moved subtree (node + descendants)
      const subtreeIds = new Set<string>();
      const queue = [id];
      while (queue.length > 0) {
        const current = queue.shift()!;
        subtreeIds.add(current);
        nodes.filter(n => n.parentId === current).forEach(n => queue.push(n.id));
      }

      nodes = nodes.map(n =>
        subtreeIds.has(n.id) ? { ...n, depth: calcDepth(n.id, nodes) } : n
      );

      return withDirtyState({ manuscriptNodes: nodes });
    });
  },
  loadManuscriptNodeContent: async (projectRoot, nodeId) => {
    const scope = globalThis as typeof globalThis & { require?: NodeRequire };
    const loader = scope.require;
    if (!loader) return '';
    try {
      const fs = loader('fs') as typeof import('fs');
      const path = loader('path') as typeof import('path');
      const filePath = path.join(projectRoot, 'writing', 'manuscript', `${nodeId}.md`);
      return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
    } catch {
      return '';
    }
  },
  saveManuscriptNodeContent: async (projectRoot, nodeId, content) => {
    const scope = globalThis as typeof globalThis & { require?: NodeRequire };
    const loader = scope.require;
    if (!loader) return;
    try {
      const fs = loader('fs') as typeof import('fs');
      const path = loader('path') as typeof import('path');
      const dir = path.join(projectRoot, 'writing', 'manuscript');
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, `${nodeId}.md`), content, 'utf8');
    } catch (err) {
      console.error('[manuscriptNode] saveManuscriptNodeContent failed:', err);
    }
  },
  // ── W3 Writing Assistant ────────────────────────────────────────────────────
  w3Status: 'idle',
  w3Options: [],
  w3Output: '',
  w3SessionId: null,
  w3Progress: 0,
  w3Error: null,
  startW3: async (payload) => {
    const { projectRoot } = get();
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    set({ w3Status: 'running', w3Error: null, w3Progress: 0 });
    try {
      const result = await electronApi.w3Start({
        projectRoot,
        scene_id: payload.scene_id,
        task: payload.task,
        hitl_mode: payload.hitl_mode,
        metadata_file_id: payload.metadata_file_id,
        api_key: profile?.apiKey ?? '',
        model: modelProfile?.model ?? 'claude-sonnet-4-6',
        endpoint: profile?.endpoint ?? 'https://api.anthropic.com',
      });
      if (result.status === 'waiting') {
        set({ w3Status: 'waiting_selection', w3Options: result.options ?? [], w3SessionId: result.session_id ?? null });
      } else if (result.status === 'done') {
        set({ w3Status: 'done', w3Output: result.output ?? '' });
      } else {
        set({ w3Status: 'error', w3Error: result.error ?? 'Unknown error' });
      }
    } catch (e) {
      set({ w3Status: 'error', w3Error: String(e) });
    }
  },
  selectW3Option: async (index) => {
    const { projectRoot, w3SessionId } = get();
    set({ w3Status: 'running' });
    try {
      const result = await electronApi.w3Select(projectRoot, w3SessionId ?? '', index);
      if (result.status === 'done') {
        set({ w3Status: 'done', w3Output: result.output ?? '' });
      } else {
        set({ w3Status: 'error', w3Error: result.error ?? 'Unknown error' });
      }
    } catch (e) {
      set({ w3Status: 'error', w3Error: String(e) });
    }
  },
  resetW3: () => set({ w3Status: 'idle', w3Options: [], w3Output: '', w3SessionId: null, w3Progress: 0, w3Error: null }),

  // ── W1 Import ─────────────────────────────────────────────────────────────
  w1Status: 'idle',
  w1Progress: 0,
  w1CompletedChunks: 0,
  w1TotalChunks: 0,
  w1Errors: [],
  w1SessionId: null,
  w1ImportMode: 'import_all',
  setW1ImportMode: (mode) => set({ w1ImportMode: mode }),
  startImport: async (payload) => {
    const { projectRoot, w1ImportMode } = get();
    const mode = payload.importMode ?? w1ImportMode;
    set({ w1Status: 'running', w1Progress: 0, w1Errors: [], w1SessionId: null });
    try {
      const result = await electronApi.w1Start({
        projectRoot: projectRoot || payload.projectRoot,
        source_file_path: payload.sourceFilePath,
        import_mode: mode,
      });
      set({ w1SessionId: result.session_id });
      if (result.status === 'error') {
        set({ w1Status: 'error', w1Errors: ['Import failed to start'] });
      }
    } catch (e) {
      set({ w1Status: 'error', w1Errors: [String(e)] });
    }
  },
  cancelImport: async () => {
    const { w1SessionId } = get();
    set({ w1Status: 'cancelled' });
    if (w1SessionId) {
      try { await electronApi.w1Cancel({ session_id: w1SessionId }); } catch { /* already cancelled */ }
    }
  },
  resetImport: () => set({ w1Status: 'idle', w1Progress: 0, w1CompletedChunks: 0, w1TotalChunks: 0, w1Errors: [], w1SessionId: null }),

  // ── W2 Manuscript Sync ────────────────────────────────────────────────────
  w2Status: 'idle',
  w2Progress: 0,
  w2ProposalCount: 0,
  startManuscriptSync: async (payload) => {
    const { projectRoot } = get();
    set({ w2Status: 'running', w2Progress: 0 });
    try {
      await electronApi.w2Start({
        projectRoot: projectRoot || payload.projectRoot,
        mode: payload.mode,
        target_chapter_id: payload.target_chapter_id,
      });
      set({ w2Status: 'done' });
    } catch (e) {
      set({ w2Status: 'error' });
    }
  },

  // ── Entity focus ──────────────────────────────────────────────────────────
  focusEntity: (entityType, entityId) => {
    const activityMap: Record<string, string> = {
      character: 'characters',
      location: 'world',
      item: 'world',
      todo: 'workbench',
      event: 'timeline',
    };
    const activity = activityMap[entityType] || 'workbench';
    set({ currentActivity: activity, selectedEntity: { type: entityType as any, id: entityId } });
  },

  // ── W4 Consistency Check ──────────────────────────────────────────────────
  w4Status: 'idle',
  w4Issues: [],
  w4SeverityCounts: {},
  w4Progress: 0,
  runConsistencyCheck: async (payload) => {
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    const api_key = profile?.apiKey ?? '';
    const model = modelProfile?.model ?? 'deepseek-chat';
    const endpoint = profile?.endpoint ?? 'https://api.deepseek.com/v1';
    set({ w4Status: 'running', w4Progress: 0, w4Issues: [], w4SeverityCounts: {} });
    try {
      const start = await electronApi.w4Start({ ...payload, api_key, model, endpoint });
      if (!start.session_id || start.status === 'error') { set({ w4Status: 'error' }); return; }
      const poll = async () => {
        for (let i = 0; i < 150; i++) {
          await new Promise(r => setTimeout(r, 2000));
          const s = await electronApi.w4Status(payload.projectRoot, start.session_id);
          set({ w4Progress: s.progress });
          if (s.status === 'done' || s.status === 'completed') {
            set({ w4Status: 'done', w4Issues: s.issues, w4SeverityCounts: s.severity_counts, w4Progress: 1 });
            return;
          }
          if (s.status === 'error' || s.status === 'failed') { set({ w4Status: 'error' }); return; }
        }
        set({ w4Status: 'error' });
      };
      await poll();
    } catch { set({ w4Status: 'error' }); }
  },

  // ── W5 Simulation Engine ──────────────────────────────────────────────────
  w5Status: 'idle',
  w5Progress: 0,
  w5ReportMarkdown: '',
  w5EngineResults: {},
  runSimulation: async (payload) => {
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    const api_key = profile?.apiKey ?? '';
    const model = modelProfile?.model ?? 'deepseek-chat';
    const endpoint = profile?.endpoint ?? 'https://api.deepseek.com/v1';
    set({ w5Status: 'running', w5Progress: 0, w5ReportMarkdown: '', w5EngineResults: {} });
    try {
      const start = await electronApi.w5Start({ ...payload, api_key, model, endpoint });
      if (!start.session_id || start.status === 'error') { set({ w5Status: 'error' }); return; }
      const poll = async () => {
        for (let i = 0; i < 150; i++) {
          await new Promise(r => setTimeout(r, 2000));
          const s = await electronApi.w5Status(payload.projectRoot, start.session_id);
          set({ w5Progress: s.progress });
          if (s.status === 'done' || s.status === 'completed') {
            set({ w5Status: 'done', w5ReportMarkdown: s.report_markdown, w5EngineResults: s.engine_results, w5Progress: 1 });
            return;
          }
          if (s.status === 'error' || s.status === 'failed') { set({ w5Status: 'error' }); return; }
        }
        set({ w5Status: 'error' });
      };
      await poll();
    } catch { set({ w5Status: 'error' }); }
  },

  // ── W6 Beta Reader ────────────────────────────────────────────────────────
  w6Status: 'idle',
  w6Progress: 0,
  w6ReportMarkdown: '',
  w6FeedbackItems: [],
  runBetaReader: async (payload) => {
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    const api_key = profile?.apiKey ?? '';
    const model = modelProfile?.model ?? 'deepseek-chat';
    const endpoint = profile?.endpoint ?? 'https://api.deepseek.com/v1';
    set({ w6Status: 'running', w6Progress: 0, w6ReportMarkdown: '', w6FeedbackItems: [] });
    try {
      const start = await electronApi.w6Start({ ...payload, api_key, model, endpoint });
      if (!start.session_id || start.status === 'error') { set({ w6Status: 'error' }); return; }
      const poll = async () => {
        for (let i = 0; i < 150; i++) {
          await new Promise(r => setTimeout(r, 2000));
          const s = await electronApi.w6Status(payload.projectRoot, start.session_id);
          set({ w6Progress: s.progress });
          if (s.status === 'done' || s.status === 'completed') {
            set({ w6Status: 'done', w6ReportMarkdown: s.report_markdown, w6FeedbackItems: s.feedback_items, w6Progress: 1 });
            return;
          }
          if (s.status === 'error' || s.status === 'failed') { set({ w6Status: 'error' }); return; }
        }
        set({ w6Status: 'error' });
      };
      await poll();
    } catch { set({ w6Status: 'error' }); }
  },

  // ── W7 Metadata Ingestion ─────────────────────────────────────────────────
  w7Status: 'idle',
  w7Progress: 0,
  w7CurrentFileId: null,
  ingestMetadata: async (payload) => {
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    const api_key = profile?.apiKey ?? '';
    const model = modelProfile?.model ?? 'deepseek-chat';
    const endpoint = profile?.endpoint ?? 'https://api.deepseek.com/v1';
    set({ w7Status: 'running', w7Progress: 0, w7CurrentFileId: null });
    try {
      const start = await electronApi.metadataIngest({ ...payload, api_key, model, endpoint });
      if (!start.session_id || start.status === 'error') { set({ w7Status: 'error' }); return; }
      set({ w7CurrentFileId: start.file_id });
      const poll = async () => {
        for (let i = 0; i < 150; i++) {
          await new Promise(r => setTimeout(r, 2000));
          const s = await electronApi.metadataStatus(payload.projectRoot, start.session_id);
          set({ w7Progress: s.progress });
          if (s.status === 'done' || s.status === 'completed') {
            set({ w7Status: 'done', w7Progress: 1, w7CurrentFileId: s.file_id || start.file_id });
            return;
          }
          if (s.status === 'error' || s.status === 'failed') { set({ w7Status: 'error' }); return; }
        }
        set({ w7Status: 'error' });
      };
      await poll();
    } catch { set({ w7Status: 'error' }); }
  },

  // ── Orchestrator ──────────────────────────────────────────────────────────
  orchestratorStatus: 'idle',
  orchestratorProgress: 0,
  orchestratorPlan: [],
  orchestratorCurrentStep: 0,
  orchestratorPendingPermission: null,
  orchestratorSessionId: null,
  startOrchestrator: async (payload) => {
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    const api_key = profile?.apiKey ?? '';
    const model = modelProfile?.model ?? 'deepseek-chat';
    const endpoint = profile?.endpoint ?? 'https://api.deepseek.com/v1';
    set({ orchestratorStatus: 'planning', orchestratorProgress: 0, orchestratorPlan: [], orchestratorCurrentStep: 0, orchestratorPendingPermission: null, orchestratorSessionId: null });
    try {
      const start = await electronApi.orchestratorStart({ ...payload, api_key, model, endpoint });
      if (!start.session_id || start.status === 'error') { set({ orchestratorStatus: 'error' }); return; }
      set({ orchestratorSessionId: start.session_id });
      const poll = async () => {
        for (let i = 0; i < 300; i++) {
          await new Promise(r => setTimeout(r, 2000));
          const s = await electronApi.orchestratorStatus(payload.projectRoot, start.session_id);
          set({
            orchestratorProgress: s.progress,
            orchestratorPlan: s.plan ?? [],
            orchestratorCurrentStep: s.current_step,
            orchestratorPendingPermission: s.pending_permission ?? null,
          });
          const st = s.status as string;
          if (st === 'waiting_permission') { set({ orchestratorStatus: 'waiting_permission' }); return; }
          if (st === 'done' || st === 'completed') { set({ orchestratorStatus: 'done', orchestratorProgress: 1 }); return; }
          if (st === 'error' || st === 'failed') { set({ orchestratorStatus: 'error' }); return; }
          if (st === 'executing') { set({ orchestratorStatus: 'executing' }); }
        }
        set({ orchestratorStatus: 'error' });
      };
      await poll();
    } catch { set({ orchestratorStatus: 'error' }); }
  },
  grantPermission: async (projectRoot, stepId) => {
    const { orchestratorSessionId } = get();
    if (!orchestratorSessionId) return;
    await electronApi.orchestratorGrant(projectRoot, stepId, orchestratorSessionId);
    set({ orchestratorStatus: 'executing', orchestratorPendingPermission: null });
    // Resume polling
    const poll = async () => {
      for (let i = 0; i < 300; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const s = await electronApi.orchestratorStatus(projectRoot, orchestratorSessionId);
        set({
          orchestratorProgress: s.progress,
          orchestratorPlan: s.plan ?? [],
          orchestratorCurrentStep: s.current_step,
          orchestratorPendingPermission: s.pending_permission ?? null,
        });
        const st = s.status as string;
        if (st === 'waiting_permission') { set({ orchestratorStatus: 'waiting_permission' }); return; }
        if (st === 'done' || st === 'completed') { set({ orchestratorStatus: 'done', orchestratorProgress: 1 }); return; }
        if (st === 'error' || st === 'failed') { set({ orchestratorStatus: 'error' }); return; }
      }
      set({ orchestratorStatus: 'error' });
    };
    poll();
  },
  denyPermission: async (projectRoot, stepId, reason) => {
    const { orchestratorSessionId } = get();
    if (!orchestratorSessionId) return;
    await electronApi.orchestratorDeny(projectRoot, stepId, orchestratorSessionId, reason);
    set({ orchestratorStatus: 'error', orchestratorPendingPermission: null });
  },
  resetOrchestrator: () => set({
    orchestratorStatus: 'idle',
    orchestratorProgress: 0,
    orchestratorPlan: [],
    orchestratorCurrentStep: 0,
    orchestratorPendingPermission: null,
    orchestratorSessionId: null,
  }),

  searchEntities: (query) => {
    if (!query) return [];
    const loweredQuery = query.toLowerCase();
    const state = get();
    const pushMatches = <T extends { id: string }>(items: T[], type: EntityKind, getLabel: (item: T) => string, description: string | ((item: T) => string)) =>
      items.forEach((item) => {
        const label = getLabel(item);
        if (label.toLowerCase().includes(loweredQuery)) {
          stateResults.push({ id: item.id, type, label, description: typeof description === 'function' ? description(item) : description });
        }
      });
    const stateResults: SearchResult[] = [];
    pushMatches(state.characters, 'character', (item) => item.name, 'Character');
    pushMatches(state.characterTags, 'character_tag', (item) => item.name, 'Tag');
    pushMatches(state.candidates, 'candidate', (item) => item.name, 'Candidate');
    pushMatches(state.timelineEvents, 'timeline_event', (item) => item.title, 'Timeline Event');
    pushMatches(state.timelineBranches, 'timeline_branch', (item) => item.name, 'Timeline Branch');
    pushMatches(state.worldItems, 'world_item', (item) => item.name, (item) => item.type);
    pushMatches(state.proposals, 'proposal', (item) => item.title, 'Workbench Proposal');
    pushMatches(state.scenes, 'scene', (item) => item.title, 'Scene');
    pushMatches(state.scripts, 'script', (item) => item.title, 'Script');
    pushMatches(state.storyboards, 'storyboard', (item) => item.title, 'Storyboard');
    pushMatches(state.importJobs, 'import_job', (item) => item.sourceFileName, 'Import Job');
    pushMatches(state.promptTemplates, 'prompt_template', (item) => item.name, 'Prompt Template');
    pushMatches(state.graphBoards, 'graph_board', (item) => item.name, 'Graph Board');
    pushMatches(state.betaPersonas, 'beta_persona', (item) => item.name, 'Beta Persona');
    return stateResults;
  },
  dbSearchEntities: async (query) => {
    const { projectRoot } = get();
    if (!projectRoot || !query?.trim()) return [];
    return electronApi.dbSearch(projectRoot, query).catch(() => []);
  },
}));
