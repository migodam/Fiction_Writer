export type EntityKind =
  | 'character'
  | 'candidate'
  | 'timeline_event'
  | 'world_item'
  | 'relationship'
  | 'chapter'
  | 'scene'
  | 'world_container'
  | 'proposal'
  | 'issue'
  | 'graph_node';

export type SaveStatus = 'Idle' | 'Unsaved changes' | 'Saving' | 'Saved' | 'Error';
export type StorageMode = 'memory' | 'nodefs';
export type ProjectTemplate = 'blank' | 'starter-demo';
export type Locale = 'en' | 'zh-CN';
export type ProposalStatus = 'pending' | 'accepted' | 'rejected' | 'archived';
export type IssueStatus = 'open' | 'resolved' | 'ignored';
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
}

export interface Relationship {
  id: string;
  sourceId: string;
  targetId: string;
  type: string;
  description?: string;
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

export interface GraphBoard {
  id: string;
  name: string;
  description: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Proposal {
  id: string;
  title: string;
  source: 'graph' | 'consistency' | 'agent';
  description: string;
  targetEntityType: EntityKind;
  targetEntityId?: string | null;
  preview: string;
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
  referenceIds: EntityReference[];
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

export interface UnreadUpdateState {
  activities: Record<string, boolean>;
  sections: Record<string, boolean>;
  entities: Record<string, boolean>;
}

export interface ProjectMetadata {
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
  lastOpenedModule?: string;
  lastOpenedSceneId?: string | null;
  lastOpenedBoardId?: string | null;
}

export interface NarrativeProject {
  metadata: ProjectMetadata;
  characters: Character[];
  candidates: Candidate[];
  timelineBranches: TimelineBranch[];
  timelineEvents: TimelineEvent[];
  relationships: Relationship[];
  chapters: Chapter[];
  scenes: Scene[];
  worldContainers: WorldContainer[];
  worldItems: WorldItem[];
  graphBoards: GraphBoard[];
  proposals: Proposal[];
  proposalHistory: Proposal[];
  issues: ConsistencyIssue[];
  exports: ExportArtifact[];
  unreadUpdates: UnreadUpdateState;
  archivedIds: string[];
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
