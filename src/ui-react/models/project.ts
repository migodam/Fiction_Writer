export const PROJECT_SCHEMA_VERSION = 4;

export type EntityKind =
  | 'character'
  | 'candidate'
  | 'character_tag'
  | 'timeline_event'
  | 'timeline_branch'
  | 'world_item'
  | 'relationship'
  | 'chapter'
  | 'scene'
  | 'world_container'
  | 'proposal'
  | 'issue'
  | 'graph_node'
  | 'graph_board'
  | 'beta_persona'
  | 'task_request'
  | 'task_run'
  | 'task_artifact'
  | 'import_job'
  | 'prompt_template'
  | 'rag_document'
  | 'rag_chunk'
  | 'script'
  | 'storyboard'
  | 'video_package';

export type SaveStatus = 'Idle' | 'Unsaved changes' | 'Saving' | 'Saved' | 'Error';
export type StorageMode = 'memory' | 'nodefs';
export type ProjectTemplate = 'blank' | 'starter-demo';
export type Locale = 'en' | 'zh-CN';
export type ProposalStatus = 'pending' | 'accepted' | 'rejected' | 'archived';
export type IssueStatus = 'open' | 'resolved' | 'ignored';
export type TaskStatus = 'queued' | 'running' | 'awaiting_user_input' | 'completed' | 'failed' | 'canceled';
export type ProposalSource = 'graph' | 'consistency' | 'agent' | 'import' | 'script' | 'video';
export type ProposalKind =
  | 'entity_update'
  | 'import_review'
  | 'metadata_extraction'
  | 'script_generation'
  | 'storyboard_generation'
  | 'video_workflow'
  | 'qa_fix';
export type ReviewPolicy = 'manual_workbench' | 'issue_review' | 'artifact_only';
export type IssueSource = 'consistency' | 'import' | 'qa' | 'agent' | 'video';
export type TaskSource = 'manual' | 'local-cli' | 'langgraph' | 'external-ai';
export type AgentType =
  | 'import-agent'
  | 'metadata-extraction-agent'
  | 'retrieval-agent'
  | 'novel-writing-agent'
  | 'script-writing-agent'
  | 'storyboard-shot-planning-agent'
  | 'video-generation-orchestration-agent'
  | 'qa-consistency-agent';
export type GraphNodeKind =
  | 'free_note'
  | 'character_ref'
  | 'event_ref'
  | 'location_ref'
  | 'world_item_ref'
  | 'image_card'
  | 'group_frame';

export interface EntityReference {
  type: EntityKind;
  id: string;
}

export interface Selection {
  type: EntityKind | null;
  id: string | null;
}

export interface CharacterStatusFlags {
  protagonist?: boolean;
  antagonist?: boolean;
  alive?: boolean;
  deceased?: boolean;
  archived?: boolean;
}

export interface Character {
  id: string;
  name: string;
  summary: string;
  background: string;
  aliases: string[];
  birthdayText: string;
  portraitAssetId?: string | null;
  traits?: string;
  goals?: string;
  fears?: string;
  secrets?: string;
  speechStyle?: string;
  arc?: string;
  tagIds: string[];
  organizationIds: string[];
  linkedSceneIds: string[];
  linkedEventIds: string[];
  linkedWorldItemIds: string[];
  statusFlags: CharacterStatusFlags;
}

export interface CharacterTag {
  id: string;
  name: string;
  color: string;
  description: string;
  characterIds: string[];
}

export interface Candidate {
  id: string;
  name: string;
  background: string;
  summary: string;
}

export interface TimelineBranch {
  id: string;
  name: string;
  description?: string;
  parentBranchId?: string | null;
  forkEventId?: string | null;
  mergeEventId?: string | null;
  color?: string;
  sortOrder: number;
  collapsed?: boolean;
}

export interface TimelineEvent {
  id: string;
  title: string;
  summary: string;
  time?: string;
  branchId: string;
  orderIndex: number;
  locationIds: string[];
  participantCharacterIds: string[];
  linkedSceneIds: string[];
  linkedWorldItemIds: string[];
  tags: string[];
  sharedBranchIds?: string[];
}

export interface Relationship {
  id: string;
  sourceId: string;
  targetId: string;
  type: string;
  description?: string;
  strength?: number;
}

export interface Chapter {
  id: string;
  title: string;
  summary: string;
  goal: string;
  notes: string;
  sceneIds: string[];
  orderIndex: number;
  status: 'draft' | 'revised' | 'final';
}

