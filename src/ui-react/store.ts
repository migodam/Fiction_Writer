import { create } from 'zustand';

interface Character {
  id: string;
  name: string;
  background: string;
  aliases?: string;
  traits?: string;
  goals?: string;
  fears?: string;
  secrets?: string;
  speechStyle?: string;
  arc?: string;
  affiliations?: string;
}

interface Candidate {
  id: string;
  name: string;
  background: string;
}

interface TimelineEvent {
  id: string;
  title: string;
  summary: string;
  time?: string;
  location?: string;
  participants?: string[];
  branchId: string;
  orderIndex: number;
}

interface TimelineBranch {
  id: string;
  name: string;
}

interface Relationship {
    id: string;
    sourceId: string;
    targetId: string;
    type: string;
    description?: string;
}

interface Scene {
    id: string;
    chapterId: string;
    title: string;
    content: string;
    orderIndex: number;
}

interface Chapter {
    id: string;
    title: string;
    orderIndex: number;
}

interface Selection {
  type: 'character' | 'candidate' | 'timeline_event' | 'world_item' | 'relationship' | 'chapter' | 'scene' | null;
  id: string | null;
}

type SaveStatus = 'Idle' | 'Unsaved changes' | 'Saving' | 'Saved' | 'Error';

interface SearchResult {
    id: string;
    type: Selection['type'];
    label: string;
    description?: string;
}

interface UIState {
  currentActivity: string;
  sidebarSection: string;
  isCommandPaletteOpen: boolean;
  lastActionStatus: string | null;
  setActivity: (id: string) => void;
  setSidebarSection: (section: string) => void;
  toggleCommandPalette: (open?: boolean) => void;
  setLastActionStatus: (status: string | null) => void;
}

interface ProjectState {
  projectName: string;
  saveStatus: SaveStatus;
  characters: Character[];
  candidates: Candidate[];
  timelineEvents: TimelineEvent[];
  timelineBranches: TimelineBranch[];
  relationships: Relationship[];
  chapters: Chapter[];
  scenes: Scene[];
  currentSceneContent: string;
  selectedEntity: Selection;
  setSelectedEntity: (type: Selection['type'], id: string | null) => void;
  addCharacter: (char: Character) => void;
  updateCharacter: (char: Character) => void;
  confirmCandidate: (candidateId: string) => void;
  rejectCandidate: (candidateId: string) => void;
  addTimelineEvent: (event: TimelineEvent) => void;
  updateTimelineEvent: (event: TimelineEvent) => void;
  addRelationship: (rel: Relationship) => void;
  updateRelationship: (rel: Relationship) => void;
  deleteRelationship: (id: string) => void;
  addChapter: (chap: Chapter) => void;
  updateChapter: (chap: Chapter) => void;
  addScene: (scene: Scene) => void;
  updateScene: (scene: Scene) => void;
  setCurrentSceneContent: (content: string) => void;
  setSaveStatus: (status: SaveStatus) => void;
  saveProject: () => Promise<void>;
  loadProject: (data: any) => void;
  searchEntities: (query: string) => SearchResult[];
}

export const useUIStore = create<UIState>((set) => ({
  currentActivity: 'workbench',
  sidebarSection: 'default',
  isCommandPaletteOpen: false,
  lastActionStatus: null,
  setActivity: (id) => set({ currentActivity: id, sidebarSection: 'default' }),
  setSidebarSection: (section) => set({ sidebarSection: section }),
  toggleCommandPalette: (open) => set((state) => ({ 
    isCommandPaletteOpen: typeof open === 'boolean' ? open : !state.isCommandPaletteOpen 
  })),
  setLastActionStatus: (status) => {
    set({ lastActionStatus: status });
    if (status) {
      setTimeout(() => set({ lastActionStatus: null }), 3000);
    }
  },
}));

