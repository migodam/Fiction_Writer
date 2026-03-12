import { create } from 'zustand';
import type {
  Candidate,
  Chapter,
  Character,
  ConsistencyIssue,
  CreateProjectInput,
  EntityKind,
  ExportArtifact,
  ExportProjectInput,
  GraphBoard,
  Locale,
  NarrativeProject,
  ProjectTemplate,
  Proposal,
  Relationship,
  SaveStatus,
  Scene,
  SearchResult,
  Selection,
  StorageMode,
  TimelineBranch,
  TimelineEvent,
  WorldContainer,
  WorldItem,
} from './models/project';
import { createStarterProject } from './mock/seedProject';
import { projectService } from './services/projectService';

const UI_SETTINGS_KEY = 'narrative-ide-ui-settings';

type PanelKind = 'sidebar' | 'inspector' | 'agentDock';

interface UIState {
  currentActivity: string;
  sidebarSection: string;
  locale: Locale;
  isCommandPaletteOpen: boolean;
  isAgentDockOpen: boolean;
  isSidebarCollapsed: boolean;
  isSettingsOpen: boolean;
  sidebarWidth: number;
  inspectorWidth: number;
  agentDockWidth: number;
  lastActionStatus: string | null;
  setActivity: (id: string) => void;
  setSidebarSection: (section: string) => void;
  setLocale: (locale: Locale) => void;
  toggleCommandPalette: (open?: boolean) => void;
  toggleAgentDock: (open?: boolean) => void;
  toggleSidebar: (open?: boolean) => void;
  toggleSettings: (open?: boolean) => void;
  setPanelWidth: (panel: PanelKind, width: number) => void;
  resetLayout: () => void;
  setLastActionStatus: (status: string | null) => void;
}

interface ProjectState {
  projectName: string;
  projectRoot: string;
  projectTemplate: ProjectTemplate;
  storageMode: StorageMode;
  saveStatus: SaveStatus;
  selectedEntity: Selection;
  characters: Character[];
  candidates: Candidate[];
  timelineEvents: TimelineEvent[];
  timelineBranches: TimelineBranch[];
  relationships: Relationship[];
  chapters: Chapter[];
  scenes: Scene[];
  currentSceneContent: string;
  worldContainers: WorldContainer[];
  worldItems: WorldItem[];
  graphBoards: GraphBoard[];
  activeGraphBoardId: string | null;
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
  addCharacter: (character: Character) => void;
  updateCharacter: (character: Character) => void;
  confirmCandidate: (candidateId: string) => string | null;
  rejectCandidate: (candidateId: string) => void;
  addTimelineEvent: (event: TimelineEvent) => void;
  updateTimelineEvent: (event: TimelineEvent) => void;
  addRelationship: (relationship: Relationship) => void;
  updateRelationship: (relationship: Relationship) => void;
  deleteRelationship: (id: string) => void;
  addChapter: (chapter: Chapter) => void;
  updateChapter: (chapter: Chapter) => void;
  addScene: (scene: Scene) => void;
  updateScene: (scene: Scene) => void;
  addWorldContainer: (container: WorldContainer) => void;
  updateWorldContainer: (container: WorldContainer) => void;
  deleteWorldContainer: (id: string) => void;
  addWorldItem: (item: WorldItem) => void;
  updateWorldItem: (item: WorldItem) => void;
  deleteWorldItem: (id: string) => void;
  setCurrentSceneContent: (content: string) => void;
  resolveProposal: (proposalId: string, status: Proposal['status']) => void;
  addProposal: (proposal: Proposal) => void;
  addGraphSyncProposal: (title: string, preview: string) => void;
  addExportArtifact: (artifact: ExportArtifact) => void;
  clearUnreadEntity: (entityId: string) => void;
  clearUnreadActivity: (activityId: string) => void;
  searchEntities: (query: string) => SearchResult[];
}

const now = () => new Date().toISOString();
const defaultProject = createStarterProject();

const readUiSettings = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  const raw = window.localStorage.getItem(UI_SETTINGS_KEY);
  return raw ? JSON.parse(raw) : null;
};

const persistUiSettings = (settings: Partial<UIState>) => {
  if (typeof window === 'undefined') {
    return;
  }
  const current = readUiSettings() || {};
  window.localStorage.setItem(UI_SETTINGS_KEY, JSON.stringify({ ...current, ...settings }));
};

