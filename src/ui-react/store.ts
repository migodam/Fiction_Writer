import { create } from 'zustand';
import type {
  BetaFeedbackItem,
  BetaPersona,
  BetaRun,
  Candidate,
  Chapter,
  Character,
  CharacterTag,
  ConsistencyIssue,
  CreateProjectInput,
  EntityKind,
  ExportArtifact,
  GraphBoard,
  GraphNode,
  ImportJob,
  Locale,
  NarrativeProject,
  PromptTemplate,
  Proposal,
  RagChunk,
  RagDocument,
  SaveStatus,
  Scene,
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
  VideoGenerationPackage,
  WorldContainer,
  WorldItem,
} from './models/project';
import { createStarterProject } from './mock/seedProject';
import { projectService } from './services/projectService';

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
  lastActionStatus: string | null;
  contextMenu: ContextMenuState;
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
  graphBoards: GraphBoard[];
  activeGraphBoardId: string | null;
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
  addCharacterTag: (tag: CharacterTag) => void;
  updateCharacterTag: (tag: CharacterTag) => void;
  deleteCharacterTag: (tagId: string) => void;
  toggleCharacterTagMembership: (tagId: string, characterId: string) => void;
  confirmCandidate: (candidateId: string) => string | null;
  rejectCandidate: (candidateId: string) => void;
  addTimelineEvent: (event: TimelineEvent) => void;
  updateTimelineEvent: (event: TimelineEvent) => void;
  addTimelineBranch: (branch: TimelineBranch) => void;
  updateTimelineBranch: (branch: TimelineBranch) => void;
  addRelationship: (relationship: NarrativeProject['relationships'][number]) => void;
  updateRelationship: (relationship: NarrativeProject['relationships'][number]) => void;
  deleteRelationship: (id: string) => void;
  addChapter: (chapter: Chapter) => void;
  updateChapter: (chapter: Chapter) => void;
  addScene: (scene: Scene) => void;
  updateScene: (scene: Scene) => void;
  updateScript: (script: ScriptDocument) => void;
  addWorldContainer: (container: WorldContainer) => void;
  updateWorldContainer: (container: WorldContainer) => void;
  deleteWorldContainer: (id: string) => void;
  addWorldItem: (item: WorldItem) => void;
  updateWorldItem: (item: WorldItem) => void;
  deleteWorldItem: (id: string) => void;
  addGraphBoard: (board: GraphBoard) => void;
  updateGraphBoard: (board: GraphBoard) => void;
  deleteGraphBoard: (boardId: string) => void;
  setActiveGraphBoard: (boardId: string) => void;
  addGraphNode: (boardId: string, node: GraphNode) => void;
  updateGraphNode: (boardId: string, node: GraphNode) => void;
  addGraphEdge: (boardId: string, edge: GraphBoard['edges'][number]) => void;
  setGraphBoardView: (boardId: string, view: GraphBoard['view']) => void;
  resolveProposal: (proposalId: string, status: Proposal['status']) => void;
  addProposal: (proposal: Proposal) => void;
  addGraphSyncProposal: (title: string, preview: string) => void;
  addExportArtifact: (artifact: ExportArtifact) => void;
  addBetaPersona: (persona: BetaPersona) => void;
  updateBetaPersona: (persona: BetaPersona) => void;
  deleteBetaPersona: (personaId: string) => void;
  runBetaPersona: (personaId: string) => void;
  addTaskRequest: (task: TaskRequest) => void;
  addTaskRun: (run: TaskRun, artifact?: TaskArtifact) => void;
  clearUnreadEntity: (entityId: string) => void;
  clearUnreadActivity: (activityId: string) => void;
  searchEntities: (query: string) => SearchResult[];
}

const now = () => new Date().toISOString();
const defaultProject = createStarterProject();
const readUiSettings = () => (typeof window === 'undefined' ? null : JSON.parse(window.localStorage.getItem(UI_SETTINGS_KEY) || 'null'));
const persistUiSettings = (settings: object) => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(UI_SETTINGS_KEY, JSON.stringify({ ...(readUiSettings() || {}), ...settings }));
};

