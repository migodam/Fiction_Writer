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
  ProposalAcceptanceIntent,
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
  WorldCategoryNode,
  WorldItem,
  AppSettings,
} from './models/project';
import { buildBranchControlPoints, cubicBezierPoint, nearestTOnCurve, tFromOrderIndex } from './components/timeline/bezierMath';
import { applyTimelineOperation } from './components/timeline/TimelineOperations';
import { createStarterProject } from './mock/seedProject';
import { projectService } from './services/projectService';
import { appSettingsService, defaultAppSettings } from './services/appSettingsService';
import * as metadataService from './services/metadataService';
import { electronApi } from './services/electronApi';
import type { RuntimeForkResult, W1CustomProfileConfig, W1OrchestratorOverrides, W1PromptProfile } from './services/electronApi';
import type { RuntimeCheckpoint, RuntimeEvent, RuntimeRun, RuntimeUnknownCall, RuntimeUnknownCallDecision } from './components/import-runtime/types';

const UI_SETTINGS_KEY = 'narrative-ide-ui-settings';
const W1_POLL_INTERVAL_MS = 3000;
const W1_SILENT_SPEND_TIMEOUT_MS = 30 * 60 * 1000;
const W1_ABSOLUTE_TIMEOUT_MS = 4 * 60 * 60 * 1000;
const W1_RUNTIME_SSE_MAX_FAILURES = 3;
const W1_RUNTIME_SSE_RECONNECT_MS = 150;

// This ID belongs to one explicit user action. It is safe to retry across an
// uncertain IPC response, but a later click deliberately receives a new ID.
const runtimeDecisionId = (action: 'pause' | 'resume' | 'cancel', attemptId: string) =>
  `runtime:${action}:${attemptId}:${crypto.randomUUID()}`;

// Demo projects use URI roots and must stay renderer-only until a filesystem project is selected.
export const isFilesystemProjectRoot = (projectRoot: unknown): projectRoot is string =>
  typeof projectRoot === 'string' && pathIsAbsolute(projectRoot) && !/^[a-z][a-z0-9+.-]*:\/\//i.test(projectRoot);

const pathIsAbsolute = (projectRoot: string) => projectRoot.startsWith('/');

type W1RuntimeTransport = 'idle' | 'connecting' | 'sse' | 'polling';

interface W1RuntimeStreamHandle {
  projectRoot: string;
  attemptId: string;
  subscriptionId: string;
  unsubscribeEvent: () => void;
  unsubscribeStatus: () => void;
}

let activeW1RuntimeStream: W1RuntimeStreamHandle | null = null;
let w1RuntimeReconnectTimer: ReturnType<typeof setTimeout> | null = null;
let w1RuntimeSubscriptionNonce = 0;

const disposeW1RuntimeStream = () => {
  if (w1RuntimeReconnectTimer) clearTimeout(w1RuntimeReconnectTimer);
  w1RuntimeReconnectTimer = null;
  const active = activeW1RuntimeStream;
  activeW1RuntimeStream = null;
  if (!active) return;
  active.unsubscribeEvent();
  active.unsubscribeStatus();
  void electronApi.runtimeEventStreamUnsubscribe(active.subscriptionId).catch(() => undefined);
};

const mergeRuntimeEvents = (current: RuntimeEvent[], incoming: RuntimeEvent[], cursor: number) => {
  const seenIds = new Set(current.map((event) => event.event_id));
  const seenSequences = new Set(current.map((event) => event.sequence));
  const fresh = incoming
    .filter((event) => Number.isSafeInteger(event.sequence) && event.sequence > 0 && !seenIds.has(event.event_id) && !seenSequences.has(event.sequence))
    .sort((left, right) => left.sequence - right.sequence);
  const events = [...current, ...fresh].sort((left, right) => left.sequence - right.sequence || left.event_id.localeCompare(right.event_id));
  const sequences = new Set(events.map((event) => event.sequence));
  let contiguousSequence = cursor;
  while (sequences.has(contiguousSequence + 1)) contiguousSequence += 1;
  return {
    events,
    sequence: contiguousSequence,
    gap: events.some((event) => event.sequence > contiguousSequence + 1),
  };
};

export const defaultW1CustomProfileConfig: W1CustomProfileConfig = {
  quality_target: 'max',
  chapters_per_window_min: 2,
  chapters_per_window_max: 6,
  max_chapters_per_window: 6,
  character_granularity: 'all',
  event_density: 'scene_level',
  timeline_topology_depth: 'full_dag',
  world_strictness: 'full_attributes',
  validation_strictness: 'per_window',
  rerun_budget: 3,
  max_rerun_iterations: 3,
  judge_pass_threshold: 0.85,
  language_policy: 'normalize_to_source',
  input_window_budget: 32000,
  output_token_budget: 4000,
  extract_relationships: true,
  extract_world: true,
  extract_timeline: true,
};

const buildW1OrchestratorOverrides = (config: W1CustomProfileConfig, enabled = true): W1OrchestratorOverrides => ({
  use_orchestrator: enabled,
  use_supervisor: enabled,
  rerun_budget: config.rerun_budget,
  judge_pass_threshold: config.judge_pass_threshold,
  quality_target: config.quality_target,
  language_policy: config.language_policy,
});

interface W1RuntimeStatus {
  current_tool?: string;
  current_window?: string | number;
  chapter_range?: string | { start?: string; end?: string };
  orchestrator_phase?: string;
  judge_score?: number;
  rerun_reason?: string;
  converge_status?: string;
  judge_artifact_summary?: import('./services/electronApi').W1JudgeArtifactSummary;
  last_activity_message?: string;
  active_api_calls?: number;
  elapsed_seconds?: number;
  idle_seconds?: number;
}

type PanelKind = 'sidebar' | 'inspector' | 'agentDock' | 'writingOutline' | 'writingContext';
export type ContextMenuItem = {
  id: string;
  label: string;
  action: () => void | Promise<void>;
  destructive?: boolean;
  disabled?: boolean;
  disabledReason?: string;
  shortcut?: string;
};
export type ContextMenuState = { x: number; y: number; items: ContextMenuItem[]; returnFocus?: HTMLElement | null } | null;

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
  characterPartitions: string[];
  graphImportanceFilter: string[];           // importance values hidden from graph; [] = show all
  characterGroupCollapsed: Record<string, boolean>;  // sidebar group collapse state
  graphSidebarLinkageEnabled: boolean;       // sidebar collapse drives graph filter when true
  addCharacterPartition: (name: string) => void;
  deleteCharacterPartition: (name: string) => void;
  setGraphImportanceFilter: (filter: string[]) => void;
  setCharacterGroupCollapsed: (collapsed: Record<string, boolean>) => void;
  toggleCharacterGroupCollapsed: (group: string) => void;
  setGraphSidebarLinkageEnabled: (enabled: boolean) => void;
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
  worldCategories: WorldCategoryNode[];
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
  archiveCharacter: (id: string) => void;
  hardDeleteCharacter: (id: string) => void;
  addCharacterTag: (tag: CharacterTag) => void;
  updateCharacterTag: (tag: CharacterTag) => void;
  deleteCharacterTag: (tagId: string) => void;
  toggleCharacterTagMembership: (tagId: string, characterId: string) => void;
  moveCharacterTag: (tagId: string, newParentId: string | null, insertBeforeSiblingId?: string | null) => void;
  toggleCharacterTagCollapsed: (tagId: string) => void;
  addWorldCategory: (node: WorldCategoryNode) => void;
  updateWorldCategory: (node: WorldCategoryNode) => void;
  deleteWorldCategory: (nodeId: string) => void;
  moveWorldCategory: (nodeId: string, newParentId: string | null, insertBeforeSiblingId?: string | null) => void;
  toggleWorldCategoryCollapsed: (nodeId: string) => void;
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
  moveWorldItem: (id: string, containerId: string) => void;
  moveWorldItemToCategory: (itemId: string, newCategory: string, newContainerId: string, newCategoryPath: string[], newCategoryId?: string | null, newParentId?: string | null) => void;
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
  resolveProposals: (proposalIds: string[], status: Proposal['status'], acceptanceIntent?: ProposalAcceptanceIntent) => Promise<void>;
  repairImportPackage: (proposalIds: string[]) => Promise<void>;
  retryImportPackage: (proposalIds: string[]) => Promise<void>;
  resolveAllProposals: (status: Proposal['status']) => Promise<void>;
  resolveIssue: (issueId: string, resolution: 'resolved' | 'ignored') => void;
  dismissIssue: (issueId: string) => void;
  addProposal: (proposal: Proposal) => void;
  addGraphSyncProposal: (title: string, preview: string) => void;
  updatePromptTemplate: (template: PromptTemplate) => void;
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
  deleteSimulationLab: (labId: string) => void;
  deleteSimulationReviewer: (reviewerId: string) => void;
  removeSimulationEngine: (engineId: string) => void;
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
  w1Status: 'idle' | 'running' | 'done' | 'error' | 'cancelled' | 'paused';
  w1Progress: number;
  w1CompletedChunks: number;
  w1TotalChunks: number;
  w1Errors: string[];
  w1CurrentStep: string;
  w1SessionId: string | null;
  w1ImportMode: 'import_content_only' | 'import_all';
  w1ConsoleLog: import('./services/electronApi').ChunkLogEntry[];
  w1ActivityLog: import('./services/electronApi').W1ActivityEntry[];
  w1LastActivityAt: string;
  w1IdleSeconds: number;
  w1ElapsedSeconds: number;
  w1ActiveApiCalls: number;
  w1TokenLedger: import('./services/electronApi').W1TokenLedger | null;
  w1CancelRequested: boolean;
  w1ConnectionWarning: string | null;
  w1Paused: boolean;
  w1BreakpointChunk: number | null;
  w1PromptProfile: W1PromptProfile;
  w1CustomProfileConfig: W1CustomProfileConfig;
  w1OrchestratorOverrides: W1OrchestratorOverrides;
  w1RuntimeStatus: W1RuntimeStatus | null;
  w1ProposalCount: number;
  w1ExtractionCounts: import('./services/electronApi').W1ExtractionCounts | null;
  w1ImportReviewReport: import('./services/electronApi').W1ImportReviewReport | null;
  w1UseSupervisor: boolean;
  w1SupervisorDecisions: unknown[];
  w1GateFailures: unknown[];
  w1SupervisorIteration: number;
  w1RuntimeLineageId: string | null;
  w1RuntimeAttemptId: string | null;
  w1RuntimeProjectRoot: string | null;
  w1RecoverableRuns: RuntimeRun[];
  w1RuntimeEvents: RuntimeEvent[];
  w1RuntimeSequence: number;
  w1RuntimeCheckpoints: RuntimeCheckpoint[];
  w1RuntimeLoading: boolean;
  w1RuntimeError: string | null;
  w1RuntimeGapWarning: boolean;
  w1RuntimeAction: string | null;
  w1RuntimeSelectedAgent: string | null;
  w1RuntimeTransport: W1RuntimeTransport;
  w1RuntimeStreamFailures: number;
  discoverW1Recovery: () => Promise<void>;
  syncW1Runtime: () => Promise<void>;
  connectW1RuntimeStream: () => void;
  disconnectW1RuntimeStream: () => void;
  resumeW1Recovery: (run: RuntimeRun) => Promise<void>;
  decideW1UnknownOutcome: (run: RuntimeRun, call: RuntimeUnknownCall, decision: RuntimeUnknownCallDecision) => Promise<void>;
  pauseW1Runtime: () => Promise<void>;
  cancelW1Runtime: () => Promise<void>;
  forkW1Checkpoint: (checkpointId: string) => Promise<void>;
  setW1RuntimeSelectedAgent: (agentId: string | null) => void;
  setW1ImportMode: (mode: 'import_content_only' | 'import_all') => void;
  setW1PromptProfile: (profile: W1PromptProfile) => void;
  setW1CustomProfileConfig: (patch: Partial<W1CustomProfileConfig>) => void;
  setW1UseSupervisor: (v: boolean) => void;
  setW1Breakpoint: (chunkId: number | null) => Promise<void>;
  resumeW1: () => Promise<void>;
  rewindW1: (toChunkId: number) => Promise<void>;
  startImport: (payload: { projectRoot: string; sourceFilePath: string; importMode?: 'import_content_only' | 'import_all'; customProfileConfig?: W1CustomProfileConfig; orchestratorOverrides?: W1OrchestratorOverrides }) => Promise<void>;
  cancelImport: () => Promise<void>;
  resetImport: () => void;

  // W2 Manuscript Sync state
  w2Status: 'idle' | 'running' | 'done' | 'error';
  w2Progress: number;
  w2ProposalCount: number;
  w2Errors: string[];
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
  orchestratorErrors: string[];
  orchestratorSessionId: string | null;
  startOrchestrator: (payload: { projectRoot: string; goal: string; auto_apply_threshold?: number }) => Promise<void>;
  grantPermission: (projectRoot: string, stepId: string) => Promise<void>;
  denyPermission: (projectRoot: string, stepId: string, reason: string) => Promise<void>;
  resetOrchestrator: () => void;
  // Undo/Redo
  undoStack: UndoEntry[];
  redoStack: UndoEntry[];
  captureUndoSnapshot: (label: string) => void;
  undoAction: () => Promise<void>;
  redoAction: () => Promise<void>;
  pendingUndoTransaction: { label: string; snapshot: ProjectDataSnapshot; undoStack: UndoEntry[] } | null;
  beginUndoTransaction: (label: string) => void;
  commitUndoTransaction: () => void;
  cancelUndoTransaction: () => void;
  rollbackUndoTransaction: () => void;
}