export interface Scene {
  id: string;
  chapterId: string;
  title: string;
  summary: string;
  content: string;
  orderIndex: number;
  povCharacterId?: string | null;
  linkedCharacterIds: string[];
  linkedEventIds: string[];
  linkedWorldItemIds: string[];
  status: 'draft' | 'revised' | 'final';
}

export interface WorldContainer {
  id: string;
  name: string;
  type: 'notebook' | 'graph' | 'timeline' | 'map';
  isDefault?: boolean;
  isCollapsed?: boolean;
  sortOrder?: number;
}

export interface WorldAttribute {
  key: string;
  value: string;
}

export interface WorldMapMarker {
  id: string;
  label: string;
  x: number;
  y: number;
  linkedEntityId?: string | null;
}

export interface WorldItem {
  id: string;
  containerId: string;
  type: string;
  name: string;
  description: string;
  attributes: WorldAttribute[];
  linkedCharacterIds: string[];
  linkedEventIds: string[];
  linkedSceneIds: string[];
  mapMarkers: WorldMapMarker[];
  assetPath?: string | null;
  tagIds?: string[];
}

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  label: string;
  description: string;
  x: number;
  y: number;
  width: number;
  height: number;
  linkedEntityId?: string | null;
  linkedEntityType?: EntityKind | null;
  imageAssetId?: string | null;
}

export interface GraphEdge {
  id: string;
  sourceId: string;
  targetId: string;
  label: string;
}

export interface GraphBoardView {
  zoom: number;
  panX: number;
  panY: number;
}

export interface GraphBoard {
  id: string;
  name: string;
  description: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  view: GraphBoardView;
  selectedNodeIds: string[];
  sortOrder: number;
}

export interface ProposalOperation {
  op: 'create' | 'update' | 'delete' | 'link' | 'unlink';
  entityType: EntityKind;
  entityId?: string | null;
  fields?: Record<string, unknown>;
}

export interface Proposal {
  id: string;
  title: string;
  source: ProposalSource;
  kind: ProposalKind;
  description: string;
  targetEntityType: EntityKind;
  targetEntityId?: string | null;
  targetEntityRefs?: EntityReference[];
  preview: string;
  proposedOperations?: ProposalOperation[];
  reviewNotes?: string;
  confidence?: number;
  payloadPath?: string | null;
  originTaskRunId?: string | null;
  reviewPolicy: ReviewPolicy;
  status: ProposalStatus;
  createdAt: string;
  resolvedAt?: string;
}

export interface ConsistencyIssue {
  id: string;
  title: string;
  description: string;
  severity: 'high' | 'medium' | 'low';
  status: IssueStatus;
  source: IssueSource;
  referenceIds: EntityReference[];
  originTaskRunId?: string | null;
  suggestedProposalIds?: string[];
  fixSuggestion?: string;
}

export interface ExportArtifact {
  id: string;
  format: 'markdown' | 'html';
  fileName: string;
  path: string | null;
  createdAt: string;
  preview: string;
}

export interface BetaPersona {
  id: string;
  name: string;
  archetype: string;
  profile: string;
  tone: string;
  focusAreas: string[];
  weights: {
    engagement: number;
    retention: number;
    resonance: number;
    pacing: number;
    consistency: number;
  };
}

export interface BetaFeedbackItem {
  id: string;
  title: string;
  text: string;
  tag: string;
  type: 'positive' | 'critical' | 'constructive';
}

export interface BetaAggregateReport {
  engagement: number;
  retention: number;
  resonance: number;
  pacing: number;
  consistency: number;
  highlights: string[];
}

export interface BetaRun {
  id: string;
  personaId: string;
  createdAt: string;
  aggregate: BetaAggregateReport;
  feedback: BetaFeedbackItem[];
}

export interface ImportCandidate {
  id: string;
  title: string;
  summary: string;
  confidence: 'high' | 'medium' | 'low';
  contentPath?: string | null;
}

export interface ImportJob {
  id: string;
  sourceFileName: string;
  sourcePath: string | null;
  sourceFormat: 'txt' | 'md' | 'docx';
  status: TaskStatus;
  stage: 'queued' | 'copied' | 'parsed' | 'canonical_written' | 'proposal_generated' | 'indexed' | 'failed';
  segmentationConfidence: 'high' | 'medium' | 'low';
  createdAt: string;
  updatedAt: string;
  taskRequestId?: string | null;
  taskRunId?: string | null;
  canonicalChapterIds: string[];
  canonicalSceneIds: string[];
  chapterCandidates: ImportCandidate[];
  sceneCandidates: ImportCandidate[];
  proposalIds: string[];
  issueIds: string[];
  notes: string[];
}