const deriveState = (project: NarrativeProject) => ({
  projectName: project.metadata.name,
  projectRoot: project.metadata.rootPath,
  projectTemplate: project.metadata.template,
  storageMode: project.metadata.storageMode,
  characters: project.characters,
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
  activeGraphBoardId: project.metadata.lastOpenedBoardId || project.graphBoards[0]?.id || null,
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
    storageMode: state.storageMode,
    template: state.projectTemplate,
    locale: locale || state.currentProject?.metadata.locale || 'en',
    lastOpenedSceneId: state.selectedEntity.type === 'scene' ? state.selectedEntity.id : state.currentProject?.metadata.lastOpenedSceneId || null,
    lastOpenedBoardId: state.activeGraphBoardId,
    updatedAt: now(),
  },
  characters: state.characters,
  candidates: state.candidates,
  timelineBranches: state.timelineBranches,
  timelineEvents: state.timelineEvents,
  relationships: state.relationships,
  chapters: state.chapters,
  scenes: state.scenes,
  worldContainers: state.worldContainers,
  worldItems: state.worldItems,
  graphBoards: state.graphBoards,
  proposals: state.proposals,
  proposalHistory: state.proposalHistory,
  issues: state.issues,
  exports: state.exports,
  unreadUpdates: state.unreadUpdates,
  archivedIds: state.archivedIds,
});

const withDirtyState = (partial: Partial<ProjectState>) => ({
  ...partial,
  saveStatus: 'Unsaved changes' as SaveStatus,
});

const defaultUi = {
  locale: (readUiSettings()?.locale as Locale) || 'en',
  sidebarWidth: readUiSettings()?.sidebarWidth || 280,
  inspectorWidth: readUiSettings()?.inspectorWidth || 360,
  agentDockWidth: readUiSettings()?.agentDockWidth || 320,
  isSidebarCollapsed: readUiSettings()?.isSidebarCollapsed || false,
  isAgentDockOpen: readUiSettings()?.isAgentDockOpen ?? true,
};

export const useUIStore = create<UIState>((set) => ({
  currentActivity: 'workbench',
  sidebarSection: 'inbox',
  locale: defaultUi.locale,
  isCommandPaletteOpen: false,
  isAgentDockOpen: defaultUi.isAgentDockOpen,
  isSidebarCollapsed: defaultUi.isSidebarCollapsed,
  isSettingsOpen: false,
  sidebarWidth: defaultUi.sidebarWidth,
  inspectorWidth: defaultUi.inspectorWidth,
  agentDockWidth: defaultUi.agentDockWidth,
  lastActionStatus: null,
  setActivity: (id) => set({ currentActivity: id }),
  setSidebarSection: (section) => set({ sidebarSection: section }),
  setLocale: (locale) => {
    persistUiSettings({ locale });
    set({ locale });
  },
  toggleCommandPalette: (open) =>
    set((state) => ({
      isCommandPaletteOpen: typeof open === 'boolean' ? open : !state.isCommandPaletteOpen,
    })),
  toggleAgentDock: (open) =>
    set((state) => {
      const next = typeof open === 'boolean' ? open : !state.isAgentDockOpen;
      persistUiSettings({ isAgentDockOpen: next });
      return { isAgentDockOpen: next };
    }),
  toggleSidebar: (open) =>
    set((state) => {
      const next = typeof open === 'boolean' ? open : !state.isSidebarCollapsed;
      persistUiSettings({ isSidebarCollapsed: next });
      return { isSidebarCollapsed: next };
    }),
  toggleSettings: (open) =>
    set((state) => ({
      isSettingsOpen: typeof open === 'boolean' ? open : !state.isSettingsOpen,
    })),
  setPanelWidth: (panel, width) =>
    set((state) => {
      const clamped = panel === 'sidebar' ? Math.min(Math.max(width, 220), 420) : Math.min(Math.max(width, 260), 520);
      const next = panel === 'sidebar'
        ? { sidebarWidth: clamped }
        : panel === 'inspector'
        ? { inspectorWidth: clamped }
        : { agentDockWidth: clamped };
      persistUiSettings(next);
      return { ...state, ...next };
    }),
  resetLayout: () => {
    const reset = {
      sidebarWidth: 280,
      inspectorWidth: 360,
      agentDockWidth: 320,
      isSidebarCollapsed: false,
      isAgentDockOpen: true,
    };
    persistUiSettings(reset);
    set(reset);
  },
  setLastActionStatus: (status) => {
    set({ lastActionStatus: status });
    if (status) {
      setTimeout(() => set({ lastActionStatus: null }), 3000);
    }
  },
}));