const MAX_UNDO_DEPTH = 20;

type ProjectDataSnapshot = Pick<ProjectState,
  | 'characters' | 'characterTags' | 'characterPartitions' | 'candidates'
  | 'timelineEvents' | 'timelineBranches' | 'relationships'
  | 'chapters' | 'scenes' | 'currentSceneContent'
  | 'worldContainers' | 'worldItems' | 'worldSettings' | 'worldMaps' | 'worldCategories'
  | 'graphBoards' | 'activeGraphBoardId'
  | 'betaPersonas' | 'betaRuns'
  | 'simulationEngines' | 'simulationLabs' | 'simulationReviewers' | 'simulationRuns'
  | 'proposals' | 'proposalHistory' | 'issues' | 'exports' | 'archivedIds'
  | 'todos' | 'manuscriptNodes'
  | 'importJobs' | 'promptTemplates' | 'ragDocuments' | 'ragChunks'
  | 'scripts' | 'storyboards' | 'videoPackages' | 'taskRequests' | 'taskRuns'
  | 'taskArtifacts' | 'taskRunLogs'
>;

interface UndoEntry {
  id: string;
  label: string;
  snapshot: ProjectDataSnapshot;
}

type WorldItemReferenceCleanup = Pick<ProjectDataSnapshot,
  'worldItems' | 'worldMaps' | 'characters' | 'timelineEvents' | 'scenes' | 'scripts' | 'storyboards' | 'graphBoards'
>;

type CharacterReferenceCleanup = Pick<ProjectDataSnapshot,
  'characters' | 'characterTags' | 'relationships' | 'timelineEvents' | 'scenes' | 'worldItems' | 'scripts' | 'storyboards' | 'graphBoards'
>;

const removeCharacterReferences = (state: ProjectState, deletedCharacterId: string): CharacterReferenceCleanup => {
  const deletedRelationshipIds = new Set(
    state.relationships
      .filter((relationship) => relationship.sourceId === deletedCharacterId || relationship.targetId === deletedCharacterId)
      .map((relationship) => relationship.id),
  );

  return {
    characters: state.characters
      .filter((character) => character.id !== deletedCharacterId)
      .map((character) => ({
        ...character,
        relationshipIds: (character.relationshipIds ?? []).filter((relationshipId) => !deletedRelationshipIds.has(relationshipId)),
      })),
    characterTags: state.characterTags.map((tag) => ({
      ...tag,
      characterIds: tag.characterIds.filter((characterId) => characterId !== deletedCharacterId),
    })),
    relationships: state.relationships.filter((relationship) => !deletedRelationshipIds.has(relationship.id)),
    timelineEvents: state.timelineEvents.map((event) => ({
      ...event,
      participantCharacterIds: (event.participantCharacterIds ?? []).filter((characterId) => characterId !== deletedCharacterId),
    })),
    scenes: state.scenes.map((scene) => ({
      ...scene,
      povCharacterId: scene.povCharacterId === deletedCharacterId ? null : scene.povCharacterId,
      linkedCharacterIds: (scene.linkedCharacterIds ?? []).filter((characterId) => characterId !== deletedCharacterId),
    })),
    worldItems: state.worldItems.map((item) => ({
      ...item,
      linkedCharacterIds: (item.linkedCharacterIds ?? []).filter((characterId) => characterId !== deletedCharacterId),
    })),
    scripts: state.scripts.map((script) => ({
      ...script,
      linkedCharacterIds: (script.linkedCharacterIds ?? []).filter((characterId) => characterId !== deletedCharacterId),
    })),
    storyboards: state.storyboards.map((storyboard) => ({
      ...storyboard,
      shots: storyboard.shots.map((shot) => ({
        ...shot,
        linkedCharacterIds: (shot.linkedCharacterIds ?? []).filter((characterId) => characterId !== deletedCharacterId),
      })),
    })),
    graphBoards: state.graphBoards.map((board) => ({
      ...board,
      nodes: board.nodes.map((node) =>
        node.linkedEntityId === deletedCharacterId && (node.linkedEntityType === 'character' || node.kind === 'character_ref')
          ? { ...node, linkedEntityId: null, linkedEntityType: null }
          : node,
      ),
    })),
  };
};

const removeWorldItemReferences = (state: ProjectState, deletedItemIds: Set<string>): WorldItemReferenceCleanup => {
  const deletedMarkerIds = new Set(
    state.worldItems
      .filter((item) => deletedItemIds.has(item.id))
      .flatMap((item) => item.mapMarkers.map((marker) => marker.id)),
  );

  return {
    worldItems: state.worldItems
      .filter((item) => !deletedItemIds.has(item.id))
      .map((item) => ({
        ...item,
        mapMarkers: item.mapMarkers.map((marker) =>
          marker.linkedEntityId && deletedItemIds.has(marker.linkedEntityId)
            ? { ...marker, linkedEntityId: null }
            : marker,
        ),
      })),
    worldMaps: state.worldMaps.map((map) => ({
      ...map,
      markerIds: map.markerIds.filter((markerId) => !deletedMarkerIds.has(markerId)),
    })),
    characters: state.characters.map((character) => ({
      ...character,
      linkedWorldItemIds: character.linkedWorldItemIds.filter((itemId) => !deletedItemIds.has(itemId)),
    })),
    timelineEvents: state.timelineEvents.map((event) => ({
      ...event,
      locationIds: event.locationIds.filter((itemId) => !deletedItemIds.has(itemId)),
      linkedWorldItemIds: event.linkedWorldItemIds.filter((itemId) => !deletedItemIds.has(itemId)),
    })),
    scenes: state.scenes.map((scene) => ({
      ...scene,
      linkedWorldItemIds: scene.linkedWorldItemIds.filter((itemId) => !deletedItemIds.has(itemId)),
    })),
    scripts: state.scripts.map((script) => ({
      ...script,
      linkedWorldItemIds: script.linkedWorldItemIds.filter((itemId) => !deletedItemIds.has(itemId)),
    })),
    storyboards: state.storyboards.map((storyboard) => ({
      ...storyboard,
      shots: storyboard.shots.map((shot) => ({
        ...shot,
        linkedWorldItemIds: shot.linkedWorldItemIds.filter((itemId) => !deletedItemIds.has(itemId)),
      })),
    })),
    graphBoards: state.graphBoards.map((board) => ({
      ...board,
      nodes: board.nodes.map((node) =>
        node.linkedEntityType === 'world_item' && node.linkedEntityId && deletedItemIds.has(node.linkedEntityId)
          ? { ...node, linkedEntityId: null, linkedEntityType: null }
          : node,
      ),
    })),
  };
};

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
    characterPartitions: hydratedProject.characterPartitions ?? ['core', 'major', 'supporting', 'minor', 'ungrouped'],
    graphImportanceFilter: [],
    characterGroupCollapsed: {},
    graphSidebarLinkageEnabled: true,
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
    worldCategories: hydratedProject.worldCategories ?? [],
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
  characterPartitions: state.characterPartitions,
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
  worldCategories: state.worldCategories,
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

const extractSnapshot = (state: ProjectState): ProjectDataSnapshot => ({
  characters: state.characters, characterTags: state.characterTags,
  characterPartitions: state.characterPartitions, candidates: state.candidates,
  timelineEvents: state.timelineEvents, timelineBranches: state.timelineBranches,
  relationships: state.relationships, chapters: state.chapters, scenes: state.scenes,
  currentSceneContent: state.currentSceneContent,
  worldContainers: state.worldContainers, worldItems: state.worldItems,
  worldSettings: state.worldSettings, worldMaps: state.worldMaps, worldCategories: state.worldCategories,
  graphBoards: state.graphBoards, activeGraphBoardId: state.activeGraphBoardId,
  betaPersonas: state.betaPersonas, betaRuns: state.betaRuns,
  simulationEngines: state.simulationEngines, simulationLabs: state.simulationLabs,
  simulationReviewers: state.simulationReviewers, simulationRuns: state.simulationRuns,
  proposals: state.proposals, proposalHistory: state.proposalHistory,
  issues: state.issues, exports: state.exports, archivedIds: state.archivedIds,
  todos: state.todos, manuscriptNodes: state.manuscriptNodes,
  importJobs: state.importJobs, promptTemplates: state.promptTemplates,
  ragDocuments: state.ragDocuments, ragChunks: state.ragChunks,
  scripts: state.scripts, storyboards: state.storyboards, videoPackages: state.videoPackages,
  taskRequests: state.taskRequests, taskRuns: state.taskRuns,
  taskArtifacts: state.taskArtifacts, taskRunLogs: state.taskRunLogs,
});