export interface TaskRunLogRef {
  taskRunId: string;
  path: string | null;
  entryCount: number;
}

export interface TaskRunFailure {
  code: string;
  message: string;
  retryable: boolean;
  details?: string;
}

export interface AwaitingUserInputPayload {
  prompt: string;
  fields: string[];
  reason: string;
}

export interface TaskRequest {
  id: string;
  title: string;
  taskType: string;
  agentType: AgentType;
  source: TaskSource;
  status: TaskStatus;
  prompt: string;
  input: Record<string, unknown>;
  contextScope?: Record<string, unknown>;
  targetIds: EntityReference[];
  reviewPolicy: ReviewPolicy;
  createdAt: string;
}

export interface TaskArtifact {
  id: string;
  taskRunId: string;
  type:
    | 'log'
    | 'proposal-batch'
    | 'issue-batch'
    | 'report'
    | 'patch-preview'
    | 'import-manifest'
    | 'context-package'
    | 'script-draft'
    | 'storyboard'
    | 'video-package'
    | 'provider-payload';
  summary: string;
  path: string | null;
  mimeType?: string;
  entityRefs?: EntityReference[];
}

export interface TaskRun {
  id: string;
  taskRequestId: string;
  status: TaskStatus;
  executor: TaskSource;
  adapter: string;
  attempt: number;
  startedAt: string;
  heartbeatAt?: string;
  finishedAt?: string;
  summary: string;
  artifactIds: string[];
  failure?: TaskRunFailure;
  awaitingUserInput?: AwaitingUserInputPayload | null;
}

export interface PromptTemplateInputField {
  name: string;
  description: string;
  required: boolean;
}

export interface PromptTemplateOutputField {
  name: string;
  description: string;
  required: boolean;
}

export interface PromptTemplateSlot {
  token: string;
  description: string;
  example: string;
}

export interface PromptTemplate {
  id: string;
  name: string;
  agentType: AgentType;
  purpose: string;
  inputContract: PromptTemplateInputField[];
  outputContract: PromptTemplateOutputField[];
  reviewPolicy: ReviewPolicy;
  promptTemplate: string;
  userCustomPromptSlot: string;
  modelHints: string[];
  version: number;
  promptTemplateSlots: PromptTemplateSlot[];
  forbiddenActions: string[];
  writeTargets: string[];
  requiresWorkbenchReview: boolean;
}

export interface RagDocument {
  id: string;
  sourceType: 'chapter' | 'scene' | 'character' | 'world_item' | 'script' | 'storyboard' | 'import_source';
  sourceId: string;
  title: string;
  path: string | null;
  entityRefs: EntityReference[];
  chunkIds: string[];
  updatedAt: string;
}

export interface RagChunk {
  id: string;
  documentId: string;
  text: string;
  tokenCount: number;
  keywords: string[];
  entityRefs: EntityReference[];
  sourcePath: string | null;
}

export interface RetrievalRequest {
  id: string;
  query: string;
  scope: {
    entityKinds?: EntityKind[];
    sourceIds?: string[];
  };
  filters?: {
    ids?: string[];
  };
  topK: number;
  includeNeighborChunks: boolean;
}

export interface RetrievalResultItem {
  chunkId: string;
  documentId: string;
  excerpt: string;
  score: number;
  entityRefs: EntityReference[];
  sourcePath: string | null;
}

export interface RetrievalResult {
  requestId: string;
  backend: 'keyword' | 'embedding';
  items: RetrievalResultItem[];
}

export interface ScriptEpisode {
  id: string;
  title: string;
  summary: string;
  sceneIds: string[];
}

export interface ScriptDocument {
  id: string;
  title: string;
  mode: 'adaptation' | 'original';
  summary: string;
  sourceSceneIds: string[];
  sourceChapterIds: string[];
  linkedCharacterIds: string[];
  linkedWorldItemIds: string[];
  status: 'draft' | 'review' | 'approved';
  reviewState: 'pending' | 'approved' | 'changes_requested';
  version: number;
  draftPath: string | null;
  content: string;
  episodes: ScriptEpisode[];
  createdAt: string;
  updatedAt: string;
}