export const useProjectStore = create<ProjectState>((set, get) => ({
  ...deriveState(defaultProject),
  saveStatus: 'Idle',
  selectedEntity: { type: null, id: null },

  setSelectedEntity: (type, id) =>
    set((state) => ({
      selectedEntity: { type, id },
      unreadUpdates: id
        ? {
            ...state.unreadUpdates,
            entities: {
              ...state.unreadUpdates.entities,
              [id]: false,
            },
          }
        : state.unreadUpdates,
    })),

  createProject: async (input) => {
    const uiLocale = useUIStore.getState().locale;
    set({ saveStatus: 'Saving' });
    const project = projectService.createProject({
      name: input?.name || 'Starter Demo Project',
      rootPath: input?.rootPath,
      template: input?.template || 'starter-demo',
      locale: input?.locale || uiLocale,
    });
    set({
      ...deriveState(project),
      selectedEntity: { type: null, id: null },
      saveStatus: 'Saved',
    });
    useUIStore.getState().setLocale(project.metadata.locale);
    setTimeout(() => {
      if (get().saveStatus === 'Saved') {
        set({ saveStatus: 'Idle' });
      }
    }, 1500);
  },

  openProject: async (rootPath) => {
    set({ saveStatus: 'Saving' });
    const project = projectService.openProject(rootPath);
    set({
      ...deriveState(project),
      selectedEntity: { type: null, id: null },
      saveStatus: 'Saved',
    });
    useUIStore.getState().setLocale(project.metadata.locale);
    setTimeout(() => {
      if (get().saveStatus === 'Saved') {
        set({ saveStatus: 'Idle' });
      }
    }, 1500);
  },

  saveProject: async () => {
    set({ saveStatus: 'Saving' });
    const project = cloneProject(get(), useUIStore.getState().locale);
    const savedProject = projectService.saveProject(project);
    set({
      ...deriveState(savedProject),
      saveStatus: 'Saved',
    });
    setTimeout(() => {
      if (get().saveStatus === 'Saved') {
        set({ saveStatus: 'Idle' });
      }
    }, 1600);
  },

  loadProject: (project) =>
    set({
      ...deriveState(project),
      selectedEntity: { type: null, id: null },
      saveStatus: 'Idle',
    }),

  setProjectLocale: (locale) =>
    set((state) => ({
      currentProject: cloneProject(state, locale),
      saveStatus: 'Unsaved changes',
    })),

  addCharacter: (character) =>
    set((state) =>
      withDirtyState({
        characters: [...state.characters, character],
      })
    ),

  updateCharacter: (character) =>
    set((state) =>
      withDirtyState({
        characters: state.characters.map((entry) => (entry.id === character.id ? character : entry)),
      })
    ),

  confirmCandidate: (candidateId) => {
    let confirmedId: string | null = null;
    set((state) => {
      const candidate = state.candidates.find((entry) => entry.id === candidateId);
      if (!candidate) {
        return state;
      }
      const promoted: Character = {
        id: candidate.id,
        name: candidate.name,
        summary: candidate.summary,
        background: candidate.background,
        aliases: [],
        birthdayText: '',
        portraitAssetId: null,
        traits: '',
        goals: '',
        fears: '',
        secrets: '',
        speechStyle: '',
        arc: '',
        tagIds: [],
        organizationIds: [],
        linkedSceneIds: [],
        linkedEventIds: [],
        linkedWorldItemIds: [],
        statusFlags: { alive: true },
      };
      confirmedId = promoted.id;
      return withDirtyState({
        candidates: state.candidates.filter((entry) => entry.id !== candidateId),
        characters: [...state.characters, promoted],
        unreadUpdates: {
          ...state.unreadUpdates,
          activities: { ...state.unreadUpdates.activities, characters: true },
          sections: { ...state.unreadUpdates.sections, 'characters.list': true },
          entities: { ...state.unreadUpdates.entities, [promoted.id]: true },
        },
      });
    });
    return confirmedId;
  },

  rejectCandidate: (candidateId) =>
    set((state) =>
      withDirtyState({
        candidates: state.candidates.filter((entry) => entry.id !== candidateId),
      })
    ),

  addTimelineEvent: (event) =>
    set((state) =>
      withDirtyState({
        timelineEvents: [...state.timelineEvents, event],
      })
    ),

  updateTimelineEvent: (event) =>
    set((state) =>
      withDirtyState({
        timelineEvents: state.timelineEvents.map((entry) => (entry.id === event.id ? event : entry)),
      })
    ),

  addRelationship: (relationship) =>
    set((state) => withDirtyState({ relationships: [...state.relationships, relationship] })),
  updateRelationship: (relationship) =>
    set((state) =>
      withDirtyState({
        relationships: state.relationships.map((entry) => (entry.id === relationship.id ? relationship : entry)),
      })
    ),
  deleteRelationship: (id) =>
    set((state) => withDirtyState({ relationships: state.relationships.filter((entry) => entry.id !== id) })),

  addChapter: (chapter) => set((state) => withDirtyState({ chapters: [...state.chapters, chapter] })),
  updateChapter: (chapter) =>
    set((state) => withDirtyState({ chapters: state.chapters.map((entry) => (entry.id === chapter.id ? chapter : entry)) })),
  addScene: (scene) => set((state) => withDirtyState({ scenes: [...state.scenes, scene] })),
  updateScene: (scene) =>
    set((state) =>
      withDirtyState({
        scenes: state.scenes.map((entry) => (entry.id === scene.id ? scene : entry)),
        currentSceneContent: scene.content,
      })
    ),

  addWorldContainer: (container) =>
    set((state) => withDirtyState({ worldContainers: [...state.worldContainers, container] })),
  updateWorldContainer: (container) =>
    set((state) =>
      withDirtyState({ worldContainers: state.worldContainers.map((entry) => (entry.id === container.id ? container : entry)) })
    ),
  deleteWorldContainer: (id) =>
    set((state) => withDirtyState({ worldContainers: state.worldContainers.filter((entry) => entry.id !== id) })),

  addWorldItem: (item) => set((state) => withDirtyState({ worldItems: [...state.worldItems, item] })),
  updateWorldItem: (item) =>
    set((state) => withDirtyState({ worldItems: state.worldItems.map((entry) => (entry.id === item.id ? item : entry)) })),
  deleteWorldItem: (id) =>
    set((state) => withDirtyState({ worldItems: state.worldItems.filter((entry) => entry.id !== id) })),

  setCurrentSceneContent: (content) => set({ currentSceneContent: content, saveStatus: 'Unsaved changes' }),

  resolveProposal: (proposalId, status) =>
    set((state) => {
      const nextProject = projectService.resolveProposal(cloneProject(state, useUIStore.getState().locale), proposalId, status);
      return withDirtyState({ ...deriveState(nextProject) });
    }),

  addProposal: (proposal) =>
    set((state) =>
      withDirtyState({
        proposals: [proposal, ...state.proposals],
        unreadUpdates: {
          ...state.unreadUpdates,
          activities: { ...state.unreadUpdates.activities, workbench: true },
          sections: { ...state.unreadUpdates.sections, 'workbench.inbox': true },
          entities: { ...state.unreadUpdates.entities, [proposal.id]: true },
        },
      })
    ),

  addGraphSyncProposal: (title, preview) =>
    set((state) => {
      const proposal: Proposal = {
        id: `proposal_${Date.now()}`,
        title,
        source: 'graph',
        description: 'Generated from graph selection and routed into Workbench.',
        targetEntityType: 'proposal',
        targetEntityId: null,
        preview,
        status: 'pending',
        createdAt: now(),
      };
      return withDirtyState({
        proposals: [proposal, ...state.proposals],
        unreadUpdates: {
          ...state.unreadUpdates,
          activities: { ...state.unreadUpdates.activities, workbench: true, graph: true },
          sections: { ...state.unreadUpdates.sections, 'workbench.inbox': true },
          entities: { ...state.unreadUpdates.entities, [proposal.id]: true },
        },
      });
    }),

  addExportArtifact: (artifact) =>
    set((state) => withDirtyState({ exports: [artifact, ...state.exports] })),

  clearUnreadEntity: (entityId) =>
    set((state) => ({
      unreadUpdates: {
        ...state.unreadUpdates,
        entities: { ...state.unreadUpdates.entities, [entityId]: false },
      },
    })),

  clearUnreadActivity: (activityId) =>
    set((state) => ({
      unreadUpdates: {
        ...state.unreadUpdates,
        activities: { ...state.unreadUpdates.activities, [activityId]: false },
      },
    })),

  searchEntities: (query) => {
    if (!query) {
      return [];
    }

    const loweredQuery = query.toLowerCase();
    const state = get();
    const results: SearchResult[] = [];

    state.characters.forEach((character) => {
      if (character.name.toLowerCase().includes(loweredQuery)) {
        results.push({ id: character.id, type: 'character', label: character.name, description: 'Character' });
      }
    });
    state.candidates.forEach((candidate) => {
      if (candidate.name.toLowerCase().includes(loweredQuery)) {
        results.push({ id: candidate.id, type: 'candidate', label: candidate.name, description: 'Candidate' });
      }
    });
    state.timelineEvents.forEach((event) => {
      if (event.title.toLowerCase().includes(loweredQuery)) {
        results.push({ id: event.id, type: 'timeline_event', label: event.title, description: 'Timeline Event' });
      }
    });
    state.worldItems.forEach((item) => {
      if (item.name.toLowerCase().includes(loweredQuery)) {
        results.push({ id: item.id, type: 'world_item', label: item.name, description: item.type });
      }
    });
    state.proposals.forEach((proposal) => {
      if (proposal.title.toLowerCase().includes(loweredQuery)) {
        results.push({ id: proposal.id, type: 'proposal', label: proposal.title, description: 'Workbench Proposal' });
      }
    });
    state.scenes.forEach((scene) => {
      if (scene.title.toLowerCase().includes(loweredQuery)) {
        results.push({ id: scene.id, type: 'scene', label: scene.title, description: 'Scene' });
      }
    });

    return results;
  },
}));
