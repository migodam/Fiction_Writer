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

interface Selection {
  type: 'character' | 'candidate' | 'timeline_event' | 'world_item' | null;
  id: string | null;
}

interface UIState {
  currentActivity: string;
  isCommandPaletteOpen: boolean;
  lastActionStatus: string | null;
  setActivity: (id: string) => void;
  toggleCommandPalette: (open?: boolean) => void;
  setLastActionStatus: (status: string | null) => void;
}

interface ProjectState {
  characters: Character[];
  candidates: Candidate[];
  timelineEvents: TimelineEvent[];
  timelineBranches: TimelineBranch[];
  currentSceneContent: string;
  selectedEntity: Selection;
  setSelectedEntity: (type: Selection['type'], id: string | null) => void;
  addCharacter: (char: Character) => void;
  updateCharacter: (char: Character) => void;
  confirmCandidate: (candidateId: string) => void;
  rejectCandidate: (candidateId: string) => void;
  addTimelineEvent: (event: TimelineEvent) => void;
  updateTimelineEvent: (event: TimelineEvent) => void;
  setCurrentSceneContent: (content: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  currentActivity: 'workbench',
  isCommandPaletteOpen: false,
  lastActionStatus: null,
  setActivity: (id) => set({ currentActivity: id }),
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

export const useProjectStore = create<ProjectState>((set) => ({
  characters: [],
  candidates: [
    { id: 'cand_1', name: 'Mysterious Stranger', background: 'Appeared at the edge of the woods.' }
  ],
  timelineEvents: [],
  timelineBranches: [
    { id: 'branch_main', name: 'Main' }
  ],
  currentSceneContent: '',
  selectedEntity: { type: null, id: null },
  setSelectedEntity: (type, id) => set({ selectedEntity: { type, id } }),
  addCharacter: (char) => set((state) => ({ characters: [...state.characters, char] })),
  updateCharacter: (char) => set((state) => ({ 
    characters: state.characters.map(c => c.id === char.id ? char : c) 
  })),
  confirmCandidate: (candidateId) => set((state) => {
    const candidate = state.candidates.find(c => c.id === candidateId);
    if (!candidate) return state;
    const newChar: Character = { ...candidate };
    return {
      candidates: state.candidates.filter(c => c.id !== candidateId),
      characters: [...state.characters, newChar]
    };
  }),
  rejectCandidate: (candidateId) => set((state) => ({
    candidates: state.candidates.filter(c => c.id !== candidateId)
  })),
  addTimelineEvent: (event) => set((state) => ({ timelineEvents: [...state.timelineEvents, event] })),
  updateTimelineEvent: (event) => set((state) => ({ 
    timelineEvents: state.timelineEvents.map(e => e.id === event.id ? event : e) 
  })),
  setCurrentSceneContent: (content) => set({ currentSceneContent: content }),
}));