export interface StoryboardShot {
  id: string;
  title: string;
  summary: string;
  visualPrompt: string;
  dialogueCue?: string;
  linkedCharacterIds: string[];
  linkedWorldItemIds: string[];
  durationSeconds?: number;
}

export interface StoryboardPlan {
  id: string;
  scriptId: string;
  episodeId: string;
  title: string;
  shots: StoryboardShot[];
  visualStyleNotes: string;
  assetRefs: string[];
  promptPackagePath?: string | null;
  status: 'draft' | 'review' | 'approved';
  createdAt: string;
  updatedAt: string;
}

export interface VideoGenerationPackage {
  id: string;
  storyboardId: string;
  provider: string;
  status: 'draft' | 'pending' | 'unsupported' | 'not_configured' | 'completed' | 'failed';
  promptPackagePath: string | null;
  providerPayloadPath?: string | null;
  providerResponsePath?: string | null;
  renderManifestPath?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface RagManifest {
  activeBackend: 'keyword' | 'embedding';
  futureBackends: string[];
  storageBackend: string;
}

export interface ProjectCapabilities {
  import: boolean;
  rag: boolean;
  scripts: boolean;
  videoWorkflow: boolean;
  promptTemplates: boolean;
}

export interface UnreadUpdateState {
  activities: Record<string, boolean>;
  sections: Record<string, boolean>;
  entities: Record<string, boolean>;
}

export interface ProjectPaneState {
  sidebarWidth: number;
  inspectorWidth: number;
  agentDockWidth: number;
  writingOutlineWidth: number;
  writingContextWidth: number;
  isSidebarCollapsed: boolean;
  isAgentDockOpen: boolean;
  isWritingOutlineCollapsed: boolean;
  isWritingContextCollapsed: boolean;
}

export interface ProjectViewState {
  activeGraphBoardId?: string | null;
  activeTimelineBranchId?: string | null;
  lastOpenedSceneId?: string | null;
}

export interface ProjectUIState {
  panes: ProjectPaneState;
  view: ProjectViewState;
  density: 'comfortable' | 'compact';
  editorWidth: 'focused' | 'wide';
  motionLevel: 'full' | 'reduced';
  experimentalFlags: string[];
}

export interface ProjectMetadata {
  schemaVersion: number;
  projectId: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  version: number;
  rootPath: string;
  storageMode: StorageMode;
  locale: Locale;
  template: ProjectTemplate;
  capabilities?: ProjectCapabilities;
  storageBackends?: {
    canonical: string;
    rag: string;
  };
  futureBackends?: string[];
  lastOpenedModule?: string;
  lastOpenedSceneId?: string | null;
  lastOpenedBoardId?: string | null;
}

export interface NarrativeProject {
  metadata: ProjectMetadata;
  characters: Character[];
  characterTags: CharacterTag[];
  candidates: Candidate[];
  timelineBranches: TimelineBranch[];
  timelineEvents: TimelineEvent[];
  relationships: Relationship[];
  chapters: Chapter[];
  scenes: Scene[];
  worldContainers: WorldContainer[];
  worldItems: WorldItem[];
  graphBoards: GraphBoard[];
  betaPersonas: BetaPersona[];
  betaRuns: BetaRun[];
  taskRequests: TaskRequest[];
  taskRuns: TaskRun[];
  taskArtifacts: TaskArtifact[];
  taskRunLogs: TaskRunLogRef[];
  importJobs: ImportJob[];
  promptTemplates: PromptTemplate[];
  ragDocuments: RagDocument[];
  ragChunks: RagChunk[];
  ragManifest: RagManifest;
  retrievalHistory: RetrievalResult[];
  scripts: ScriptDocument[];
  storyboards: StoryboardPlan[];
  videoPackages: VideoGenerationPackage[];
  proposals: Proposal[];
  proposalHistory: Proposal[];
  issues: ConsistencyIssue[];
  exports: ExportArtifact[];
  unreadUpdates: UnreadUpdateState;
  archivedIds: string[];
  uiState: ProjectUIState;
}

export interface CreateProjectInput {
  name: string;
  rootPath?: string | null;
  template: ProjectTemplate;
  locale: Locale;
}

export interface SearchResult {
  id: string;
  type: EntityKind;
  label: string;
  description?: string;
}

export interface ExportProjectInput {
  format: 'markdown' | 'html';
  includeAppendices: boolean;
}