export const useProjectStore = create<ProjectState>((set, get) => ({
  ...deriveState(defaultProject),
  saveStatus: 'Idle',
  selectedEntity: { type: null, id: null },
  undoStack: [],
  redoStack: [],
  pendingUndoTransaction: null,
  captureUndoSnapshot: (label) => {
    const snapshot = extractSnapshot(get());
    const entry: UndoEntry = { id: crypto.randomUUID(), label, snapshot };
    set((s) => ({
      undoStack: [entry, ...s.undoStack].slice(0, MAX_UNDO_DEPTH),
      redoStack: [],
    }));
  },
  undoAction: async () => {
    const state = get();
    if (state.undoStack.length === 0) return;
    const [entry, ...restUndo] = state.undoStack;
    const redoEntry: UndoEntry = {
      id: crypto.randomUUID(),
      label: entry.label,
      snapshot: extractSnapshot(state),
    };
    set({
      ...entry.snapshot,
      undoStack: restUndo,
      redoStack: [redoEntry, ...state.redoStack].slice(0, MAX_UNDO_DEPTH),
      saveStatus: 'Unsaved changes' as SaveStatus,
    });
    await get().saveProject();
  },
  redoAction: async () => {
    const state = get();
    if (state.redoStack.length === 0) return;
    const [entry, ...restRedo] = state.redoStack;
    const undoEntry: UndoEntry = {
      id: crypto.randomUUID(),
      label: entry.label,
      snapshot: extractSnapshot(state),
    };
    set({
      ...entry.snapshot,
      redoStack: restRedo,
      undoStack: [undoEntry, ...state.undoStack].slice(0, MAX_UNDO_DEPTH),
      saveStatus: 'Unsaved changes' as SaveStatus,
    });
    await get().saveProject();
  },
  beginUndoTransaction: (label) => {
    if (get().pendingUndoTransaction) {
      console.warn('[undo] beginUndoTransaction called while transaction already pending; ignoring');
      return;
    }
    const snapshot = extractSnapshot(get());
    const undoStack = get().undoStack;
    set({ pendingUndoTransaction: { label, snapshot, undoStack } });
  },
  commitUndoTransaction: () => {
    const { pendingUndoTransaction } = get();
    if (!pendingUndoTransaction) return;
    const current = extractSnapshot(get());
    const prev = pendingUndoTransaction.snapshot;
    // Selection is intentionally absent from ProjectDataSnapshot: one gesture commits once.
    const changed = Object.keys(current).some((key) => current[key as keyof ProjectDataSnapshot] !== prev[key as keyof ProjectDataSnapshot]);
    if (!changed) {
      set({ pendingUndoTransaction: null });
      return;
    }
    const entry: UndoEntry = {
      id: crypto.randomUUID(),
      label: pendingUndoTransaction.label,
      snapshot: pendingUndoTransaction.snapshot,
    };
    set({
      undoStack: [entry, ...pendingUndoTransaction.undoStack].slice(0, MAX_UNDO_DEPTH),
      redoStack: [],
      pendingUndoTransaction: null,
    });
  },
  cancelUndoTransaction: () => {
    set({ pendingUndoTransaction: null });
  },
  rollbackUndoTransaction: () => {
    const pending = get().pendingUndoTransaction;
    if (!pending) return;
    set({ ...pending.snapshot, undoStack: pending.undoStack, pendingUndoTransaction: null });
  },
  setSelectedEntity: (type, id) => set((state) => ({
    selectedEntity: { type, id },
    unreadUpdates: id ? { ...state.unreadUpdates, entities: { ...state.unreadUpdates.entities, [id]: false } } : state.unreadUpdates,
  })),
  createProject: async (input) => {
    const uiLocale = useUIStore.getState().locale;
    set({ saveStatus: 'Saving' });
    const project = projectService.createProject({ name: input?.name || 'Starter Demo Project', rootPath: input?.rootPath, template: input?.template || 'starter-demo', locale: input?.locale || uiLocale });
    useUIStore.getState().hydrateFromProjectUiState(project.uiState);
    set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Saved', undoStack: [], redoStack: [], pendingUndoTransaction: null });
    useUIStore.getState().setLocale(project.metadata.locale);
    setTimeout(() => get().saveStatus === 'Saved' && set({ saveStatus: 'Idle' }), 1200);
  },
  openProject: async (rootPath) => {
    // Close previous DB if switching projects
    const prevRoot = get().projectRoot;
    if (isFilesystemProjectRoot(prevRoot) && prevRoot !== rootPath) {
      electronApi.dbClose(prevRoot).catch(() => {});
    }
    set({ saveStatus: 'Saving' });
    const project = await projectService.openProject(rootPath);
    useUIStore.getState().hydrateFromProjectUiState(project.uiState);
    set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Saved', undoStack: [], redoStack: [], pendingUndoTransaction: null });
    useUIStore.getState().setLocale(project.metadata.locale);
    if (rootPath) get().loadMetadata(rootPath);
    const persistedRoot = rootPath ?? project.metadata.rootPath;
    if (isFilesystemProjectRoot(persistedRoot)) {
      // Open/migrate SQLite DB (fire-and-forget; JSON store still drives memory)
      electronApi.dbOpen(persistedRoot, project).catch(() => {});
      electronApi.sidecarSpawn(persistedRoot).catch(() => {});
    }
    setTimeout(() => get().saveStatus === 'Saved' && set({ saveStatus: 'Idle' }), 1200);
  },
  saveProject: async () => {
    set({ saveStatus: 'Saving' });
    const savedProject = projectService.saveProject(cloneProject(get(), useUIStore.getState().locale));
    const { graphImportanceFilter, characterGroupCollapsed, graphSidebarLinkageEnabled } = get();
    set({ ...deriveState(savedProject), graphImportanceFilter, characterGroupCollapsed, graphSidebarLinkageEnabled, saveStatus: 'Saved' });
    setTimeout(() => get().saveStatus === 'Saved' && set({ saveStatus: 'Idle' }), 1200);
  },
  loadProject: (project) => { useUIStore.getState().hydrateFromProjectUiState(project.uiState); set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Idle', undoStack: [], redoStack: [], pendingUndoTransaction: null }); },
  setProjectLocale: (locale) => set((state) => ({ currentProject: cloneProject(state, locale), saveStatus: 'Unsaved changes' })),
  syncProjectUiState: () => set((state) => ({ currentProject: cloneProject(state, useUIStore.getState().locale), saveStatus: state.saveStatus === 'Idle' ? 'Unsaved changes' : state.saveStatus })),
  addCharacter: (character) => {
    get().captureUndoSnapshot('Add character');
    set((state) => withDirtyState({ characters: [...state.characters, character] }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'characters', character.id, character).catch(() => {});
  },
  updateCharacter: (character) => {
    get().captureUndoSnapshot('Edit character');
    set((state) => withDirtyState({ characters: state.characters.map((entry) => entry.id === character.id ? character : entry) }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'characters', character.id, character).catch(() => {});
  },
  deleteCharacter: (id) => {
    get().captureUndoSnapshot('Delete character');
    set((state) => withDirtyState(removeCharacterReferences(state, id)));
    const { projectRoot } = get();
    if (projectRoot) {
      electronApi.dbDelete(projectRoot, 'characters', id).catch(() => {});
    }
  },
  archiveCharacter: (id) => {
    get().captureUndoSnapshot('Archive character');
    set((state) => withDirtyState({
      archivedIds: Array.from(new Set([...state.archivedIds, id])),
    }));
  },
  hardDeleteCharacter: (id) => get().deleteCharacter(id),
  addCharacterTag: (tag) => { get().captureUndoSnapshot('Add tag'); set((state) => withDirtyState({ characterTags: [...state.characterTags, tag] })); },
  updateCharacterTag: (tag) => { get().captureUndoSnapshot('Edit tag'); set((state) => withDirtyState({ characterTags: state.characterTags.map((entry) => entry.id === tag.id ? tag : entry) })); },
  deleteCharacterTag: (tagId) => { get().captureUndoSnapshot('Delete tag'); set((state) => withDirtyState({ characterTags: state.characterTags.filter((tag) => tag.id !== tagId), characters: state.characters.map((character) => ({ ...character, tagIds: character.tagIds.filter((id) => id !== tagId) })) })); },
  addCharacterPartition: (name) => { get().captureUndoSnapshot('Add character group'); set((state) => withDirtyState({ characterPartitions: [...state.characterPartitions, name] })); },
  deleteCharacterPartition: (name) => { get().captureUndoSnapshot('Delete character group'); set((state) => {
    const characters = state.characters.map(c =>
      c.importance === name ? { ...c, importance: 'ungrouped' as const } : c
    );
    return withDirtyState({
      characterPartitions: state.characterPartitions.filter(p => p !== name),
      characters,
    });
  }); },
  setGraphImportanceFilter: (filter) => set({ graphImportanceFilter: filter }),
  setCharacterGroupCollapsed: (collapsed) => set({ characterGroupCollapsed: collapsed }),
  toggleCharacterGroupCollapsed: (group) => set((s) => ({
    characterGroupCollapsed: { ...s.characterGroupCollapsed, [group]: !s.characterGroupCollapsed[group] },
  })),
  setGraphSidebarLinkageEnabled: (enabled) => set({ graphSidebarLinkageEnabled: enabled }),
  toggleCharacterTagMembership: (tagId, characterId) => { get().captureUndoSnapshot('Toggle tag'); set((state) => withDirtyState({
    characterTags: state.characterTags.map((tag) => tag.id !== tagId ? tag : { ...tag, characterIds: tag.characterIds.includes(characterId) ? tag.characterIds.filter((id) => id !== characterId) : [...tag.characterIds, characterId] }),
    characters: state.characters.map((character) => character.id !== characterId ? character : { ...character, tagIds: character.tagIds.includes(tagId) ? character.tagIds.filter((id) => id !== tagId) : [...character.tagIds, tagId] }),
  })); },
  moveCharacterTag: (tagId, newParentId, insertBeforeSiblingId) => set((state) => {
    const isDescendantOfTag = (candidateId: string | null, ancestorId: string, tags: CharacterTag[]): boolean => {
      if (!candidateId) return false;
      if (candidateId === ancestorId) return true;
      const parent = tags.find((t) => t.id === candidateId)?.parentTagId;
      return isDescendantOfTag(parent ?? null, ancestorId, tags);
    };
    if (newParentId && isDescendantOfTag(newParentId, tagId, state.characterTags)) {
      console.warn(`moveCharacterTag: cycle detected — cannot move ${tagId} under ${newParentId}`);
      return state;
    }
    const siblings = state.characterTags
      .filter((t) => t.id !== tagId && (t.parentTagId ?? null) === newParentId)
      .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0));
    const insertIdx = insertBeforeSiblingId ? siblings.findIndex((t) => t.id === insertBeforeSiblingId) : siblings.length;
    const finalIdx = insertIdx < 0 ? siblings.length : insertIdx;
    const updatedTags = state.characterTags.map((tag) => {
      if (tag.id === tagId) return { ...tag, parentTagId: newParentId, sortOrder: finalIdx };
      const sibIdx = siblings.findIndex((s) => s.id === tag.id);
      if (sibIdx >= 0) return { ...tag, sortOrder: sibIdx < finalIdx ? sibIdx : sibIdx + 1 };
      return tag;
    });
    return withDirtyState({ characterTags: updatedTags });
  }),
  toggleCharacterTagCollapsed: (tagId) => set((state) => withDirtyState({
    characterTags: state.characterTags.map((tag) => tag.id !== tagId ? tag : { ...tag, collapsed: !tag.collapsed }),
  })),
  addWorldCategory: (node) => {
    if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Add world category');
    set((state) => withDirtyState({ worldCategories: [...state.worldCategories, node] }));
  },
  updateWorldCategory: (node) => { set((state) => withDirtyState({ worldCategories: state.worldCategories.map((n) => n.id === node.id ? node : n) })); },
  deleteWorldCategory: (nodeId) => { set((state) => withDirtyState({ worldCategories: state.worldCategories.filter((n) => n.id !== nodeId) })); },
  moveWorldCategory: (nodeId, newParentId, insertBeforeSiblingId) => {
    if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Move world category');
    set((state) => {
      const isDescendantOfNode = (candidateId: string | null, ancestorId: string, nodes: WorldCategoryNode[]): boolean => {
        if (!candidateId) return false;
        if (candidateId === ancestorId) return true;
        const parent = nodes.find((n) => n.id === candidateId)?.parentId;
        return isDescendantOfNode(parent ?? null, ancestorId, nodes);
      };
      if (newParentId && isDescendantOfNode(newParentId, nodeId, state.worldCategories)) {
        console.warn(`moveWorldCategory: cycle detected — cannot move ${nodeId} under ${newParentId}`);
        return state;
      }
      const siblings = state.worldCategories
        .filter((n) => n.id !== nodeId && n.parentId === newParentId)
        .sort((a, b) => a.sortOrder - b.sortOrder);
      const insertIdx = insertBeforeSiblingId ? siblings.findIndex((n) => n.id === insertBeforeSiblingId) : siblings.length;
      const finalIdx = insertIdx < 0 ? siblings.length : insertIdx;
      const updatedNodes = state.worldCategories.map((node) => {
        if (node.id === nodeId) return { ...node, parentId: newParentId, sortOrder: finalIdx };
        const sibIdx = siblings.findIndex((s) => s.id === node.id);
        if (sibIdx >= 0) return { ...node, sortOrder: sibIdx < finalIdx ? sibIdx : sibIdx + 1 };
        return node;
      });
      return withDirtyState({ worldCategories: updatedNodes });
    });
  },
  toggleWorldCategoryCollapsed: (nodeId) => set((state) => withDirtyState({
    worldCategories: state.worldCategories.map((n) => n.id !== nodeId ? n : { ...n, collapsed: !n.collapsed }),
  })),
  confirmCandidate: (candidateId) => {
    get().captureUndoSnapshot('Confirm candidate');
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
  rejectCandidate: (candidateId) => { get().captureUndoSnapshot('Reject candidate'); set((state) => withDirtyState({ candidates: state.candidates.filter((entry) => entry.id !== candidateId) })); },
  addTimelineEvent: (event) => { get().captureUndoSnapshot('Add event'); set((state) => withDirtyState({ timelineEvents: [...state.timelineEvents, event] })); },
  updateTimelineEvent: (event) => { get().captureUndoSnapshot('Edit event'); set((state) => withDirtyState({ timelineEvents: state.timelineEvents.map((entry) => entry.id === event.id ? event : entry) })); },
  deleteTimelineEvent: (id) => { get().captureUndoSnapshot('Delete event'); set((state) => withDirtyState({
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
  })); },
  addTimelineBranch: (branch) => { get().captureUndoSnapshot('Add branch'); set((state) => withDirtyState({ timelineBranches: [...state.timelineBranches, branch] })); },
  updateTimelineBranch: (branch) => { get().captureUndoSnapshot('Edit branch'); set((state) => withDirtyState({ timelineBranches: state.timelineBranches.map((entry) => entry.id === branch.id ? branch : entry) })); },
  deleteTimelineBranch: (branchId) => { get().captureUndoSnapshot('Delete branch'); set((state) => {
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
  }); },
  createTimelineBranch: (mode, anchor) => {
    get().captureUndoSnapshot('Create branch');
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
  moveTimelineEvent: (eventId, targetBranchId, targetSlot) => { if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Move event'); set((state) => {
    const { timelineBranches, timelineEvents, warnings } = applyTimelineOperation(
      { timelineBranches: state.timelineBranches, timelineEvents: state.timelineEvents },
      { type: 'move_event', eventId, branchId: targetBranchId, orderIndex: targetSlot },
    );
    if (warnings.length > 0) console.warn('[Timeline] moveTimelineEvent:', warnings);
    return withDirtyState(propagateTimelineAnchorDependencies(timelineBranches, timelineEvents));
  }); },
  setTimelineBranchGeometry: (branchId, geometry) => { if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Adjust branch'); set((state) => {
    const existing = state.timelineBranches.find((b) => b.id === branchId);
    const { timelineBranches, timelineEvents } = applyTimelineOperation(
      { timelineBranches: state.timelineBranches, timelineEvents: state.timelineEvents },
      { type: 'update_branch_geometry', branchId, geometry: {
        laneOffset: geometry?.laneOffset ?? existing?.geometry?.laneOffset ?? 0,
        bend: geometry?.bend ?? existing?.geometry?.bend ?? 0.25,
        thickness: geometry?.thickness ?? existing?.geometry?.thickness ?? 1,
      }},
    );
    return withDirtyState({ timelineBranches, timelineEvents });
  }); },
  // NOTE: endAnchor, endMode, mergeTargetBranchId, mergeEventId are CANONICAL topology fields.
  // They are written to disk via saveProject() and must not be in BRANCH_RUNTIME_FIELDS.
  setTimelineBranchAnchors: (branchId, startPos, endPos, anchors) => { if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Anchor branch'); set((state) => {
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
  }); },
  updateTimelineEventPosition: (eventId, position) => set((state) => withDirtyState(
    propagateTimelineAnchorDependencies(
      state.timelineBranches,
      state.timelineEvents.map((entry) => (entry.id === eventId ? { ...entry, position } : entry)),
    ),
  )),
  addRelationship: (relationship) => { get().captureUndoSnapshot('Add relationship'); set((state) => withDirtyState({
    relationships: [...state.relationships, relationship],
    characters: state.characters.map((character) => character.id === relationship.sourceId || character.id === relationship.targetId ? { ...character, relationshipIds: Array.from(new Set([...(character.relationshipIds || []), relationship.id])) } : character),
  })); },
  updateRelationship: (relationship) => { get().captureUndoSnapshot('Edit relationship'); set((state) => withDirtyState({ relationships: state.relationships.map((entry) => entry.id === relationship.id ? relationship : entry) })); },
  deleteRelationship: (id) => { get().captureUndoSnapshot('Delete relationship'); set((state) => withDirtyState({ relationships: state.relationships.filter((entry) => entry.id !== id), characters: state.characters.map((character) => ({ ...character, relationshipIds: (character.relationshipIds || []).filter((entry) => entry !== id) })) })); },
  addChapter: (chapter) => {
    get().captureUndoSnapshot('Add chapter');
    set((state) => withDirtyState({ chapters: [...state.chapters, chapter] }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'chapters', chapter.id, chapter).catch(() => {});
  },
  updateChapter: (chapter) => {
    get().captureUndoSnapshot('Edit chapter');
    set((state) => withDirtyState({ chapters: state.chapters.map((entry) => entry.id === chapter.id ? chapter : entry) }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'chapters', chapter.id, chapter).catch(() => {});
  },
  deleteChapter: (id) => {
    get().captureUndoSnapshot('Delete chapter');
    set((state) => withDirtyState({ chapters: state.chapters.filter((entry) => entry.id !== id) }));
    const { projectRoot } = get();
    if (projectRoot) {
      electronApi.dbDelete(projectRoot, 'chapters', id).catch(() => {});
    }
  },
  addScene: (scene) => {
    get().captureUndoSnapshot('Add scene');
    set((state) => withDirtyState({ scenes: [...state.scenes, scene] }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'scenes', scene.id, scene).catch(() => {});
  },
  updateScene: (scene) => {
    get().captureUndoSnapshot('Edit scene');
    set((state) => withDirtyState({ scenes: state.scenes.map((entry) => entry.id === scene.id ? scene : entry), currentSceneContent: scene.content }));
    const { projectRoot } = get();
    if (projectRoot) electronApi.dbUpsert(projectRoot, 'scenes', scene.id, scene).catch(() => {});
  },
  deleteScene: (id) => {
    get().captureUndoSnapshot('Delete scene');
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
  addWorldContainer: (container) => { get().captureUndoSnapshot('Add container'); set((state) => withDirtyState({ worldContainers: [...state.worldContainers, container] })); },
  updateWorldContainer: (container) => { get().captureUndoSnapshot('Edit container'); set((state) => withDirtyState({ worldContainers: state.worldContainers.map((entry) => entry.id === container.id ? container : entry) })); },
  deleteWorldContainer: (id) => {
    get().captureUndoSnapshot('Delete container');
    set((state) => {
      const deletedContainerIds = new Set([id]);
      let addedContainer = true;
      while (addedContainer) {
        addedContainer = false;
        for (const container of state.worldContainers) {
          if (container.parentId && deletedContainerIds.has(container.parentId) && !deletedContainerIds.has(container.id)) {
            deletedContainerIds.add(container.id);
            addedContainer = true;
          }
        }
      }
      const deletedItemIds = new Set(
        state.worldItems
          .filter((item) => deletedContainerIds.has(item.folderId ?? item.containerId))
          .map((item) => item.id),
      );
      return withDirtyState({
        worldContainers: state.worldContainers.filter((container) => !deletedContainerIds.has(container.id)),
        ...removeWorldItemReferences(state, deletedItemIds),
      });
    });
  },
  addWorldItem: (item) => { get().captureUndoSnapshot('Add world item'); set((state) => withDirtyState({ worldItems: [...state.worldItems, { ...item, folderId: item.folderId ?? item.containerId }] })); },
  updateWorldItem: (item) => { get().captureUndoSnapshot('Edit world item'); set((state) => withDirtyState({ worldItems: state.worldItems.map((entry) => entry.id === item.id ? { ...item, folderId: item.folderId ?? item.containerId } : entry) })); },
  deleteWorldItem: (id) => {
    get().captureUndoSnapshot('Delete world item');
    set((state) => withDirtyState(removeWorldItemReferences(state, new Set([id]))));
  },
  moveWorldItem: (id, containerId) => {
    if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Move world item');
    set((state) => withDirtyState({
      worldItems: state.worldItems.map((item) => item.id === id ? { ...item, folderId: containerId, containerId } : item),
    }));
  },
  moveWorldItemToCategory: (itemId, newCategory, newContainerId, newCategoryPath, newCategoryId?, newParentId?) => {
    if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Move world item');
    set((state) => withDirtyState({
      worldItems: state.worldItems.map((item) =>
        item.id === itemId
          ? {
              ...item,
              folderId: newContainerId,
              containerId: newContainerId,
              category: newCategory,
              categoryPath: newCategoryPath,
              categoryId: newCategoryId !== undefined ? newCategoryId : (item.categoryId ?? null),
              parentId: newParentId !== undefined ? newParentId : item.parentId,
            }
          : item
      ),
    }));
  },
  updateWorldSettings: (worldSettings) => { get().captureUndoSnapshot('Edit world settings'); set(() => withDirtyState({ worldSettings })); },
  createWorldMap: (map) => set((state) => withDirtyState({ worldMaps: [...state.worldMaps, map] })),
  updateWorldMap: (map) => set((state) => withDirtyState({ worldMaps: state.worldMaps.map((entry) => entry.id === map.id ? map : entry) })),
  addGraphBoard: (board) => { get().captureUndoSnapshot('Add board'); set((state) => withDirtyState({ graphBoards: [...state.graphBoards, board], activeGraphBoardId: board.id })); },
  updateGraphBoard: (board) => { get().captureUndoSnapshot('Edit board'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((entry) => entry.id === board.id ? board : entry) })); },
  deleteGraphBoard: (boardId) => { get().captureUndoSnapshot('Delete board'); set((state) => { const nextBoards = state.graphBoards.filter((entry) => entry.id !== boardId); return withDirtyState({ graphBoards: nextBoards, activeGraphBoardId: nextBoards[0]?.id || null }); }); },
  setActiveGraphBoard: (boardId) => set((state) => withDirtyState({ activeGraphBoardId: boardId, currentProject: state.currentProject ? { ...cloneProject(state), uiState: { ...cloneProject(state).uiState, view: { ...cloneProject(state).uiState.view, activeGraphBoardId: boardId } } } : state.currentProject })),
  addGraphNode: (boardId, node) => { get().captureUndoSnapshot('Add node'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, nodes: [...board.nodes, node], selectedNodeIds: [node.id] } : board) })); },
  updateGraphNode: (boardId, node) => { if (!get().pendingUndoTransaction) get().captureUndoSnapshot('Edit node'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, nodes: board.nodes.map((entry) => entry.id === node.id ? node : entry) } : board) })); },
  addGraphEdge: (boardId, edge) => { get().captureUndoSnapshot('Add edge'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, edges: [...board.edges, edge] } : board) })); },
  deleteGraphNode: (boardId, nodeId) => { get().captureUndoSnapshot('Delete node'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, nodes: board.nodes.filter((n) => n.id !== nodeId), edges: board.edges.filter((e) => e.sourceId !== nodeId && e.targetId !== nodeId), selectedNodeIds: board.selectedNodeIds.filter((id) => id !== nodeId) } : board) })); },
  deleteGraphEdge: (boardId, edgeId) => { get().captureUndoSnapshot('Delete edge'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, edges: board.edges.filter((e) => e.id !== edgeId) } : board) })); },
  updateGraphEdge: (boardId, edge) => { get().captureUndoSnapshot('Edit edge'); set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, edges: board.edges.map((e) => e.id === edge.id ? { ...e, ...edge } : e) } : board) })); },
  setGraphBoardView: (boardId, view) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, view } : board) })),
  resolveProposal: (proposalId, status) => {
    set((state) => withDirtyState(projectService.resolveProposal(cloneProject(state, useUIStore.getState().locale), proposalId, status)));
  },
  resolveProposals: async (proposalIds, status, acceptanceIntent = 'bulk') => {
    const project = await projectService.resolveProposals(cloneProject(get(), useUIStore.getState().locale), proposalIds, status, acceptanceIntent);
    set(withDirtyState(project));
  },
  repairImportPackage: async (proposalIds) => {
    const project = await projectService.repairImportPackage(cloneProject(get(), useUIStore.getState().locale), proposalIds);
    set(withDirtyState(project));
  },
  retryImportPackage: async (proposalIds) => {
    const project = await projectService.retryImportPackage(cloneProject(get(), useUIStore.getState().locale), proposalIds);
    set(withDirtyState(project));
  },
  resolveAllProposals: async (status) => {
    const pending = get().proposals.filter((p) => p.status === 'pending' || !p.status);
    if (!pending.length) return;
    const project = await projectService.resolveProposals(
      cloneProject(get(), useUIStore.getState().locale),
      pending.map((proposal) => proposal.id),
      status,
      'bulk',
    );
    set(withDirtyState(project));
  },
  resolveIssue: (issueId, resolution) => set((state) => withDirtyState({
    issues: state.issues.map((issue) => issue.id === issueId ? { ...issue, status: resolution, visibility: 'history', dismissedAt: new Date().toISOString() } : issue),
  })),
  dismissIssue: (issueId) => set((state) => withDirtyState({
    issues: state.issues.map((issue) => issue.id === issueId ? { ...issue, status: 'ignored', visibility: 'hidden', dismissedAt: new Date().toISOString() } : issue),
  })),
  addProposal: (proposal) => set((state) => withDirtyState({ proposals: [proposal, ...state.proposals], unreadUpdates: { ...state.unreadUpdates, activities: { ...state.unreadUpdates.activities, workbench: true }, sections: { ...state.unreadUpdates.sections, 'workbench.inbox': true }, entities: { ...state.unreadUpdates.entities, [proposal.id]: true } } })),
  updatePromptTemplate: (template) => set((state) => withDirtyState({
    promptTemplates: state.promptTemplates.some(t => t.id === template.id)
      ? state.promptTemplates.map(t => t.id === template.id ? template : t)
      : [...state.promptTemplates, template],
  })),
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
  deleteSimulationLab: (labId) => set((state) => withDirtyState({
    simulationLabs: state.simulationLabs.filter(l => l.id !== labId),
    simulationRuns: state.simulationRuns.filter(r => !(r.entityId === labId && r.entityType === 'lab')),
  })),
  deleteSimulationReviewer: (reviewerId) => set((state) => withDirtyState({
    simulationReviewers: state.simulationReviewers.filter(r => r.id !== reviewerId),
    simulationRuns: state.simulationRuns.filter(r => !(r.entityId === reviewerId && r.entityType === 'reviewer')),
  })),
  removeSimulationEngine: (engineId) => set((state) => withDirtyState({
    simulationEngines: state.simulationEngines.filter(e => e.id !== engineId),
    simulationLabs: state.simulationLabs.map(l => ({ ...l, engineIds: l.engineIds.filter(id => id !== engineId) })),
    simulationReviewers: state.simulationReviewers.map(r => ({ ...r, engineIds: r.engineIds.filter(id => id !== engineId) })),
  })),
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
    get().captureUndoSnapshot('Add node');
    const id = crypto.randomUUID();
    const newNode: ManuscriptNode = { ...node, id };
    set((state) => withDirtyState({ manuscriptNodes: [...state.manuscriptNodes, newNode] }));
    return newNode;
  },
  updateManuscriptNode: (id, updates) => { get().captureUndoSnapshot('Edit node'); set((state) => withDirtyState({ manuscriptNodes: state.manuscriptNodes.map((n) => (n.id === id ? { ...n, ...updates } : n)) })); },
  deleteManuscriptNode: (id) => { get().captureUndoSnapshot('Delete node'); set((state) => withDirtyState({
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
      })); },
  moveManuscriptNode: (id, newParentId, newOrderIndex) => {
    get().captureUndoSnapshot('Move node');
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
    const node = get().manuscriptNodes.find((entry) => entry.id === nodeId);
    const linkedScene = node?.linkedSceneId
      ? get().scenes.find((scene) => scene.id === node.linkedSceneId)
      : null;
    if (!loader) return linkedScene?.content || '';
    try {
      const fs = loader('fs') as typeof import('fs');
      const path = loader('path') as typeof import('path');
      const filePath = path.join(projectRoot, 'writing', 'manuscript', `${nodeId}.md`);
      if (fs.existsSync(filePath)) return fs.readFileSync(filePath, 'utf8');
      if (linkedScene?.content) return linkedScene.content;
      if (node?.linkedSceneId) {
        const scenePath = path.join(projectRoot, 'writing', 'scenes', `${node.linkedSceneId}.md`);
        if (fs.existsSync(scenePath)) return fs.readFileSync(scenePath, 'utf8');
      }
      return '';
    } catch {
      return linkedScene?.content || '';
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
  w1CurrentStep: '',
  w1SessionId: null,
  w1ImportMode: 'import_all',
  w1ConsoleLog: [],
  w1ActivityLog: [],
  w1LastActivityAt: '',
  w1IdleSeconds: 0,
  w1ElapsedSeconds: 0,
  w1ActiveApiCalls: 0,
  w1TokenLedger: null,
  w1CancelRequested: false,
  w1ConnectionWarning: null,
  w1Paused: false,
  w1BreakpointChunk: null,
  w1PromptProfile: 'balanced',
  w1CustomProfileConfig: defaultW1CustomProfileConfig,
  w1OrchestratorOverrides: buildW1OrchestratorOverrides(defaultW1CustomProfileConfig),
  w1RuntimeStatus: null,
  w1ProposalCount: 0,
  w1ExtractionCounts: null,
  w1ImportReviewReport: null,
  w1UseSupervisor: true,
  w1SupervisorDecisions: [],
  w1GateFailures: [],
  w1SupervisorIteration: 0,
  w1RuntimeLineageId: null,
  w1RuntimeAttemptId: null,
  w1RuntimeProjectRoot: null,
  w1RecoverableRuns: [],
  w1RuntimeEvents: [],
  w1RuntimeSequence: 0,
  w1RuntimeCheckpoints: [],
  w1RuntimeLoading: false,
  w1RuntimeError: null,
  w1RuntimeGapWarning: false,
  w1RuntimeAction: null,
  w1RuntimeSelectedAgent: null,
  w1RuntimeTransport: 'idle',
  w1RuntimeStreamFailures: 0,
  setW1ImportMode: (mode) => set({ w1ImportMode: mode }),
  setW1PromptProfile: (profile) => set((state) => {
    const supervisorDefault = true;
    return {
      w1PromptProfile: profile,
      w1UseSupervisor: supervisorDefault,
      w1OrchestratorOverrides: buildW1OrchestratorOverrides(state.w1CustomProfileConfig, supervisorDefault),
    };
  }),
  setW1CustomProfileConfig: (patch) => set((state) => {
    const nextConfig = {
      ...state.w1CustomProfileConfig,
      ...patch,
    };
    nextConfig.max_chapters_per_window = nextConfig.chapters_per_window_max;
    nextConfig.max_rerun_iterations = nextConfig.rerun_budget;
    return {
      w1CustomProfileConfig: nextConfig,
      w1OrchestratorOverrides: buildW1OrchestratorOverrides(nextConfig, true),
    };
  }),
  setW1UseSupervisor: (v) => set({ w1UseSupervisor: v }),
  discoverW1Recovery: async () => {
    const { projectRoot } = get();
    if (!projectRoot) {
      get().disconnectW1RuntimeStream();
      set({ w1RuntimeProjectRoot: null, w1RuntimeLineageId: null, w1RuntimeAttemptId: null, w1RecoverableRuns: [], w1RuntimeEvents: [], w1RuntimeSequence: 0, w1RuntimeCheckpoints: [], w1RuntimeGapWarning: false });
      return;
    }
    const projectChanged = get().w1RuntimeProjectRoot !== projectRoot;
    if (projectChanged) get().disconnectW1RuntimeStream();
    set({ w1RuntimeLoading: true, w1RuntimeError: null });
    const result = await electronApi.runtimeRecoverable(projectRoot).catch(() => ({ runs: [], error: 'sidecar_offline' }));
    const runs = Array.isArray(result.runs) ? result.runs as RuntimeRun[] : [];
    const active = runs.find((run) => run.attempt_id) ?? null;
    const selectedAttemptId = projectChanged ? active?.attempt_id ?? null : get().w1RuntimeAttemptId ?? active?.attempt_id ?? null;
    set({
      w1RecoverableRuns: runs,
      w1RuntimeLoading: false,
      w1RuntimeError: result.error ?? null,
      w1RuntimeProjectRoot: projectRoot,
      w1RuntimeLineageId: projectChanged ? active?.lineage_id ?? null : get().w1RuntimeLineageId ?? active?.lineage_id ?? null,
      w1RuntimeAttemptId: selectedAttemptId,
      ...(projectChanged ? { w1RuntimeEvents: [], w1RuntimeSequence: 0, w1RuntimeCheckpoints: [], w1RuntimeGapWarning: false } : {}),
    });
    if (selectedAttemptId) {
      get().connectW1RuntimeStream();
      await get().syncW1Runtime();
    } else {
      get().disconnectW1RuntimeStream();
    }
  },
  syncW1Runtime: async () => {
    const { projectRoot, w1RuntimeAttemptId, w1RuntimeSequence, w1RuntimeTransport } = get();
    if (!projectRoot || !w1RuntimeAttemptId) return;
    const shouldPollEvents = w1RuntimeTransport === 'polling' || w1RuntimeTransport === 'idle';
    const [eventsResult, checkpointsResult] = await Promise.all([
      shouldPollEvents
        ? electronApi.runtimeEvents(projectRoot, w1RuntimeAttemptId, w1RuntimeSequence).catch(() => ({ events: [], error: 'sidecar_offline' }))
        : Promise.resolve({ events: [] as RuntimeEvent[], error: undefined }),
      electronApi.runtimeCheckpoints(projectRoot, w1RuntimeAttemptId).catch(() => ({ checkpoints: [], error: 'sidecar_offline' })),
    ]);
    const incoming = Array.isArray(eventsResult.events) ? eventsResult.events as RuntimeEvent[] : [];
    set((state) => {
      const merged = mergeRuntimeEvents(state.w1RuntimeEvents, incoming, state.w1RuntimeSequence);
      return {
        w1RuntimeEvents: merged.events,
        w1RuntimeSequence: merged.sequence,
        w1RuntimeCheckpoints: Array.isArray(checkpointsResult.checkpoints) ? checkpointsResult.checkpoints as RuntimeCheckpoint[] : state.w1RuntimeCheckpoints,
        w1RuntimeError: eventsResult.error ?? checkpointsResult.error ?? state.w1RuntimeError,
        w1RuntimeGapWarning: state.w1RuntimeGapWarning || merged.gap,
      };
    });
  },
  connectW1RuntimeStream: () => {
    const { projectRoot, w1RuntimeAttemptId, w1RuntimeSequence, w1RuntimeTransport, w1RuntimeStreamFailures } = get();
    if (!projectRoot || !w1RuntimeAttemptId) return;
    if (activeW1RuntimeStream?.projectRoot === projectRoot && activeW1RuntimeStream.attemptId === w1RuntimeAttemptId) return;
    if (w1RuntimeTransport === 'polling' && w1RuntimeStreamFailures >= W1_RUNTIME_SSE_MAX_FAILURES) return;
    disposeW1RuntimeStream();
    if (!electronApi.runtimeEventStreamSupported()) {
      set({ w1RuntimeTransport: 'polling', w1RuntimeStreamFailures: W1_RUNTIME_SSE_MAX_FAILURES });
      return;
    }

    const subscriptionId = `runtime-${Date.now()}-${++w1RuntimeSubscriptionNonce}`;
    const target = { projectRoot, attemptId: w1RuntimeAttemptId, subscriptionId };
    const restart = (countFailure: boolean) => {
      const state = get();
      if (state.projectRoot !== target.projectRoot || state.w1RuntimeAttemptId !== target.attemptId) return;
      const failures = countFailure ? state.w1RuntimeStreamFailures + 1 : state.w1RuntimeStreamFailures;
      disposeW1RuntimeStream();
      if (failures >= W1_RUNTIME_SSE_MAX_FAILURES) {
        set({ w1RuntimeTransport: 'polling', w1RuntimeStreamFailures: failures });
        void get().syncW1Runtime();
        return;
      }
      set({ w1RuntimeTransport: 'connecting', w1RuntimeStreamFailures: failures });
      w1RuntimeReconnectTimer = setTimeout(() => {
        w1RuntimeReconnectTimer = null;
        get().connectW1RuntimeStream();
      }, countFailure ? W1_RUNTIME_SSE_RECONNECT_MS * Math.max(1, failures) : 0);
    };
    const unsubscribeEvent = electronApi.onRuntimeEvent((message) => {
      if (message.subscription_id !== subscriptionId || message.attempt_id !== w1RuntimeAttemptId) return;
      let gapDetected = false;
      set((state) => {
        const merged = mergeRuntimeEvents(state.w1RuntimeEvents, [message.event as RuntimeEvent], state.w1RuntimeSequence);
        gapDetected = merged.gap;
        return {
          w1RuntimeEvents: merged.events,
          w1RuntimeSequence: merged.sequence,
          w1RuntimeGapWarning: state.w1RuntimeGapWarning || merged.gap,
          w1RuntimeStreamFailures: 0,
          w1RuntimeTransport: 'sse',
        };
      });
      if (gapDetected) restart(false);
    });
    const unsubscribeStatus = electronApi.onRuntimeEventStreamStatus((status) => {
      if (status.subscription_id !== subscriptionId || status.attempt_id !== w1RuntimeAttemptId) return;
      if (status.status === 'open') {
        set({ w1RuntimeTransport: 'sse' });
      } else if (status.status === 'closed') {
        restart(false);
      } else if (status.status === 'error') {
        restart(true);
      }
    });
    activeW1RuntimeStream = { ...target, unsubscribeEvent, unsubscribeStatus };
    set({ w1RuntimeTransport: 'connecting' });
    void electronApi.runtimeEventStreamSubscribe(projectRoot, w1RuntimeAttemptId, w1RuntimeSequence, subscriptionId).then((result) => {
      if (!result.ok && activeW1RuntimeStream?.subscriptionId === subscriptionId) restart(true);
    }).catch(() => {
      if (activeW1RuntimeStream?.subscriptionId === subscriptionId) restart(true);
    });
  },
  disconnectW1RuntimeStream: () => {
    disposeW1RuntimeStream();
    set({ w1RuntimeTransport: 'idle', w1RuntimeStreamFailures: 0 });
  },
  resumeW1Recovery: async (run) => {
    const { projectRoot, w1RuntimeAction } = get();
    const hasUnresolvedUnknownCall = run.unknown_calls?.some((call) => call.decision_state !== 'authorize_retry_once');
    if (!projectRoot || w1RuntimeAction || run.source_compatible === false || !run.attempt_id || hasUnresolvedUnknownCall) return;
    set({ w1RuntimeAction: 'resume' });
    const result: RuntimeRun = await electronApi.runtimeAction(projectRoot, 'resume', run.attempt_id, runtimeDecisionId('resume', run.attempt_id)).catch(() => ({ lineage_id: run.lineage_id, attempt_id: run.attempt_id, status: 'error' }));
    const nextAttemptId = result.attempt_id ?? run.attempt_id;
    if (nextAttemptId !== get().w1RuntimeAttemptId) get().disconnectW1RuntimeStream();
    set({ w1RuntimeAction: null, w1RuntimeLineageId: run.lineage_id, w1RuntimeAttemptId: nextAttemptId, w1RuntimeEvents: nextAttemptId !== run.attempt_id ? [] : get().w1RuntimeEvents, w1RuntimeSequence: nextAttemptId !== run.attempt_id ? 0 : get().w1RuntimeSequence, w1RuntimeGapWarning: false, w1RuntimeStreamFailures: 0, w1RuntimeError: result.status === 'needs_credentials' ? 'needs_credentials' : result.status === 'error' ? 'runtime_action_failed' : null });
    get().connectW1RuntimeStream();
    await get().syncW1Runtime();
  },
  decideW1UnknownOutcome: async (run, call, decision) => {
    const { projectRoot, w1RuntimeAction } = get();
    if (!projectRoot || !run.attempt_id || w1RuntimeAction || call.decision_state !== 'pending') return;

    const pendingAction = `unknown:${decision}:${call.tool_call_id}`;
    set({ w1RuntimeAction: pendingAction, w1RuntimeError: null });
    const decisionResult = await electronApi
      .runtimeDecision(projectRoot, call.decision_key, run.attempt_id, decision)
      .catch(() => ({ error: 'sidecar_offline' }));
    if (decisionResult.error) {
      set({ w1RuntimeAction: null, w1RuntimeError: 'runtime_decision_failed' });
      return;
    }

    // Refresh the durable decision state before any attempt can be resumed.
    await get().discoverW1Recovery();
    if (decision === 'cancel') {
      set({ w1RuntimeAction: null });
      return;
    }

    const refreshedRun = get().w1RecoverableRuns.find((candidate) => candidate.attempt_id === run.attempt_id);
    const allUnknownCallsAuthorized = Boolean(
      refreshedRun?.unknown_calls?.length
      && refreshedRun.unknown_calls.every((unknownCall) => unknownCall.decision_state === 'authorize_retry_once'),
    );
    if (!allUnknownCallsAuthorized) {
      set({ w1RuntimeAction: null });
      return;
    }

    const result: RuntimeRun = await electronApi
      .runtimeAction(projectRoot, 'resume', run.attempt_id, runtimeDecisionId('resume', run.attempt_id))
      .catch(() => ({ lineage_id: run.lineage_id, attempt_id: run.attempt_id, status: 'error' }));
    const nextAttemptId = result.attempt_id ?? run.attempt_id;
    if (nextAttemptId !== get().w1RuntimeAttemptId) get().disconnectW1RuntimeStream();
    set({
      w1RuntimeLineageId: run.lineage_id,
      w1RuntimeAttemptId: nextAttemptId,
      w1RuntimeEvents: nextAttemptId !== run.attempt_id ? [] : get().w1RuntimeEvents,
      w1RuntimeSequence: nextAttemptId !== run.attempt_id ? 0 : get().w1RuntimeSequence,
      w1RuntimeGapWarning: false,
      w1RuntimeStreamFailures: 0,
    });
    get().connectW1RuntimeStream();
    await get().discoverW1Recovery();
    set({
      w1RuntimeAction: null,
      w1RuntimeError: result.status === 'needs_credentials'
        ? 'needs_credentials'
        : result.status === 'error' || result.error
          ? 'runtime_action_failed'
          : null,
    });
  },
  pauseW1Runtime: async () => {
    const { projectRoot, w1RuntimeAttemptId, w1RuntimeAction } = get();
    if (!projectRoot || !w1RuntimeAttemptId || w1RuntimeAction) return;
    set({ w1RuntimeAction: 'pause' });
    await electronApi.runtimeAction(projectRoot, 'pause', w1RuntimeAttemptId, runtimeDecisionId('pause', w1RuntimeAttemptId)).catch(() => null);
    set({ w1RuntimeAction: null });
  },
  cancelW1Runtime: async () => {
    const { projectRoot, w1RuntimeAttemptId, w1RuntimeAction } = get();
    if (!projectRoot || !w1RuntimeAttemptId || w1RuntimeAction) return;
    set({ w1RuntimeAction: 'cancel' });
    await electronApi.runtimeAction(projectRoot, 'cancel', w1RuntimeAttemptId, runtimeDecisionId('cancel', w1RuntimeAttemptId)).catch(() => null);
    set({ w1RuntimeAction: null });
  },
  forkW1Checkpoint: async (checkpointId) => {
    const { projectRoot, w1RuntimeAttemptId, w1RuntimeAction } = get();
    if (!projectRoot || !w1RuntimeAttemptId || w1RuntimeAction) return;
    set({ w1RuntimeAction: 'fork' });
    const decisionId = `fork:${w1RuntimeAttemptId}:${checkpointId}`;
    const result: RuntimeForkResult = await electronApi.runtimeFork(projectRoot, w1RuntimeAttemptId, checkpointId, decisionId).catch(() => ({ attempt: { lineage_id: '', status: 'error' }, parent_attempt_id: w1RuntimeAttemptId }));
    const forkedAttemptId = result.attempt?.attempt_id;
    if (forkedAttemptId) get().disconnectW1RuntimeStream();
    set({ w1RuntimeAction: null, w1RuntimeAttemptId: forkedAttemptId ?? w1RuntimeAttemptId, w1RuntimeSequence: forkedAttemptId ? 0 : get().w1RuntimeSequence, w1RuntimeEvents: forkedAttemptId ? [] : get().w1RuntimeEvents, w1RuntimeGapWarning: false, w1RuntimeError: result.attempt?.status === 'error' ? 'runtime_action_failed' : null });
    get().connectW1RuntimeStream();
    await get().syncW1Runtime();
  },
  setW1RuntimeSelectedAgent: (agentId) => set({ w1RuntimeSelectedAgent: agentId }),
  setW1Breakpoint: async (chunkId) => {
    const { projectRoot, w1SessionId } = get();
    if (!projectRoot || !w1SessionId) return;
    set({ w1BreakpointChunk: chunkId });
    await electronApi.w1SetBreakpoint(projectRoot, w1SessionId, chunkId);
  },
  resumeW1: async () => {
    const { projectRoot, w1SessionId } = get();
    if (!projectRoot || !w1SessionId) return;
    set({ w1Paused: false, w1BreakpointChunk: null });
    await electronApi.w1Resume(projectRoot, w1SessionId);
  },
  rewindW1: async (toChunkId) => {
    const { w1RuntimeAttemptId, w1RuntimeCheckpoints } = get();
    const checkpoint = w1RuntimeCheckpoints.find((entry) => entry.sequence === toChunkId);
    if (w1RuntimeAttemptId && checkpoint) {
      await get().forkW1Checkpoint(checkpoint.checkpoint_id);
      return;
    }
    set({ w1ConnectionWarning: 'Immutable runtime recovery is unavailable for this legacy checkpoint. Start a new import or select a durable runtime checkpoint.' });
  },
  startImport: async (payload) => {
    const { projectRoot, w1ImportMode, w1PromptProfile, w1UseSupervisor, w1CustomProfileConfig, w1OrchestratorOverrides } = get();
    const mode = payload.importMode ?? w1ImportMode;
    const effectiveRoot = projectRoot || payload.projectRoot;
    if (!effectiveRoot) {
      set({ w1Status: 'error', w1Errors: ['No project root — open a project first.'] });
      return;
    }
    // Resolve the active provider/model credentials from settings (same pattern as startW3)
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const providerProfile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    set({
      w1Status: 'running',
      w1Progress: 0,
      w1Errors: [],
      w1SessionId: null,
      w1CurrentStep: '',
      w1ProposalCount: 0,
      w1ImportReviewReport: null,
      w1RuntimeStatus: null,
      w1ConsoleLog: [],
      w1ActivityLog: [],
      w1LastActivityAt: '',
      w1IdleSeconds: 0,
      w1ElapsedSeconds: 0,
      w1ActiveApiCalls: 0,
      w1TokenLedger: null,
      w1CancelRequested: false,
      w1ConnectionWarning: null,
    });
    // Ensure sidecar is alive before calling start
    try { await electronApi.sidecarSpawn(effectiveRoot); } catch { /* best effort */ }
    let sessionId: string | null = null;
    // Retry start up to 3 times with delay (sidecar may still be booting)
    let result: any = null;
    // Product imports always use the quality path. content-only is an explicit
    // deterministic mode and intentionally bypasses extraction orchestration.
    const shouldUseSupervisor = mode === 'import_all';
    const customProfileConfig = payload.customProfileConfig ?? w1CustomProfileConfig;
    const orchestratorOverrides = payload.orchestratorOverrides ?? buildW1OrchestratorOverrides(
      customProfileConfig,
      shouldUseSupervisor,
    );
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        result = await electronApi.w1Start({
          projectRoot: effectiveRoot,
          source_file_path: payload.sourceFilePath,
          import_mode: mode,
          prompt_profile: w1PromptProfile,
          use_supervisor: shouldUseSupervisor,
          use_orchestrator: shouldUseSupervisor,
          custom_profile_config: w1PromptProfile === 'custom'
            ? customProfileConfig
            : ({
                extract_relationships: customProfileConfig.extract_relationships,
                extract_world: customProfileConfig.extract_world,
                extract_timeline: customProfileConfig.extract_timeline,
              } as unknown as W1CustomProfileConfig),
          orchestrator_overrides: shouldUseSupervisor ? orchestratorOverrides : undefined,
          api_key: providerProfile?.apiKey ?? '',
          model: modelProfile?.model ?? 'deepseek-chat',
          endpoint: providerProfile?.endpoint ?? 'https://api.deepseek.com/v1',
        });
        break;
      } catch (e) {
        if (attempt < 2) {
          await new Promise(r => setTimeout(r, 2000));
          continue;
        }
        set({ w1Status: 'error', w1Errors: [String(e)] });
        return;
      }
    }
    try {
      sessionId = result.session_id || null;
      set({ w1SessionId: sessionId });
      if (result.status === 'error') {
        set({ w1Status: 'error', w1Errors: [result.error || 'Import failed to start'] });
        return;
      }
    } catch (e) {
      set({ w1Status: 'error', w1Errors: [String(e)] });
      return;
    }
    // Poll sidecar for progress. Stop only when the run is truly silent: no
    // recent activity, no active API call, and no token/cost movement. Long
    // deep imports can legitimately exceed 30 minutes while still making
    // visible progress.
    let consoleLogOffset = 0;
    let activityLogOffset = 0;
    let consecutivePollFailures = 0;
    const pollStartedAt = Date.now();
    let lastTokenTotal = 0;
    let lastTokenProgressAt = pollStartedAt;
    let lastActivityProgressAt = pollStartedAt;
    const shouldContinuePolling = () => get().w1Status !== 'cancelled';
    let isFirstPoll = true;
    while (shouldContinuePolling()) {
      if (!isFirstPoll) await new Promise(r => setTimeout(r, W1_POLL_INTERVAL_MS));
      isFirstPoll = false;
      const { w1Status: cur } = get();
      if (cur === 'cancelled') return;
      try {
        const s = await electronApi.w1Status(effectiveRoot, sessionId ?? undefined);
        consecutivePollFailures = 0;
        const now = Date.now();
        const tokenTotal = Number(s.token_ledger?.actual_total_tokens ?? 0);
        if (tokenTotal > lastTokenTotal) {
          lastTokenTotal = tokenTotal;
          lastTokenProgressAt = now;
        }
        if ((s.last_activity_message || s.current_tool || s.current_step) && Number(s.idle_seconds ?? 0) < 90) {
          lastActivityProgressAt = now;
        }
        set({
          w1Progress: s.progress ?? 0,
          w1CompletedChunks: s.completed_chunks ?? 0,
          w1TotalChunks: s.total_chunks ?? 0,
          w1Errors: s.errors ?? [],
          w1CurrentStep: s.current_step ?? '',
          w1PromptProfile: s.prompt_profile ?? w1PromptProfile,
          w1ProposalCount: s.proposals_count ?? 0,
          w1ExtractionCounts: s.extraction_counts ?? null,
          w1ImportReviewReport: s.import_review_report ?? null,
          w1LastActivityAt: s.last_activity_at ?? '',
          w1IdleSeconds: s.idle_seconds ?? 0,
          w1ElapsedSeconds: s.elapsed_seconds ?? 0,
          w1ActiveApiCalls: s.active_api_calls ?? 0,
          w1TokenLedger: s.token_ledger ?? null,
          w1CancelRequested: Boolean(s.cancel_requested),
          w1ConnectionWarning: null,
          w1RuntimeStatus: {
            current_tool: s.current_tool,
            current_window: s.current_window,
            chapter_range: s.chapter_range,
            orchestrator_phase: s.orchestrator_phase,
            judge_score: s.judge_score,
            rerun_reason: s.rerun_reason,
            converge_status: s.converge_status,
            judge_artifact_summary: s.judge_artifact_summary,
            last_activity_message: s.last_activity_message,
            active_api_calls: s.active_api_calls,
            elapsed_seconds: s.elapsed_seconds,
            idle_seconds: s.idle_seconds,
          },
        });
        // Also poll console log for real-time chunk detail
        try {
          const console = await electronApi.w1Console(effectiveRoot, sessionId ?? '', consoleLogOffset, activityLogOffset);
          const chunkEntries = console.entries ?? [];
          const activityEntries = console.activity_entries ?? [];
          if (chunkEntries.length > 0) {
            consoleLogOffset += chunkEntries.length;
            set((state) => {
              const seen = new Set(state.w1ConsoleLog.map((entry) => `${entry.chunk_id}:${entry.timestamp}`));
              const fresh = chunkEntries.filter((entry) => !seen.has(`${entry.chunk_id}:${entry.timestamp}`));
              return fresh.length ? { w1ConsoleLog: [...state.w1ConsoleLog, ...fresh] } : {};
            });
          }
          if (activityEntries.length > 0) {
            activityLogOffset += activityEntries.length;
            set((state) => {
              const seen = new Set(state.w1ActivityLog.map((entry) => entry.id));
              const fresh = activityEntries.filter((entry) => !seen.has(entry.id));
              return fresh.length ? { w1ActivityLog: [...state.w1ActivityLog, ...fresh] } : {};
            });
          }
          set({ w1Paused: console.paused, w1BreakpointChunk: console.breakpoint_chunk });
          if (console.paused) {
            set({ w1Status: 'paused' });
            // Keep polling while paused so resume is reflected promptly
          }
        } catch (consoleError) {
          set({ w1ConnectionWarning: `Console activity feed unavailable: ${String(consoleError)}` });
        }
        if (s.status === 'done') {
          set({ w1Status: 'done' });
          // Reload project from disk to surface newly-written proposals in system/inbox.json
          try {
            const { projectRoot } = get();
            if (projectRoot) {
              const freshProject = await projectService.openProject(projectRoot);
              if (freshProject) {
                get().loadProject(freshProject);
              }
            }
          } catch { /* best effort */ }
          return;
        }
        if (s.status === 'error') { set({ w1Status: 'error' }); return; }
        if (s.status === 'cancelled') { set({ w1Status: 'cancelled' }); return; }
        const elapsedMs = now - pollStartedAt;
        const idleMs = Number(s.idle_seconds ?? 0) * 1000;
        const tokenStallMs = now - lastTokenProgressAt;
        const activityStallMs = now - lastActivityProgressAt;
        const hasActiveApiCalls = Number(s.active_api_calls ?? 0) > 0;
        const isSilent =
          !hasActiveApiCalls &&
          idleMs >= W1_SILENT_SPEND_TIMEOUT_MS &&
          tokenStallMs >= W1_SILENT_SPEND_TIMEOUT_MS &&
          activityStallMs >= W1_SILENT_SPEND_TIMEOUT_MS;
        if (elapsedMs >= W1_SILENT_SPEND_TIMEOUT_MS && isSilent) {
          try {
            if (sessionId) await electronApi.w1Cancel({ session_id: sessionId });
          } catch { /* best effort */ }
          set({ w1Status: 'error', w1Errors: ['Import had no activity, no active API call, and no token progress for 30 minutes; it was cancelled to prevent silent spend.'] });
          return;
        }
        if (elapsedMs >= W1_ABSOLUTE_TIMEOUT_MS) {
          try {
            if (sessionId) await electronApi.w1Cancel({ session_id: sessionId });
          } catch { /* best effort */ }
          set({ w1Status: 'error', w1Errors: ['Import exceeded the 4 hour absolute safety limit and was cancelled.'] });
          return;
        }
      } catch (statusError) {
        consecutivePollFailures += 1;
        if (consecutivePollFailures >= 3) {
          set({ w1ConnectionWarning: `Sidecar status polling failed ${consecutivePollFailures} times: ${String(statusError)}` });
        }
      }
    }
  },
  cancelImport: async () => {
    const { w1SessionId } = get();
    set({ w1Status: 'cancelled' });
    if (w1SessionId) {
      try { await electronApi.w1Cancel({ session_id: w1SessionId }); } catch { /* already cancelled */ }
    }
  },
  resetImport: () => set({
    w1Status: 'idle',
    w1Progress: 0,
    w1CompletedChunks: 0,
    w1TotalChunks: 0,
    w1Errors: [],
    w1CurrentStep: '',
    w1SessionId: null,
    w1ConsoleLog: [],
    w1ActivityLog: [],
    w1LastActivityAt: '',
    w1IdleSeconds: 0,
    w1ElapsedSeconds: 0,
    w1ActiveApiCalls: 0,
    w1TokenLedger: null,
    w1CancelRequested: false,
    w1ConnectionWarning: null,
    w1Paused: false,
    w1BreakpointChunk: null,
    w1ProposalCount: 0,
    w1ExtractionCounts: null,
    w1ImportReviewReport: null,
    w1RuntimeStatus: null,
  }),

  // ── W2 Manuscript Sync ────────────────────────────────────────────────────
  w2Status: 'idle',
  w2Progress: 0,
  w2ProposalCount: 0,
  w2Errors: [],
  startManuscriptSync: async (payload) => {
    const { projectRoot } = get();
    const effectiveRoot = projectRoot || payload.projectRoot;
    const appSettings = useUIStore.getState().appSettings;
    const profiles = appSettings?.providerProfiles ?? [];
    const modelProfiles = appSettings?.modelProfiles ?? [];
    const profile = profiles.find((p: { id: string }) => p.id === appSettings?.selectedProviderProfileId) ?? profiles[0] as { apiKey?: string; endpoint?: string } | undefined;
    const modelProfile = modelProfiles.find((m: { id: string }) => m.id === appSettings?.selectedModelProfileId) ?? modelProfiles[0] as { model?: string } | undefined;
    set({ w2Status: 'running', w2Progress: 0, w2ProposalCount: 0, w2Errors: [] });
    try {
      try { await electronApi.sidecarSpawn(effectiveRoot); } catch { /* best effort */ }
      const start = await electronApi.w2Start({
        projectRoot: effectiveRoot,
        mode: payload.mode,
        target_chapter_id: payload.target_chapter_id,
        api_key: profile?.apiKey ?? '',
        model: modelProfile?.model ?? 'deepseek-chat',
        endpoint: profile?.endpoint ?? 'https://api.deepseek.com/v1',
      });
      if (!start.session_id || start.status === 'error') {
        set({ w2Status: 'error', w2Errors: [start.error || 'Manuscript sync failed to start'] });
        return;
      }
      for (let i = 0; i < 150; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const s = await electronApi.w2Status(effectiveRoot, start.session_id);
        set({
          w2Progress: s.progress ?? 0,
          w2ProposalCount: s.proposals_count ?? 0,
          w2Errors: s.errors ?? [],
        });
        if (s.status === 'done' || s.status === 'completed') {
          set({ w2Status: 'done', w2Progress: 1, w2ProposalCount: s.proposals_count ?? 0 });
          try {
            if (effectiveRoot) {
              const freshProject = await projectService.openProject(effectiveRoot);
              if (freshProject) {
                get().loadProject(freshProject);
              }
            }
          } catch { /* best effort */ }
          return;
        }
        if (s.status === 'error' || s.status === 'failed') {
          set({ w2Status: 'error', w2Errors: s.errors?.length ? s.errors : ['Manuscript sync failed'] });
          return;
        }
      }
      set({ w2Status: 'error', w2Errors: ['Manuscript sync timed out'] });
    } catch (e) {
      set({ w2Status: 'error', w2Errors: [String(e)] });
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
    useUIStore.getState().setActivity(activity);
    set({ selectedEntity: { type: entityType as any, id: entityId } });
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
  orchestratorErrors: [],
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
    set({ orchestratorStatus: 'planning', orchestratorProgress: 0, orchestratorPlan: [], orchestratorCurrentStep: 0, orchestratorPendingPermission: null, orchestratorErrors: [], orchestratorSessionId: null });
    try {
      const start = await electronApi.orchestratorStart({ ...payload, api_key, model, endpoint });
      if (!start.session_id || start.status === 'error') { set({ orchestratorStatus: 'error', orchestratorErrors: ['Failed to start W0 orchestrator.'] }); return; }
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
            orchestratorErrors: s.errors ?? [],
          });
          const st = s.status as string;
          if (st === 'waiting_permission') { set({ orchestratorStatus: 'waiting_permission' }); return; }
          if (st === 'done' || st === 'completed') { set({ orchestratorStatus: 'done', orchestratorProgress: 1 }); return; }
          if (st === 'error' || st === 'failed') { set({ orchestratorStatus: 'error' }); return; }
          if (st === 'executing') { set({ orchestratorStatus: 'executing' }); }
        }
        set({ orchestratorStatus: 'error', orchestratorErrors: ['W0 timed out before completion.'] });
      };
      await poll();
    } catch (err) { set({ orchestratorStatus: 'error', orchestratorErrors: [String(err)] }); }
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
          orchestratorErrors: s.errors ?? [],
        });
        const st = s.status as string;
        if (st === 'waiting_permission') { set({ orchestratorStatus: 'waiting_permission' }); return; }
        if (st === 'done' || st === 'completed') { set({ orchestratorStatus: 'done', orchestratorProgress: 1 }); return; }
        if (st === 'error' || st === 'failed') { set({ orchestratorStatus: 'error' }); return; }
      }
      set({ orchestratorStatus: 'error', orchestratorErrors: ['W0 timed out before completion.'] });
    };
    poll();
  },
  denyPermission: async (projectRoot, stepId, reason) => {
    const { orchestratorSessionId } = get();
    if (!orchestratorSessionId) return;
    await electronApi.orchestratorDeny(projectRoot, stepId, orchestratorSessionId, reason);
    set({ orchestratorStatus: 'error', orchestratorPendingPermission: null, orchestratorErrors: [`Permission denied: ${reason}`] });
  },
  resetOrchestrator: () => set({
    orchestratorStatus: 'idle',
    orchestratorProgress: 0,
    orchestratorPlan: [],
    orchestratorCurrentStep: 0,
    orchestratorPendingPermission: null,
    orchestratorErrors: [],
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

if (typeof window !== 'undefined' && (import.meta as any).env?.DEV) {
  (window as any).__narrativeStore = useProjectStore;
}