const deriveState = (project: NarrativeProject) => ({
  projectName: project.metadata.name,
  projectRoot: project.metadata.rootPath,
  characters: project.characters,
  characterTags: project.characterTags,
  candidates: project.candidates,
  timelineEvents: project.timelineEvents,
  timelineBranches: project.timelineBranches,
  relationships: project.relationships,
  chapters: project.chapters,
  scenes: project.scenes,
  currentSceneContent: project.scenes[0]?.content || '',
  worldContainers: project.worldContainers,
  worldItems: project.worldItems,
  graphBoards: project.graphBoards,
  activeGraphBoardId: project.uiState.view.activeGraphBoardId || project.metadata.lastOpenedBoardId || project.graphBoards[0]?.id || null,
  betaPersonas: project.betaPersonas,
  betaRuns: project.betaRuns,
  taskRequests: project.taskRequests,
  taskRuns: project.taskRuns,
  taskArtifacts: project.taskArtifacts,
  taskRunLogs: project.taskRunLogs,
  importJobs: project.importJobs,
  promptTemplates: project.promptTemplates,
  ragDocuments: project.ragDocuments,
  ragChunks: project.ragChunks,
  scripts: project.scripts,
  storyboards: project.storyboards,
  videoPackages: project.videoPackages,
  proposals: project.proposals,
  proposalHistory: project.proposalHistory,
  issues: project.issues,
  exports: project.exports,
  archivedIds: project.archivedIds,
  unreadUpdates: project.unreadUpdates,
  currentProject: project,
});

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
  graphBoards: state.graphBoards,
  betaPersonas: state.betaPersonas,
  betaRuns: state.betaRuns,
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
  lastActionStatus: null,
  contextMenu: null,
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
      panel === 'sidebar' ? { sidebarWidth: clamp(width, 120, 420) } :
      panel === 'inspector' ? { inspectorWidth: clamp(width, 220, 560) } :
      panel === 'agentDock' ? { agentDockWidth: clamp(width, 180, 520) } :
      panel === 'writingOutline' ? { writingOutlineWidth: clamp(width, 160, 500) } :
      { writingContextWidth: clamp(width, 180, 520) };
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
    set({ saveStatus: 'Saving' });
    const project = projectService.openProject(rootPath);
    useUIStore.getState().hydrateFromProjectUiState(project.uiState);
    set({ ...deriveState(project), selectedEntity: { type: null, id: null }, saveStatus: 'Saved' });
    useUIStore.getState().setLocale(project.metadata.locale);
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
  addCharacter: (character) => set((state) => withDirtyState({ characters: [...state.characters, character] })),
  updateCharacter: (character) => set((state) => withDirtyState({ characters: state.characters.map((entry) => entry.id === character.id ? character : entry) })),
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
      const promoted: Character = { id: candidate.id, name: candidate.name, summary: candidate.summary, background: candidate.background, aliases: [], birthdayText: '', portraitAssetId: null, traits: '', goals: '', fears: '', secrets: '', speechStyle: '', arc: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: { alive: true } };
      confirmedId = promoted.id;
      return withDirtyState({ candidates: state.candidates.filter((entry) => entry.id !== candidateId), characters: [...state.characters, promoted] });
    });
    return confirmedId;
  },
  rejectCandidate: (candidateId) => set((state) => withDirtyState({ candidates: state.candidates.filter((entry) => entry.id !== candidateId) })),
  addTimelineEvent: (event) => set((state) => withDirtyState({ timelineEvents: [...state.timelineEvents, event] })),
  updateTimelineEvent: (event) => set((state) => withDirtyState({ timelineEvents: state.timelineEvents.map((entry) => entry.id === event.id ? event : entry) })),
  addTimelineBranch: (branch) => set((state) => withDirtyState({ timelineBranches: [...state.timelineBranches, branch] })),
  updateTimelineBranch: (branch) => set((state) => withDirtyState({ timelineBranches: state.timelineBranches.map((entry) => entry.id === branch.id ? branch : entry) })),
  addRelationship: (relationship) => set((state) => withDirtyState({ relationships: [...state.relationships, relationship] })),
  updateRelationship: (relationship) => set((state) => withDirtyState({ relationships: state.relationships.map((entry) => entry.id === relationship.id ? relationship : entry) })),
  deleteRelationship: (id) => set((state) => withDirtyState({ relationships: state.relationships.filter((entry) => entry.id !== id) })),
  addChapter: (chapter) => set((state) => withDirtyState({ chapters: [...state.chapters, chapter] })),
  updateChapter: (chapter) => set((state) => withDirtyState({ chapters: state.chapters.map((entry) => entry.id === chapter.id ? chapter : entry) })),
  addScene: (scene) => set((state) => withDirtyState({ scenes: [...state.scenes, scene] })),
  updateScene: (scene) => set((state) => withDirtyState({ scenes: state.scenes.map((entry) => entry.id === scene.id ? scene : entry), currentSceneContent: scene.content })),
  updateScript: (script) => set((state) => withDirtyState({ scripts: state.scripts.map((entry) => entry.id === script.id ? script : entry) })),
  addWorldContainer: (container) => set((state) => withDirtyState({ worldContainers: [...state.worldContainers, container] })),
  updateWorldContainer: (container) => set((state) => withDirtyState({ worldContainers: state.worldContainers.map((entry) => entry.id === container.id ? container : entry) })),
  deleteWorldContainer: (id) => set((state) => withDirtyState({ worldContainers: state.worldContainers.filter((entry) => entry.id !== id), worldItems: state.worldItems.filter((entry) => entry.containerId !== id) })),
  addWorldItem: (item) => set((state) => withDirtyState({ worldItems: [...state.worldItems, item] })),
  updateWorldItem: (item) => set((state) => withDirtyState({ worldItems: state.worldItems.map((entry) => entry.id === item.id ? item : entry) })),
  deleteWorldItem: (id) => set((state) => withDirtyState({ worldItems: state.worldItems.filter((entry) => entry.id !== id) })),
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
  setGraphBoardView: (boardId, view) => set((state) => withDirtyState({ graphBoards: state.graphBoards.map((board) => board.id === boardId ? { ...board, view } : board) })),
  resolveProposal: (proposalId, status) => set((state) => withDirtyState(projectService.resolveProposal(cloneProject(state, useUIStore.getState().locale), proposalId, status))),
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
  addTaskRequest: (task) => set((state) => withDirtyState({ taskRequests: [task, ...state.taskRequests] })),
  addTaskRun: (run, artifact) => set((state) => withDirtyState({ taskRuns: [run, ...state.taskRuns], taskArtifacts: artifact ? [artifact, ...state.taskArtifacts] : state.taskArtifacts })),
  clearUnreadEntity: (entityId) => set((state) => ({ unreadUpdates: { ...state.unreadUpdates, entities: { ...state.unreadUpdates.entities, [entityId]: false } } })),
  clearUnreadActivity: (activityId) => set((state) => ({ unreadUpdates: { ...state.unreadUpdates, activities: { ...state.unreadUpdates.activities, [activityId]: false } } })),
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
}));