export const useProjectStore = create<ProjectState>((set, get) => ({
  projectName: 'Seed Project',
  saveStatus: 'Idle',
  characters: [],
  candidates: [
    { id: 'cand_1', name: 'Mysterious Stranger', background: 'Appeared at the edge of the woods.' }
  ],
  timelineEvents: [],
  timelineBranches: [
    { id: 'branch_main', name: 'Main' }
  ],
  relationships: [],
  chapters: [
      { id: 'chap_1', title: 'Chapter 1', orderIndex: 0 }
  ],
  scenes: [
      { id: 'scene_1', chapterId: 'chap_1', title: 'The Beginning', content: 'Once upon a time...', orderIndex: 0 }
  ],
  currentSceneContent: '',
  selectedEntity: { type: null, id: null },
  setSelectedEntity: (type, id) => set({ selectedEntity: { type, id } }),
  addCharacter: (char) => {
    set((state) => ({ characters: [...state.characters, char], saveStatus: 'Unsaved changes' }));
  },
  updateCharacter: (char) => set((state) => ({ 
    characters: state.characters.map(c => c.id === char.id ? char : c),
    saveStatus: 'Unsaved changes'
  })),
  confirmCandidate: (candidateId) => set((state) => {
    const candidate = state.candidates.find(c => c.id === candidateId);
    if (!candidate) return state;
    const newChar: Character = { ...candidate };
    return {
      candidates: state.candidates.filter(c => c.id !== candidateId),
      characters: [...state.characters, newChar],
      saveStatus: 'Unsaved changes'
    };
  }),
  rejectCandidate: (candidateId) => set((state) => ({
    candidates: state.candidates.filter(c => c.id !== candidateId),
    saveStatus: 'Unsaved changes'
  })),
  addTimelineEvent: (event) => set((state) => ({ 
    timelineEvents: [...state.timelineEvents, event],
    saveStatus: 'Unsaved changes'
  })),
  updateTimelineEvent: (event) => set((state) => ({ 
    timelineEvents: state.timelineEvents.map(e => e.id === event.id ? event : e),
    saveStatus: 'Unsaved changes'
  })),
  addRelationship: (rel) => set((state) => ({
      relationships: [...state.relationships, rel],
      saveStatus: 'Unsaved changes'
  })),
  updateRelationship: (rel) => set((state) => ({
      relationships: state.relationships.map(r => r.id === rel.id ? rel : r),
      saveStatus: 'Unsaved changes'
  })),
  deleteRelationship: (id) => set((state) => ({
      relationships: state.relationships.filter(r => r.id !== id),
      saveStatus: 'Unsaved changes'
  })),
  addChapter: (chap) => set((state) => ({ chapters: [...state.chapters, chap], saveStatus: 'Unsaved changes' })),
  updateChapter: (chap) => set((state) => ({ 
      chapters: state.chapters.map(c => c.id === chap.id ? chap : c),
      saveStatus: 'Unsaved changes'
  })),
  addScene: (scene) => set((state) => ({ scenes: [...state.scenes, scene], saveStatus: 'Unsaved changes' })),
  updateScene: (scene) => set((state) => ({ 
      scenes: state.scenes.map(s => s.id === scene.id ? scene : s),
      saveStatus: 'Unsaved changes'
  })),
  setCurrentSceneContent: (content) => set({ currentSceneContent: content, saveStatus: 'Unsaved changes' }),
  setSaveStatus: (status) => set({ saveStatus: status }),
  saveProject: async () => {
    set({ saveStatus: 'Saving' });
    await new Promise(resolve => setTimeout(resolve, 800));
    set({ saveStatus: 'Saved' });
    setTimeout(() => {
        if (get().saveStatus === 'Saved') set({ saveStatus: 'Idle' });
    }, 2000);
  },
  loadProject: (data) => set({
    projectName: data.metadata?.name || 'Untitled',
    characters: data.characters || [],
    timelineEvents: data.timeline?.events || [],
    timelineBranches: data.timeline?.branches || [{ id: 'branch_main', name: 'Main' }],
    relationships: data.relationships || [],
    chapters: data.chapters || [],
    scenes: data.scenes || [],
    saveStatus: 'Idle'
  }),
  searchEntities: (query) => {
    if (!query) return [];
    const q = query.toLowerCase();
    const results: SearchResult[] = [];
    
    get().characters.forEach(c => {
        if (c.name.toLowerCase().includes(q)) {
            results.push({ id: c.id, type: 'character', label: c.name, description: 'Character' });
        }
    });

    get().candidates.forEach(c => {
        if (c.name.toLowerCase().includes(q)) {
            results.push({ id: c.id, type: 'candidate', label: c.name, description: 'Candidate' });
        }
    });
    
    get().timelineEvents.forEach(e => {
        if (e.title.toLowerCase().includes(q)) {
            results.push({ id: e.id, type: 'timeline_event', label: e.title, description: 'Timeline Event' });
        }
    });
    
    return results;
  }
}));
