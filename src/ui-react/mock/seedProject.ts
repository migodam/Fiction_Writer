import type {
  BetaPersona,
  BetaRun,
  Candidate,
  Chapter,
  Character,
  CharacterTag,
  ConsistencyIssue,
  ExportArtifact,
  GraphBoard,
  ImportJob,
  Locale,
  NarrativeProject,
  PromptTemplate,
  ProjectTemplate,
  Proposal,
  RagChunk,
  RagDocument,
  Relationship,
  Scene,
  ScriptDocument,
  SimulationEngine,
  SimulationLab,
  SimulationReviewer,
  SimulationRun,
  StoryboardPlan,
  TaskArtifact,
  TaskRequest,
  TaskRun,
  TaskRunLogRef,
  TimelineBranch,
  TimelineEvent,
  VideoGenerationPackage,
  WorldContainer,
  WorldMapDocument,
  WorldSettings,
  WorldItem,
} from '../models/project';
import { PROJECT_SCHEMA_VERSION } from '../models/project';

const now = () => new Date().toISOString();

const createStarterTags = (): CharacterTag[] => [
  { id: 'tag_lead', name: 'Lead', color: '#f59e0b', description: 'Primary perspective driver.', characterIds: ['char_aria'] },
  { id: 'tag_strategist', name: 'Strategist', color: '#38bdf8', description: 'Pattern-detecting operators.', characterIds: ['char_rowan', 'char_nila'] },
  { id: 'tag_resistance', name: 'Resistance', color: '#22c55e', description: 'Opposition-aligned characters.', characterIds: ['char_seren'] },
  { id: 'tag_antagonist', name: 'Antagonist', color: '#ef4444', description: 'Primary hostile force.', characterIds: ['char_vesper'] },
];

const createStarterBetaPersonas = (): BetaPersona[] => [
  {
    id: 'beta_logician',
    name: 'The Logician',
    archetype: 'Analytical',
    profile: 'Focuses on plot holes and cause-effect chains.',
    tone: 'precise',
    focusAreas: ['consistency', 'causality', 'pacing'],
    weights: { engagement: 62, retention: 68, resonance: 48, pacing: 82, consistency: 95 },
  },
  {
    id: 'beta_empath',
    name: 'The Empath',
    archetype: 'Emotional',
    profile: 'Tracks emotional resonance and character arcs.',
    tone: 'warm',
    focusAreas: ['resonance', 'engagement', 'character'],
    weights: { engagement: 85, retention: 74, resonance: 93, pacing: 58, consistency: 65 },
  },
  {
    id: 'beta_generalist',
    name: 'The Generalist',
    archetype: 'Broad audience',
    profile: 'Represents average reader enjoyment and clarity.',
    tone: 'balanced',
    focusAreas: ['engagement', 'retention', 'clarity'],
    weights: { engagement: 81, retention: 79, resonance: 75, pacing: 78, consistency: 71 },
  },
];

const createStarterBetaRuns = (): BetaRun[] => [
  {
    id: 'beta_run_seed',
    personaId: 'beta_generalist',
    createdAt: now(),
    aggregate: {
      engagement: 82,
      retention: 71,
      resonance: 85,
      pacing: 77,
      consistency: 68,
      highlights: [
        'Bridge Intercept lands as a strong act-turning sequence.',
        'Rowan and Nila have memorable tactical chemistry.',
        'The public fallout thread wants one more aftermath scene.',
      ],
    },
    feedback: [
      {
        id: 'feedback_1',
        title: 'Chapter 1 pacing',
        text: 'The introduction is strong, but the market transition wants one more beat of emotional processing.',
        tag: 'Pacing',
        type: 'constructive',
      },
      {
        id: 'feedback_2',
        title: 'Cipher setup',
        text: 'The archive reconstruction sequence is compelling, but Nila should own more of the deciphering setup earlier.',
        tag: 'Consistency',
        type: 'critical',
      },
      {
        id: 'feedback_3',
        title: 'Rowan voice',
        text: 'Rowan consistently lands with a dry tactical humor that helps the investigation feel sharp.',
        tag: 'Voice',
        type: 'positive',
      },
    ],
  },
];

const createStarterTaskRequests = (): TaskRequest[] => [
  {
    id: 'task_graph_sync',
    title: 'Graph sync candidate review',
    taskType: 'proposal_generation',
    agentType: 'qa-consistency-agent',
    source: 'manual',
    status: 'queued',
    prompt: 'Review selected graph notes and prepare canonical-safe proposals.',
    input: {
      objective: 'Turn reviewed graph notes into Workbench-safe proposals.',
    },
    contextScope: {
      graphBoardIds: ['board_main'],
      targetEntityIds: ['event_bridge'],
    },
    targetIds: [
      { type: 'graph_board', id: 'board_main' },
      { type: 'timeline_event', id: 'event_bridge' },
    ],
    reviewPolicy: 'manual_workbench',
    createdAt: now(),
  },
  {
    id: 'task_import_seed',
    title: 'Starter import review',
    taskType: 'novel_import',
    agentType: 'import-agent',
    source: 'local-cli',
    status: 'awaiting_user_input',
    prompt: 'Validate imported chapter and scene structure before metadata extraction.',
    input: {
      importJobId: 'import_seed_project',
      sourceFormat: 'md',
    },
    contextScope: {
      importJobIds: ['import_seed_project'],
    },
    targetIds: [{ type: 'import_job', id: 'import_seed_project' }],
    reviewPolicy: 'manual_workbench',
    createdAt: now(),
  },
];

const createStarterTaskRuns = (): TaskRun[] => [
  {
    id: 'run_graph_sync_seed',
    taskRequestId: 'task_graph_sync',
    status: 'completed',
    executor: 'manual',
    adapter: 'noop-qa-adapter',
    attempt: 1,
    startedAt: now(),
    heartbeatAt: now(),
    finishedAt: now(),
    summary: 'Generated one graph sync proposal and one consistency summary.',
    artifactIds: ['artifact_graph_sync_seed'],
  },
  {
    id: 'run_import_seed',
    taskRequestId: 'task_import_seed',
    status: 'awaiting_user_input',
    executor: 'local-cli',
    adapter: 'rule-import-adapter',
    attempt: 1,
    startedAt: now(),
    heartbeatAt: now(),
    summary: 'Imported manuscript skeleton and paused for user confirmation.',
    artifactIds: ['artifact_import_manifest_seed', 'artifact_context_seed'],
    awaitingUserInput: {
      prompt: 'Confirm whether imported chapter boundaries are acceptable before metadata extraction.',
      fields: ['chapter_boundaries', 'scene_split_quality'],
      reason: 'Import staging needs human review before downstream agent steps.',
    },
  },
];

const createStarterTaskArtifacts = (): TaskArtifact[] => [
  {
    id: 'artifact_graph_sync_seed',
    taskRunId: 'run_graph_sync_seed',
    type: 'report',
    summary: 'Seed analysis bundle for review.',
    path: null,
    mimeType: 'application/json',
    entityRefs: [{ type: 'proposal', id: 'proposal_graph_public_fallout' }],
  },
  {
    id: 'artifact_import_manifest_seed',
    taskRunId: 'run_import_seed',
    type: 'import-manifest',
    summary: 'Staged import manifest for starter demo project.',
    path: 'system/imports/staging/import_seed_project/manifest.json',
    mimeType: 'application/json',
    entityRefs: [{ type: 'import_job', id: 'import_seed_project' }],
  },
  {
    id: 'artifact_context_seed',
    taskRunId: 'run_import_seed',
    type: 'context-package',
    summary: 'Keyword retrieval context generated from imported source.',
    path: 'system/rag/indexes/keyword-index.json',
    mimeType: 'application/json',
    entityRefs: [{ type: 'rag_document', id: 'rag_doc_import_seed' }],
  },
];

const createStarterTaskRunLogs = (): TaskRunLogRef[] => [
  {
    taskRunId: 'run_graph_sync_seed',
    path: 'system/runs/logs/run_graph_sync_seed.jsonl',
    entryCount: 3,
  },
  {
    taskRunId: 'run_import_seed',
    path: 'system/runs/logs/run_import_seed.jsonl',
    entryCount: 4,
  },
];

const createDefaultUiState = (): NarrativeProject['uiState'] => ({
  panes: {
    sidebarWidth: 280,
    inspectorWidth: 360,
    agentDockWidth: 320,
    writingOutlineWidth: 320,
    writingContextWidth: 340,
    isSidebarCollapsed: false,
    isAgentDockOpen: true,
    isWritingOutlineCollapsed: false,
    isWritingContextCollapsed: false,
  },
  view: {
    activeGraphBoardId: 'board_main',
    activeTimelineBranchId: 'branch_main',
    lastOpenedSceneId: 'scene_arrival',
    importSessionId: null,
  },
  density: 'comfortable',
  editorWidth: 'focused',
  motionLevel: 'full',
  experimentalFlags: ['context-menu', 'graph-canvas-pan'],
});

const createWorldSettings = (): WorldSettings => ({
  projectType: 'urban fantasy mystery',
  narrativePacing: 'tight, escalating, chapter-end hooks',
  languageStyle: 'cinematic, tactile, precise',
  narrativePerspective: 'close third person with rotating POV',
  lengthStrategy: 'supports long serial arcs and thousand-chapter expansion',
  worldRulesSummary: 'Memory shards alter political power, routes, and identity; public institutions and covert networks compete to control them.',
});

const createWorldMaps = (): WorldMapDocument[] => [
  {
    id: 'map_city_primary',
    title: 'Asterfall City Map',
    description: 'Annotated city map with route and location markers.',
    assetPath: defaultMapAsset,
    markerIds: ['marker_sky_map', 'marker_market_map', 'marker_lantern_map', 'marker_bridge_map'],
    sortOrder: 0,
  },
  {
    id: 'map_routes_overlay',
    title: 'Shadow Routes Overlay',
    description: 'Secondary map showing illicit paths and missing transit layers.',
    assetPath: defaultMapAsset,
    markerIds: ['marker_market_map', 'marker_bridge_map'],
    sortOrder: 1,
  },
];

const createSimulationEngines = (): SimulationEngine[] => [
  { id: 'engine_lab_main_scenario', name: 'Scenario Engine', type: 'scenario', summary: 'Predict likely next scenario threads.', promptOverride: 'Focus on next 3 scenario beats.', enabled: true, inputNotes: 'Use current chapters and open issues.' },
  { id: 'engine_lab_main_character', name: 'Character Engine', type: 'character', summary: 'Predict likely next character decisions.', promptOverride: 'Weight protagonist and antagonist motivations first.', enabled: true, targetCharacterId: 'char_aria' },
  { id: 'engine_lab_main_author', name: 'Author Engine', type: 'author', summary: 'Forecast twists, reversals, and pacing spikes.', promptOverride: 'Prioritize escalation and reversals every 2-3 chapters.', enabled: true },
  { id: 'engine_lab_main_reader', name: 'Reader Engine', type: 'reader', summary: 'Infer what readers may want next.', promptOverride: 'Bias toward beta reader aggregate preferences.', enabled: true },
  { id: 'engine_lab_main_logic', name: 'Logic Engine', type: 'logic', summary: 'Forecast from established story logic and constraints.', promptOverride: 'Disallow contradictions with world rules.', enabled: true },
  { id: 'engine_reviewer_logic', name: 'Reviewer Logic', type: 'logic', summary: 'Score logical consistency and point out weak causal links.', promptOverride: 'Output critique and scores only.', enabled: true },
];

const createSimulationLabs = (): SimulationLab[] => [
  {
    id: 'lab_main',
    name: 'Main Forecast Lab',
    description: 'Primary lab for predicting next developments across scenario, character, author, reader, and logic engines.',
    engineIds: ['engine_lab_main_scenario', 'engine_lab_main_character', 'engine_lab_main_author', 'engine_lab_main_reader', 'engine_lab_main_logic'],
    summary: 'Use this lab when you want a broad prediction sweep.',
  },
];

const createSimulationReviewers = (): SimulationReviewer[] => [
  {
    id: 'reviewer_main',
    name: 'Narrative Reviewer',
    description: 'Checks coherence, scores current material, and flags weaknesses.',
    engineIds: ['engine_reviewer_logic'],
    scoringNotes: 'Logic-heavy reviewer with explicit scoring output.',
  },
];

const createSimulationRuns = (): SimulationRun[] => [
  {
    id: 'sim_run_seed_lab',
    entityId: 'lab_main',
    entityType: 'lab',
    createdAt: now(),
    status: 'completed',
    output: 'Scenario engine expects a public fallout chapter, character engine expects Aria to trust Rowan reluctantly, author engine suggests a reveal reversal by chapter 3.',
  },
];

const mapSvg = encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#112032" />
      <stop offset="100%" stop-color="#0b1520" />
    </linearGradient>
  </defs>
  <rect width="1200" height="800" fill="url(#bg)" />
  <path d="M80 620 C240 470, 360 460, 470 540 S700 730, 1110 520" fill="none" stroke="#8ecae6" stroke-width="24" stroke-linecap="round" opacity="0.55" />
  <path d="M140 140 C210 210, 300 230, 430 190 S700 120, 980 220" fill="none" stroke="#d4a373" stroke-width="18" stroke-linecap="round" opacity="0.35" />
  <circle cx="250" cy="280" r="130" fill="#1d3557" opacity="0.45" />
  <circle cx="780" cy="240" r="180" fill="#264653" opacity="0.33" />
  <circle cx="620" cy="560" r="200" fill="#3a5a40" opacity="0.22" />
</svg>
`);
const defaultMapAsset = `data:image/svg+xml;charset=utf-8,${mapSvg}`;

const createStarterCharacters = (): Character[] => [
  {
    id: 'char_aria',
    name: 'Aria Solis',
    summary: 'Lead investigator chasing the memory archive theft.',
    background: 'Aria grew up in the Ember Quarter and now works as a field archivist for the Meridian Bureau.',
    aliases: ['Archivist Aria'],
    birthdayText: 'Late Frost 14',
    portraitAssetId: null,
    traits: 'Observant, stubborn, quietly compassionate',
    goals: 'Recover the stolen archive shard before the city fractures.',
    fears: 'Repeating the failure that cost her mentor.',
    secrets: 'She already touched the shard and hears fragments of future memories.',
    speechStyle: 'Precise with sudden flashes of warmth.',
    arc: 'From guarded investigator to visible leader.',
    tagIds: ['lead', 'bureau'],
    organizationIds: ['org_meridian'],
    linkedSceneIds: ['scene_arrival', 'scene_archive', 'scene_bridge'],
    linkedEventIds: ['event_arrival', 'event_shard', 'event_bridge'],
    linkedWorldItemIds: ['loc_sky_dock', 'item_memory_shard'],
    importance: 'core',
    groupKey: 'core',
    relationshipIds: ['rel_aria_rowan', 'rel_aria_seren', 'rel_aria_vesper'],
    povInsights: {
      summary: 'Aria carries the clearest POV spine and the strongest duty-vs-trust conflict.',
      scores: [
        { key: 'agency', label: 'Agency', score: 92 },
        { key: 'volatility', label: 'Volatility', score: 68 },
        { key: 'mystery', label: 'Mystery Value', score: 88 },
      ],
      radar: [
        { key: 'resolve', label: 'Resolve', score: 90 },
        { key: 'empathy', label: 'Empathy', score: 76 },
        { key: 'risk', label: 'Risk Appetite', score: 71 },
        { key: 'secrecy', label: 'Secrecy', score: 84 },
        { key: 'leadership', label: 'Leadership', score: 79 },
      ],
      source: 'placeholder',
      updatedAt: now(),
    },
    statusFlags: { protagonist: true, alive: true },
  },
  {
    id: 'char_rowan',
    name: 'Rowan Vale',
    summary: 'A disgraced tactician who knows the undercity routes.',
    background: 'Former Meridian strategist, now trading maps and rumors in the flood markets.',
    aliases: ['Map Fox'],
    birthdayText: 'Rainswell 3',
    portraitAssetId: null,
    traits: 'Dry, analytical, defensive',
    goals: 'Pay off old debts and stay out of Bureau reach.',
    fears: 'Being pulled back into command and losing autonomy.',
    secrets: 'He leaked a route chart years ago that enabled the current theft ring.',
    speechStyle: 'Short tactical sentences.',
    arc: 'From detached fixer to invested ally.',
    tagIds: ['strategist'],
    organizationIds: [],
    linkedSceneIds: ['scene_arrival', 'scene_market'],
    linkedEventIds: ['event_arrival', 'event_market'],
    linkedWorldItemIds: ['loc_flood_market'],
    importance: 'major',
    groupKey: 'major',
    relationshipIds: ['rel_aria_rowan', 'rel_rowan_nila'],
    povInsights: {
      summary: 'Rowan is a pressure-release POV with tactical ambiguity and strong decision prediction value.',
      scores: [
        { key: 'agency', label: 'Agency', score: 74 },
        { key: 'volatility', label: 'Volatility', score: 63 },
        { key: 'mystery', label: 'Mystery Value', score: 82 },
      ],
      radar: [
        { key: 'resolve', label: 'Resolve', score: 72 },
        { key: 'empathy', label: 'Empathy', score: 58 },
        { key: 'risk', label: 'Risk Appetite', score: 66 },
        { key: 'secrecy', label: 'Secrecy', score: 88 },
        { key: 'leadership', label: 'Leadership', score: 54 },
      ],
      source: 'placeholder',
      updatedAt: now(),
    },
    statusFlags: { alive: true },
  },
  {
    id: 'char_seren',
    name: 'Seren Thorne',
    summary: 'Leader of the Glass Choir opposition cell.',
    background: 'Seren rallies civic resistance against state memory control from hidden salons in Lantern Ward.',
    aliases: ['The Choir Keeper'],
    birthdayText: 'High Ember 22',
    portraitAssetId: null,
    traits: 'Charismatic, idealistic, relentless',
    goals: 'Turn the shard theft into public leverage.',
    fears: 'Compromising people she has sworn to protect.',
    secrets: 'She financed one of the thieves without knowing the full buyer chain.',
    speechStyle: 'Measured and theatrical.',
    arc: 'From agitator to reluctant coalition partner.',
    tagIds: ['opposition'],
    organizationIds: ['org_glass_choir'],
    linkedSceneIds: ['scene_choir', 'scene_bridge'],
    linkedEventIds: ['event_choir', 'event_bridge'],
    linkedWorldItemIds: ['org_glass_choir', 'loc_lantern_ward'],
    importance: 'major',
    groupKey: 'major',
    relationshipIds: ['rel_aria_seren', 'rel_seren_vesper'],
    povInsights: {
      summary: 'Seren works best as a conviction-driven POV that sharpens public stakes.',
      scores: [
        { key: 'agency', label: 'Agency', score: 85 },
        { key: 'volatility', label: 'Volatility', score: 57 },
        { key: 'mystery', label: 'Mystery Value', score: 61 },
      ],
      radar: [
        { key: 'resolve', label: 'Resolve', score: 94 },
        { key: 'empathy', label: 'Empathy', score: 81 },
        { key: 'risk', label: 'Risk Appetite', score: 75 },
        { key: 'secrecy', label: 'Secrecy', score: 46 },
        { key: 'leadership', label: 'Leadership', score: 88 },
      ],
      source: 'placeholder',
      updatedAt: now(),
    },
    statusFlags: { alive: true },
  },
  {
    id: 'char_vesper',
    name: 'Vesper Hale',
    summary: 'A polished antagonist directing the theft network.',
    background: 'Vesper fronts as a trade consul while quietly assembling a private memory market.',
    aliases: ['Consul Hale'],
    birthdayText: 'Ashfall 9',
    portraitAssetId: null,
    traits: 'Elegant, patient, manipulative',
    goals: 'Monopolize shard access before the city council reacts.',
    fears: 'Losing narrative control and public image.',
    secrets: 'He orchestrated the bridge collapse years ago to erase a witness circle.',
    speechStyle: 'Soft, surgical, never hurried.',
    arc: 'Antagonist hidden in plain sight.',
    tagIds: ['antagonist'],
    organizationIds: ['org_black_tide'],
    linkedSceneIds: ['scene_consul', 'scene_bridge'],
    linkedEventIds: ['event_shard', 'event_bridge'],
    linkedWorldItemIds: ['org_black_tide', 'item_memory_shard'],
    importance: 'core',
    groupKey: 'core',
    relationshipIds: ['rel_aria_vesper', 'rel_seren_vesper'],
    povInsights: {
      summary: 'Vesper is a high-control antagonist POV best used sparingly for precision reveals.',
      scores: [
        { key: 'agency', label: 'Agency', score: 89 },
        { key: 'volatility', label: 'Volatility', score: 44 },
        { key: 'mystery', label: 'Mystery Value', score: 95 },
      ],
      radar: [
        { key: 'resolve', label: 'Resolve', score: 87 },
        { key: 'empathy', label: 'Empathy', score: 28 },
        { key: 'risk', label: 'Risk Appetite', score: 52 },
        { key: 'secrecy', label: 'Secrecy', score: 97 },
        { key: 'leadership', label: 'Leadership', score: 83 },
      ],
      source: 'placeholder',
      updatedAt: now(),
    },
    statusFlags: { antagonist: true, alive: true },
  },
  {
    id: 'char_nila',
    name: 'Nila Quill',
    summary: 'Cartographer and world-map specialist for the Bureau.',
    background: 'Nila maintains the city map overlays and traces route anomalies faster than anyone else.',
    aliases: ['Linekeeper'],
    birthdayText: 'Riversend 18',
    portraitAssetId: null,
    traits: 'Playful, obsessive, kind under pressure',
    goals: 'Prove the theft route crosses impossible map layers.',
    fears: 'Being treated as support instead of primary analyst.',
    secrets: 'She has been feeding Seren anonymized transit data.',
    speechStyle: 'Fast, diagram-heavy explanations.',
    arc: 'Support specialist who becomes indispensable.',
    tagIds: ['cartographer'],
    organizationIds: ['org_meridian'],
    linkedSceneIds: ['scene_archive', 'scene_bridge'],
    linkedEventIds: ['event_shard', 'event_bridge'],
    linkedWorldItemIds: ['item_city_map'],
    importance: 'supporting',
    groupKey: 'supporting',
    relationshipIds: ['rel_rowan_nila'],
    povInsights: {
      summary: 'Nila adds analytic clarity and map-centric exposition without stalling pace.',
      scores: [
        { key: 'agency', label: 'Agency', score: 67 },
        { key: 'volatility', label: 'Volatility', score: 51 },
        { key: 'mystery', label: 'Mystery Value', score: 72 },
      ],
      radar: [
        { key: 'resolve', label: 'Resolve', score: 69 },
        { key: 'empathy', label: 'Empathy', score: 73 },
        { key: 'risk', label: 'Risk Appetite', score: 48 },
        { key: 'secrecy', label: 'Secrecy', score: 58 },
        { key: 'leadership', label: 'Leadership', score: 44 },
      ],
      source: 'placeholder',
      updatedAt: now(),
    },
    statusFlags: { alive: true },
  },
];

const createWorldContainers = (): WorldContainer[] => [
  { id: 'cont_locations', name: 'Locations', type: 'notebook', isDefault: true },
  { id: 'cont_orgs', name: 'Organizations', type: 'graph', isDefault: true },
  { id: 'cont_items', name: 'Items', type: 'notebook', isDefault: true },
  { id: 'cont_lore', name: 'Lore', type: 'notebook', isDefault: true },
  { id: 'cont_world_map', name: 'World Map', type: 'map', isDefault: true },
  { id: 'cont_notes', name: 'Notes', type: 'notebook', isDefault: true },
];

const createWorldItems = (): WorldItem[] => [
  {
    id: 'loc_sky_dock',
    containerId: 'cont_locations',
    type: 'location',
    name: 'Sky Dock',
    description: 'The upper docking ring where official arrivals and silent inspections happen.',
    attributes: [{ key: 'District', value: 'North Elevation' }],
    linkedCharacterIds: ['char_aria', 'char_rowan'],
    linkedEventIds: ['event_arrival'],
    linkedSceneIds: ['scene_arrival'],
    mapMarkers: [{ id: 'marker_sky', label: 'Sky Dock', x: 0.23, y: 0.21, linkedEntityId: 'loc_sky_dock' }],
    assetPath: null,
    tagIds: ['arrival'],
  },
  {
    id: 'loc_flood_market',
    containerId: 'cont_locations',
    type: 'location',
    name: 'Flood Market',
    description: 'An undercity bazaar rebuilt around old water channels and rumor traders.',
    attributes: [{ key: 'Mood', value: 'Noisy, unstable, transactional' }],
    linkedCharacterIds: ['char_rowan'],
    linkedEventIds: ['event_market'],
    linkedSceneIds: ['scene_market'],
    mapMarkers: [{ id: 'marker_market', label: 'Flood Market', x: 0.41, y: 0.66, linkedEntityId: 'loc_flood_market' }],
    assetPath: null,
    tagIds: ['undercity'],
  },
  {
    id: 'loc_lantern_ward',
    containerId: 'cont_locations',
    type: 'location',
    name: 'Lantern Ward',
    description: 'A cultural quarter of salons, hidden stages, and encrypted meeting houses.',
    attributes: [{ key: 'Security', value: 'Civilian cover with hidden sentries' }],
    linkedCharacterIds: ['char_seren'],
    linkedEventIds: ['event_choir'],
    linkedSceneIds: ['scene_choir'],
    mapMarkers: [{ id: 'marker_lantern', label: 'Lantern Ward', x: 0.68, y: 0.28, linkedEntityId: 'loc_lantern_ward' }],
    assetPath: null,
    tagIds: ['culture'],
  },
  {
    id: 'loc_glass_bridge',
    containerId: 'cont_locations',
    type: 'location',
    name: 'Glass Bridge',
    description: 'A suspended transit line where the decisive interception will happen.',
    attributes: [{ key: 'Risk', value: 'High vertical exposure' }],
    linkedCharacterIds: ['char_aria', 'char_seren', 'char_vesper'],
    linkedEventIds: ['event_bridge'],
    linkedSceneIds: ['scene_bridge'],
    mapMarkers: [{ id: 'marker_bridge', label: 'Glass Bridge', x: 0.59, y: 0.5, linkedEntityId: 'loc_glass_bridge' }],
    assetPath: null,
    tagIds: ['climax'],
  },
  {
    id: 'org_meridian',
    containerId: 'cont_orgs',
    type: 'organization',
    name: 'Meridian Bureau',
    description: 'State archive agency responsible for memory shard custody and route surveillance.',
    attributes: [{ key: 'Alignment', value: 'Official' }],
    linkedCharacterIds: ['char_aria', 'char_nila'],
    linkedEventIds: ['event_arrival', 'event_shard'],
    linkedSceneIds: ['scene_archive'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['bureau'],
  },
  {
    id: 'org_glass_choir',
    containerId: 'cont_orgs',
    type: 'organization',
    name: 'Glass Choir',
    description: 'Civic opposition network that opposes controlled-memory monopolies.',
    attributes: [{ key: 'Alignment', value: 'Resistance' }],
    linkedCharacterIds: ['char_seren'],
    linkedEventIds: ['event_choir'],
    linkedSceneIds: ['scene_choir'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['resistance'],
  },
  {
    id: 'org_black_tide',
    containerId: 'cont_orgs',
    type: 'organization',
    name: 'Black Tide Consortium',
    description: 'A covert broker network moving restricted knowledge and recovered artifacts.',
    attributes: [{ key: 'Alignment', value: 'Hostile market network' }],
    linkedCharacterIds: ['char_vesper'],
    linkedEventIds: ['event_shard'],
    linkedSceneIds: ['scene_consul'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['antagonist'],
  },
  {
    id: 'item_memory_shard',
    containerId: 'cont_items',
    type: 'item',
    name: 'Memory Shard',
    description: 'The artifact at the center of the theft and every faction objective.',
    attributes: [{ key: 'State', value: 'Fragmented but active' }],
    linkedCharacterIds: ['char_aria', 'char_vesper'],
    linkedEventIds: ['event_shard', 'event_bridge'],
    linkedSceneIds: ['scene_archive', 'scene_bridge'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['artifact'],
  },
  {
    id: 'item_city_map',
    containerId: 'cont_items',
    type: 'item',
    name: 'Layered City Map',
    description: 'Nila\'s annotated atlas revealing impossible route overlays.',
    attributes: [{ key: 'Status', value: 'Updated hourly' }],
    linkedCharacterIds: ['char_nila'],
    linkedEventIds: ['event_bridge'],
    linkedSceneIds: ['scene_archive'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['map'],
  },
  {
    id: 'lore_memory_tax',
    containerId: 'cont_lore',
    type: 'lore',
    name: 'Memory Tax',
    description: 'A public levy that allows the state to record and resell fragments of civic memory.',
    attributes: [{ key: 'Effect', value: 'Fuel for unrest' }],
    linkedCharacterIds: ['char_seren', 'char_aria'],
    linkedEventIds: ['event_choir'],
    linkedSceneIds: ['scene_choir'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['policy'],
  },
  {
    id: 'map_city',
    containerId: 'cont_world_map',
    type: 'map',
    name: 'Asterfall City Map',
    description: 'Annotated base map used for route, location, and pursuit planning.',
    attributes: [{ key: 'Revision', value: '3.2' }],
    linkedCharacterIds: ['char_nila'],
    linkedEventIds: ['event_bridge'],
    linkedSceneIds: ['scene_bridge'],
    mapMarkers: [
      { id: 'marker_sky_map', label: 'Sky Dock', x: 0.23, y: 0.21, linkedEntityId: 'loc_sky_dock' },
      { id: 'marker_market_map', label: 'Flood Market', x: 0.41, y: 0.66, linkedEntityId: 'loc_flood_market' },
      { id: 'marker_lantern_map', label: 'Lantern Ward', x: 0.68, y: 0.28, linkedEntityId: 'loc_lantern_ward' },
      { id: 'marker_bridge_map', label: 'Glass Bridge', x: 0.59, y: 0.5, linkedEntityId: 'loc_glass_bridge' },
    ],
    assetPath: defaultMapAsset,
    tagIds: ['map'],
  },
  {
    id: 'note_open_questions',
    containerId: 'cont_notes',
    type: 'note',
    name: 'Open Questions',
    description: 'List of unresolved motives and route contradictions.',
    attributes: [{ key: 'Owner', value: 'Workbench' }],
    linkedCharacterIds: ['char_aria', 'char_vesper'],
    linkedEventIds: ['event_shard'],
    linkedSceneIds: ['scene_archive'],
    mapMarkers: [],
    assetPath: null,
    tagIds: ['todo'],
  },
];

const createStarterBranches = (): TimelineBranch[] => [
  { id: 'branch_main', name: 'Main Investigation', description: 'Primary narrative thread.', parentBranchId: null, forkEventId: null, mergeEventId: 'event_merge_public', color: '#f59e0b', sortOrder: 0, collapsed: false, mode: 'root', startAnchor: null, endMode: 'open', mergeTargetBranchId: null, geometry: { laneOffset: 0, bend: 0.18, thickness: 1 } },
  { id: 'branch_shadow', name: 'Shadow Routes', description: 'Undercity movements and hidden handoffs.', parentBranchId: 'branch_main', forkEventId: 'event_arrival', mergeEventId: 'event_bridge', color: '#38bdf8', sortOrder: 1, collapsed: false, mode: 'forked', startAnchor: { branchId: 'branch_main', eventId: 'event_arrival' }, endMode: 'merge', mergeTargetBranchId: 'branch_main', geometry: { laneOffset: -90, bend: 0.36, thickness: 1 } },
  { id: 'branch_public', name: 'Public Pressure', description: 'Political and civic fallout.', parentBranchId: 'branch_main', forkEventId: 'event_arrival', mergeEventId: 'event_merge_public', color: '#22c55e', sortOrder: 2, collapsed: false, mode: 'forked', startAnchor: { branchId: 'branch_main', eventId: 'event_arrival' }, endMode: 'merge', mergeTargetBranchId: 'branch_main', geometry: { laneOffset: 110, bend: 0.28, thickness: 1 } },
];

const createStarterEvents = (): TimelineEvent[] => [
  {
    id: 'event_arrival',
    title: 'Arrival at Sky Dock',
    summary: 'Aria reaches the city ring and recruits Rowan to trace the first courier route.',
    time: 'Day 1 - Dawn',
    branchId: 'branch_main',
    orderIndex: 0,
    locationIds: ['loc_sky_dock'],
    participantCharacterIds: ['char_aria', 'char_rowan'],
    linkedSceneIds: ['scene_arrival'],
    linkedWorldItemIds: ['loc_sky_dock'],
    tags: ['arrival'],
    sharedBranchIds: ['branch_shadow', 'branch_public'],
    importance: 'high',
    colorToken: 'amber',
    layoutLock: true,
    modalStateHints: ['fork-anchor'],
  },
  {
    id: 'event_market',
    title: 'Market Route Leak',
    summary: 'A hidden seller exposes a transit path that should not exist on official maps.',
    time: 'Day 1 - Midday',
    branchId: 'branch_shadow',
    orderIndex: 0,
    locationIds: ['loc_flood_market'],
    participantCharacterIds: ['char_rowan', 'char_nila'],
    linkedSceneIds: ['scene_market'],
    linkedWorldItemIds: ['item_city_map'],
    tags: ['intel'],
    importance: 'medium',
    colorToken: 'sky',
    layoutLock: false,
    modalStateHints: ['branch-shadow'],
  },
  {
    id: 'event_choir',
    title: 'Choir Salon Meeting',
    summary: 'Seren reveals the public stakes and offers civilian support in exchange for truth.',
    time: 'Day 1 - Night',
    branchId: 'branch_public',
    orderIndex: 0,
    locationIds: ['loc_lantern_ward'],
    participantCharacterIds: ['char_aria', 'char_seren'],
    linkedSceneIds: ['scene_choir'],
    linkedWorldItemIds: ['lore_memory_tax', 'org_glass_choir'],
    tags: ['politics'],
    importance: 'medium',
    colorToken: 'emerald',
    layoutLock: false,
    modalStateHints: ['branch-public'],
  },
  {
    id: 'event_shard',
    title: 'Archive Breach Review',
    summary: 'The team reconstructs how the Memory Shard was stolen from a locked chamber.',
    time: 'Day 2 - Morning',
    branchId: 'branch_main',
    orderIndex: 1,
    locationIds: ['loc_sky_dock'],
    participantCharacterIds: ['char_aria', 'char_nila', 'char_vesper'],
    linkedSceneIds: ['scene_archive', 'scene_consul'],
    linkedWorldItemIds: ['item_memory_shard', 'org_meridian'],
    tags: ['artifact'],
    importance: 'high',
    colorToken: 'amber',
    layoutLock: false,
    modalStateHints: ['mainline'],
  },
  {
    id: 'event_bridge',
    title: 'Bridge Intercept',
    summary: 'All branches converge as the shard convoy attempts to cross the Glass Bridge.',
    time: 'Day 2 - Sunset',
    branchId: 'branch_main',
    orderIndex: 2,
    locationIds: ['loc_glass_bridge'],
    participantCharacterIds: ['char_aria', 'char_seren', 'char_vesper', 'char_nila'],
    linkedSceneIds: ['scene_bridge'],
    linkedWorldItemIds: ['loc_glass_bridge', 'item_memory_shard', 'item_city_map'],
    tags: ['climax'],
    sharedBranchIds: ['branch_shadow'],
    importance: 'critical',
    colorToken: 'red',
    layoutLock: true,
    modalStateHints: ['merge-anchor'],
  },
  {
    id: 'event_merge_public',
    title: 'Emergency Public Hearing',
    summary: 'The political fallout merges back into the main investigation after the bridge clash.',
    time: 'Day 3 - Morning',
    branchId: 'branch_main',
    orderIndex: 3,
    locationIds: ['loc_glass_bridge'],
    participantCharacterIds: ['char_aria', 'char_seren'],
    linkedSceneIds: [],
    linkedWorldItemIds: ['loc_glass_bridge'],
    tags: ['merge'],
    sharedBranchIds: ['branch_public'],
    importance: 'high',
    colorToken: 'emerald',
    layoutLock: true,
    modalStateHints: ['merge-anchor'],
  },
];

const createStarterChapters = (): Chapter[] => [
  {
    id: 'chap_1',
    title: 'Fractured Arrival',
    summary: 'The investigation begins and the first hidden route surfaces.',
    goal: 'Establish the cast, the city, and the theft stakes.',
    notes: 'Chapter one should feel investigative and urban.',
    sceneIds: ['scene_arrival', 'scene_market'],
    orderIndex: 0,
    status: 'draft',
  },
  {
    id: 'chap_2',
    title: 'Pressure Lines',
    summary: 'Political pressure, archive reconstruction, and the bridge setup collide.',
    goal: 'Align the public, covert, and personal stakes before the intercept.',
    notes: 'Chapter two should cross-cut between official and civilian spaces.',
    sceneIds: ['scene_choir', 'scene_archive', 'scene_consul', 'scene_bridge'],
    orderIndex: 1,
    status: 'revised',
  },
];

const createStarterScenes = (): Scene[] => [
  {
    id: 'scene_arrival',
    chapterId: 'chap_1',
    title: 'Dockside Arrival',
    summary: 'Aria reaches Asterfall and persuades Rowan to guide her below the official transit lines.',
    content: 'Aria stepped off the lift into the Sky Dock haze, where the city smelled like cold copper and stormwater. Rowan waited beside a stack of confiscated trunks, already bored by her questions and curious in spite of himself.',
    orderIndex: 0,
    povCharacterId: 'char_aria',
    linkedCharacterIds: ['char_aria', 'char_rowan'],
    linkedEventIds: ['event_arrival'],
    linkedWorldItemIds: ['loc_sky_dock'],
    status: 'draft',
  },
  {
    id: 'scene_market',
    chapterId: 'chap_1',
    title: 'Flood Market Line',
    summary: 'Rowan and Nila compare impossible route markings beneath the market canopies.',
    content: 'Below the market awnings, Nila unrolled her layered city map across a tea crate. Rowan pointed to a corridor no patrol report admitted existed, and the ink shimmered as though the city itself disliked being found.',
    orderIndex: 1,
    povCharacterId: 'char_rowan',
    linkedCharacterIds: ['char_rowan', 'char_nila'],
    linkedEventIds: ['event_market'],
    linkedWorldItemIds: ['loc_flood_market', 'item_city_map'],
    status: 'draft',
  },
  {
    id: 'scene_choir',
    chapterId: 'chap_2',
    title: 'Choir in Lantern Ward',
    summary: 'Seren lays out the public consequences of the theft and asks Aria to choose transparency.',
    content: 'Seren did not greet Aria with suspicion but with receipts, witness statements, and names of families priced out of their own memories. The room listened for Aria\'s answer before anyone reached for wine.',
    orderIndex: 0,
    povCharacterId: 'char_seren',
    linkedCharacterIds: ['char_aria', 'char_seren'],
    linkedEventIds: ['event_choir'],
    linkedWorldItemIds: ['loc_lantern_ward', 'lore_memory_tax', 'org_glass_choir'],
    status: 'revised',
  },
  {
    id: 'scene_archive',
    chapterId: 'chap_2',
    title: 'Archive Reconstruction',
    summary: 'Aria and Nila discover the shard breach overlaps with erased route layers.',
    content: 'The breach looked surgical until Nila overlaid the transit lines. Then the theft became choreography: a convoy stepping between map revisions, using the city\'s own forgotten seams as cover.',
    orderIndex: 1,
    povCharacterId: 'char_nila',
    linkedCharacterIds: ['char_aria', 'char_nila'],
    linkedEventIds: ['event_shard'],
    linkedWorldItemIds: ['item_memory_shard', 'item_city_map', 'org_meridian'],
    status: 'revised',
  },
  {
    id: 'scene_consul',
    chapterId: 'chap_2',
    title: 'Consul\'s Smile',
    summary: 'Vesper publicly performs calm while privately steering the breach review.',
    content: 'Vesper spoke like a man tidying an inconvenience rather than defending a crime scene. Every answer he offered was elegant, plausible, and positioned exactly one step away from the truth.',
    orderIndex: 2,
    povCharacterId: 'char_vesper',
    linkedCharacterIds: ['char_vesper', 'char_aria'],
    linkedEventIds: ['event_shard'],
    linkedWorldItemIds: ['org_black_tide', 'item_memory_shard'],
    status: 'draft',
  },
  {
    id: 'scene_bridge',
    chapterId: 'chap_2',
    title: 'Glass Bridge Intercept',
    summary: 'All threads converge at the bridge as the convoy attempts its escape.',
    content: 'By the time the convoy reached the Glass Bridge, every alliance had already become conditional. Aria tracked the shard, Seren controlled the crowd, Nila corrected the map in real time, and Vesper smiled like he had authored the weather.',
    orderIndex: 3,
    povCharacterId: 'char_aria',
    linkedCharacterIds: ['char_aria', 'char_seren', 'char_vesper', 'char_nila'],
    linkedEventIds: ['event_bridge'],
    linkedWorldItemIds: ['loc_glass_bridge', 'item_memory_shard', 'item_city_map'],
    status: 'draft',
  },
];

const createStarterRelationships = (): Relationship[] => [
  { id: 'rel_aria_rowan', sourceId: 'char_aria', targetId: 'char_rowan', type: 'Uneasy alliance', description: 'Professional trust forming under pressure.', category: 'alliance', directionality: 'bidirectional', status: 'active', sourceNotes: 'Starts transactional, trends toward trust.' },
  { id: 'rel_aria_seren', sourceId: 'char_aria', targetId: 'char_seren', type: 'Negotiated trust', description: 'They need each other but disagree on exposure.', category: 'political', directionality: 'bidirectional', status: 'strained', sourceNotes: 'Useful alliance with ideological friction.' },
  { id: 'rel_aria_vesper', sourceId: 'char_aria', targetId: 'char_vesper', type: 'Hidden rivalry', description: 'Aria suspects Vesper before she can prove it.', category: 'conflict', directionality: 'source_to_target', status: 'active', sourceNotes: 'Suspicion escalates across archive and bridge scenes.' },
  { id: 'rel_rowan_nila', sourceId: 'char_rowan', targetId: 'char_nila', type: 'Tactical banter', description: 'A fast-moving analyst duo.', category: 'alliance', directionality: 'bidirectional', status: 'active', sourceNotes: 'High chemistry in route-analysis scenes.' },
  { id: 'rel_seren_vesper', sourceId: 'char_seren', targetId: 'char_vesper', type: 'Political opposition', description: 'They understand each other too well.', category: 'conflict', directionality: 'bidirectional', status: 'active', sourceNotes: 'Public and covert power centers collide here.' },
];

const createStarterBoards = (): GraphBoard[] => [
  {
    id: 'board_main',
    name: 'Main Storyboard',
    description: 'Mixed-mode board for sketching conflicts, routes, and sync candidates.',
    nodes: [
      { id: 'graph_char_aria', kind: 'character_ref', label: 'Aria Solis', description: 'Lead investigator card.', x: 80, y: 80, width: 220, height: 170, linkedEntityId: 'char_aria', linkedEntityType: 'character', imageAssetId: null },
      { id: 'graph_event_bridge', kind: 'event_ref', label: 'Bridge Intercept', description: 'Climax event card.', x: 390, y: 90, width: 240, height: 170, linkedEntityId: 'event_bridge', linkedEntityType: 'timeline_event', imageAssetId: null },
      { id: 'graph_loc_bridge', kind: 'location_ref', label: 'Glass Bridge', description: 'Climax location node.', x: 720, y: 110, width: 230, height: 160, linkedEntityId: 'loc_glass_bridge', linkedEntityType: 'world_item', imageAssetId: null },
      { id: 'graph_item_shard', kind: 'world_item_ref', label: 'Memory Shard', description: 'Central artifact.', x: 420, y: 320, width: 230, height: 160, linkedEntityId: 'item_memory_shard', linkedEntityType: 'world_item', imageAssetId: null },
      { id: 'graph_note_public', kind: 'free_note', label: 'Public fallout escalates after bridge damage', description: 'Potential expansion for Chapter 3.', x: 95, y: 360, width: 260, height: 180, linkedEntityId: null, linkedEntityType: null, imageAssetId: null },
      { id: 'graph_image_city', kind: 'image_card', label: 'City mood board', description: 'Reference texture for Asterfall.', x: 720, y: 340, width: 230, height: 180, linkedEntityId: null, linkedEntityType: null, imageAssetId: defaultMapAsset },
      { id: 'graph_frame_climax', kind: 'group_frame', label: 'Climax cluster', description: 'All elements needed for the intercept.', x: 360, y: 40, width: 620, height: 500, linkedEntityId: null, linkedEntityType: null, imageAssetId: null },
    ],
    edges: [
      { id: 'edge_aria_bridge', sourceId: 'graph_char_aria', targetId: 'graph_event_bridge', label: 'drives' },
      { id: 'edge_bridge_loc', sourceId: 'graph_event_bridge', targetId: 'graph_loc_bridge', label: 'happens at' },
      { id: 'edge_bridge_shard', sourceId: 'graph_event_bridge', targetId: 'graph_item_shard', label: 'centers on' },
      { id: 'edge_note_bridge', sourceId: 'graph_note_public', targetId: 'graph_event_bridge', label: 'aftershock' },
    ],
    view: { zoom: 1, panX: 0, panY: 0 },
    selectedNodeIds: [],
    sortOrder: 0,
  },
  {
    id: 'board_relationships',
    name: 'Relationship Tensions',
    description: 'Character pressure map for alliance and betrayal analysis.',
    nodes: [
      { id: 'graph_rel_aria', kind: 'character_ref', label: 'Aria', description: 'Anchor point.', x: 220, y: 180, width: 180, height: 120, linkedEntityId: 'char_aria', linkedEntityType: 'character', imageAssetId: null },
      { id: 'graph_rel_seren', kind: 'character_ref', label: 'Seren', description: 'Public pressure axis.', x: 480, y: 80, width: 180, height: 120, linkedEntityId: 'char_seren', linkedEntityType: 'character', imageAssetId: null },
      { id: 'graph_rel_vesper', kind: 'character_ref', label: 'Vesper', description: 'Hidden threat axis.', x: 690, y: 250, width: 180, height: 120, linkedEntityId: 'char_vesper', linkedEntityType: 'character', imageAssetId: null },
      { id: 'graph_rel_rowan', kind: 'character_ref', label: 'Rowan', description: 'Shadow logistics.', x: 360, y: 330, width: 180, height: 120, linkedEntityId: 'char_rowan', linkedEntityType: 'character', imageAssetId: null },
    ],
    edges: [
      { id: 'edge_rel_a_s', sourceId: 'graph_rel_aria', targetId: 'graph_rel_seren', label: 'trust / leverage' },
      { id: 'edge_rel_a_v', sourceId: 'graph_rel_aria', targetId: 'graph_rel_vesper', label: 'suspects' },
      { id: 'edge_rel_a_r', sourceId: 'graph_rel_aria', targetId: 'graph_rel_rowan', label: 'needs' },
    ],
    view: { zoom: 0.95, panX: 0, panY: 0 },
    selectedNodeIds: [],
    sortOrder: 1,
  },
];

const createStarterImportJobs = (): ImportJob[] => [
  {
    id: 'import_seed_project',
    sourceFileName: 'starter-manuscript.md',
    sourcePath: 'system/imports/staging/import_seed_project/source.md',
    sourceFormat: 'md',
    status: 'awaiting_user_input',
    stage: 'proposal_generated',
    segmentationConfidence: 'high',
    createdAt: now(),
    updatedAt: now(),
    taskRequestId: 'task_import_seed',
    taskRunId: 'run_import_seed',
    canonicalChapterIds: ['chap_1', 'chap_2'],
    canonicalSceneIds: ['scene_arrival', 'scene_market', 'scene_choir', 'scene_archive', 'scene_consul', 'scene_bridge'],
    chapterCandidates: [
      { id: 'import_chap_1', title: 'Fractured Arrival', summary: 'Imported from markdown heading.', confidence: 'high', contentPath: 'system/imports/staging/import_seed_project/chapter_candidates.json' },
      { id: 'import_chap_2', title: 'Pressure Lines', summary: 'Imported from markdown heading.', confidence: 'high', contentPath: 'system/imports/staging/import_seed_project/chapter_candidates.json' },
    ],
    sceneCandidates: [
      { id: 'import_scene_arrival', title: 'Dockside Arrival', summary: 'Imported from second-level heading.', confidence: 'high', contentPath: 'system/imports/staging/import_seed_project/scene_candidates.json' },
      { id: 'import_scene_bridge', title: 'Glass Bridge Intercept', summary: 'Imported from second-level heading.', confidence: 'high', contentPath: 'system/imports/staging/import_seed_project/scene_candidates.json' },
    ],
    proposalIds: ['proposal_import_entities_seed'],
    issueIds: [],
    notes: ['Deterministic chapter split succeeded.', 'Metadata extraction is staged behind Workbench review.'],
  },
];

const createPromptTemplate = (
  id: PromptTemplate['id'],
  name: string,
  agentType: PromptTemplate['agentType'],
  purpose: string,
  reviewPolicy: PromptTemplate['reviewPolicy'],
  promptTemplate: string,
  userSlot: string,
  extraSlots: PromptTemplate['promptTemplateSlots'],
  requiresWorkbenchReview: boolean,
): PromptTemplate => ({
  id,
  name,
  agentType,
  purpose,
  inputContract: [
    { name: 'project_context', description: 'Canonical project snapshot or scoped entity references.', required: true },
    { name: 'task_input', description: 'Agent-specific input payload.', required: true },
  ],
  outputContract: [
    { name: 'artifacts', description: 'Structured output artifacts for downstream storage.', required: true },
    { name: 'review_notes', description: 'Notes for Workbench or operator review.', required: true },
  ],
  reviewPolicy,
  promptTemplate,
  userCustomPromptSlot: userSlot,
  modelHints: ['Prefer structured JSON output.', 'Never mutate canonical data directly.'],
  version: 1,
  promptTemplateSlots: extraSlots,
  forbiddenActions: [
    'Do not write directly to canonical entities or scene files.',
    'Do not invent missing facts without flagging uncertainty.',
  ],
  writeTargets: requiresWorkbenchReview ? ['proposal', 'issue', 'artifact', 'run_log'] : ['artifact', 'run_log'],
  requiresWorkbenchReview,
});

const createStarterPromptTemplates = (): PromptTemplate[] => [
  createPromptTemplate(
    'import-agent',
    'Import Agent',
    'import-agent',
    'Import raw novel files and produce canonical-safe chapter/scene skeletons plus review artifacts.',
    'manual_workbench',
    `Agent Goal:
Import raw manuscript content and extract deterministic structure only.

Inputs:
- source document
- import config
- canonical project snapshot

Outputs:
- import manifest
- chapter/scene candidates
- import review proposals

Forbidden:
- no silent metadata writes
- no direct mutation of canonical world or character entities

Review Boundary:
- all inferred metadata must go to Workbench

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '导入时的额外偏好，例如章节点切分偏好。', example: '优先保留原文章节名，不要自动润色。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '项目通用风格和命名约束。', example: '角色和地点命名尽量沿用原文译名。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '模型输出格式或长度约束。', example: '输出仅限 JSON。' },
    ],
    true,
  ),
  createPromptTemplate(
    'metadata-extraction-agent',
    'Metadata Extraction Agent',
    'metadata-extraction-agent',
    'Extract characters, locations, organizations, events, and world facts as proposals with uncertainty notes.',
    'manual_workbench',
    `Agent Goal:
Extract metadata from novel/script chunks into proposal-ready entities.

Inputs:
- source chunks
- known entities
- import or retrieval context

Outputs:
- entity proposals
- link proposals
- uncertainty notes

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '你希望重点抽取的元数据类型。', example: '优先抽取组织和地点。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '实体命名和摘要风格规则。', example: '世界观条目用简短百科语气。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '模型特定输出格式要求。', example: '置信度使用 high/medium/low。' },
    ],
    true,
  ),
  createPromptTemplate(
    'retrieval-agent',
    'Retrieval Agent',
    'retrieval-agent',
    'Retrieve local project context from the keyword RAG layer without mutating canonical data.',
    'artifact_only',
    `Agent Goal:
Return the most relevant local context package for a given query.

Inputs:
- retrieval query
- scope filters
- local RAG manifest

Outputs:
- retrieved chunks
- entity matches
- context package

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '检索偏好，例如召回更重角色或场景。', example: '优先返回和角色动机相关的片段。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '上下文包的表达偏好。', example: '摘要尽量简短，方便写作 agent 消费。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '模型运行时注意事项。', example: '输出不超过 8 个 chunk。' },
    ],
    false,
  ),
  createPromptTemplate(
    'novel-writing-agent',
    'Novel Writing Agent',
    'novel-writing-agent',
    'Produce scene/chapter drafts, rewrites, or alternatives from structured context.',
    'manual_workbench',
    `Agent Goal:
Assist with novel chapter or scene writing while preserving canonical consistency.

Inputs:
- scene brief
- context package
- style guide

Outputs:
- draft
- rewrite alternatives
- editorial notes

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[STORY_STYLE_REQUIREMENTS]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '这次写作任务的具体要求。', example: '强调压迫感和调查推进。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '项目级长期风格要求。', example: '保持第三人称近距离视角。' },
      { token: '[[STORY_STYLE_REQUIREMENTS]]', description: '当前故事段落的风格要求。', example: '更 noir、更克制。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '模型长度或格式限制。', example: '先给 2 个版本，不要自动决定。' },
    ],
    true,
  ),
  createPromptTemplate(
    'script-writing-agent',
    'Script Writing Agent',
    'script-writing-agent',
    'Adapt novel material into script episodes, scenes, and dialogue blocks.',
    'manual_workbench',
    `Agent Goal:
Turn novel or outline content into script drafts suitable for review and storyboard planning.

Inputs:
- source scenes or outline
- metadata
- style guide

Outputs:
- script draft
- episode breakdown
- dialogue blocks

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[SCRIPT_STYLE_REQUIREMENTS]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '这次剧本任务的具体目标。', example: '改编成短剧第一集，节奏更快。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '项目通用风格要求。', example: '人物对白要保留原著辨识度。' },
      { token: '[[SCRIPT_STYLE_REQUIREMENTS]]', description: '剧本格式和节奏偏好。', example: '对白短促，动作提示清晰。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '模型输出约束。', example: '输出 Fountain 风格文本。' },
    ],
    true,
  ),
  createPromptTemplate(
    'storyboard-shot-planning-agent',
    'Storyboard / Shot Planning Agent',
    'storyboard-shot-planning-agent',
    'Plan shots and prompt packages from scripts and linked project metadata.',
    'manual_workbench',
    `Agent Goal:
Create shot lists and visual prompt packages from approved scripts.

Inputs:
- script
- character/location metadata
- visual style notes

Outputs:
- storyboard notes
- shot list
- prompt package

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[VIDEO_STYLE_REQUIREMENTS]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '分镜重点，例如镜头密度或人物优先级。', example: '每场戏控制在 6 个镜头以内。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '项目级视觉叙事要求。', example: '保持工业奇幻视觉基调。' },
      { token: '[[VIDEO_STYLE_REQUIREMENTS]]', description: '视频或短剧风格要求。', example: '偏短剧竖屏节奏，强近景。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '模型输出限制。', example: '每个 shot 都给一句 visual prompt。' },
    ],
    true,
  ),
  createPromptTemplate(
    'video-generation-orchestration-agent',
    'Video Generation Orchestration Agent',
    'video-generation-orchestration-agent',
    'Transform prompt packages into provider-ready video tasks and status artifacts.',
    'manual_workbench',
    `Agent Goal:
Prepare provider-ready video generation tasks without pretending generation has already succeeded.

Inputs:
- shot plan
- provider config
- asset refs

Outputs:
- video task requests
- provider payloads
- failure or pending logs

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[VIDEO_STYLE_REQUIREMENTS]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '编排要求，例如 provider 选择或批次大小。', example: '优先拆成 shot 级任务。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '项目全局约束。', example: '人物设定不能与 canonical metadata 冲突。' },
      { token: '[[VIDEO_STYLE_REQUIREMENTS]]', description: '视频风格要求。', example: '冷色调、低饱和、悬疑感。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: 'provider 或模型注意事项。', example: '如果 provider 未配置，只输出 placeholder artifact。' },
    ],
    true,
  ),
  createPromptTemplate(
    'qa-consistency-agent',
    'QA / Consistency Agent',
    'qa-consistency-agent',
    'Review novel/script/project metadata and emit issues or fix proposals.',
    'manual_workbench',
    `Agent Goal:
Find consistency issues and propose safe fixes.

Inputs:
- project metadata
- novel/script content
- retrieval context

Outputs:
- issues
- fix suggestions
- review proposals

User Slots:
${'[[USER_CUSTOM_REQUIREMENTS]]'}
${'[[PROJECT_STYLE_GUIDE]]'}
${'[[MODEL_SPECIFIC_NOTES]]'}`,
    '[[USER_CUSTOM_REQUIREMENTS]]',
    [
      { token: '[[USER_CUSTOM_REQUIREMENTS]]', description: '你当前最关心的 QA 范围。', example: '重点检查角色时间线和地点连续性。' },
      { token: '[[PROJECT_STYLE_GUIDE]]', description: '项目级审校偏好。', example: '尽量保守，不要提出风格性重写。' },
      { token: '[[MODEL_SPECIFIC_NOTES]]', description: '输出要求。', example: '每个 issue 必须附带 evidence。' },
    ],
    true,
  ),
];

const createStarterScripts = (): ScriptDocument[] => [
  {
    id: 'script_episode_1',
    title: 'Short Drama Episode 1',
    mode: 'adaptation',
    summary: 'Adapts the arrival and market investigation into a fast-paced short drama pilot.',
    sourceSceneIds: ['scene_arrival', 'scene_market'],
    sourceChapterIds: ['chap_1'],
    linkedCharacterIds: ['char_aria', 'char_rowan', 'char_nila'],
    linkedWorldItemIds: ['loc_sky_dock', 'loc_flood_market', 'item_city_map'],
    status: 'review',
    reviewState: 'pending',
    version: 1,
    draftPath: 'entities/scripts/script_episode_1.fountain',
    content: `INT. SKY DOCK - DAWN

Aria steps out of the lift into cold copper haze.

ARIA
The theft route starts here. You still know the undercity?

ROWAN
I know where official maps start lying.

INT. FLOOD MARKET - DAY

Nila spreads a layered city map across a tea crate.`,
    episodes: [
      { id: 'script_ep1', title: 'Episode 1', summary: 'Arrival, uneasy alliance, first route anomaly.', sceneIds: ['scene_arrival', 'scene_market'] },
    ],
    createdAt: now(),
    updatedAt: now(),
  },
];

const createStarterStoryboards = (): StoryboardPlan[] => [
  {
    id: 'storyboard_ep1',
    scriptId: 'script_episode_1',
    episodeId: 'script_ep1',
    title: 'Episode 1 Vertical Drama Storyboard',
    shots: [
      {
        id: 'shot_1',
        title: 'Dock Reveal',
        summary: 'Wide shot establishing Sky Dock and Aria arrival.',
        visualPrompt: 'Cinematic industrial fantasy sky dock at dawn, cold copper haze, lone investigator stepping from lift, vertical frame.',
        linkedCharacterIds: ['char_aria'],
        linkedWorldItemIds: ['loc_sky_dock'],
        durationSeconds: 4,
      },
      {
        id: 'shot_2',
        title: 'Map Tension',
        summary: 'Close-up on city map as Rowan points to impossible route.',
        visualPrompt: 'Close-up layered city map over tea crate, gloved hand tracing hidden route, neon market reflections.',
        dialogueCue: 'I know where official maps start lying.',
        linkedCharacterIds: ['char_rowan', 'char_nila'],
        linkedWorldItemIds: ['loc_flood_market', 'item_city_map'],
        durationSeconds: 5,
      },
    ],
    visualStyleNotes: 'Vertical short-drama framing, industrial fantasy, blue-amber palette, moody practical lighting.',
    assetRefs: ['script_episode_1'],
    promptPackagePath: 'exports/video/video_pkg_ep1.json',
    status: 'review',
    createdAt: now(),
    updatedAt: now(),
  },
];

const createStarterVideoPackages = (): VideoGenerationPackage[] => [
  {
    id: 'video_pkg_ep1',
    storyboardId: 'storyboard_ep1',
    provider: 'placeholder-runway',
    status: 'not_configured',
    promptPackagePath: 'exports/video/video_pkg_ep1.json',
    providerPayloadPath: 'exports/video/video_pkg_ep1.provider.json',
    providerResponsePath: 'exports/video/video_pkg_ep1.response.json',
    renderManifestPath: 'exports/video/video_pkg_ep1.render.json',
    createdAt: now(),
    updatedAt: now(),
  },
];

const createStarterRagDocuments = (): RagDocument[] => [
  {
    id: 'rag_doc_scene_arrival',
    sourceType: 'scene',
    sourceId: 'scene_arrival',
    title: 'Dockside Arrival',
    path: 'writing/scenes/scene_arrival.md',
    entityRefs: [
      { type: 'scene', id: 'scene_arrival' },
      { type: 'character', id: 'char_aria' },
      { type: 'character', id: 'char_rowan' },
    ],
    chunkIds: ['rag_chunk_scene_arrival_1'],
    updatedAt: now(),
  },
  {
    id: 'rag_doc_script_ep1',
    sourceType: 'script',
    sourceId: 'script_episode_1',
    title: 'Short Drama Episode 1',
    path: 'entities/scripts/script_episode_1.fountain',
    entityRefs: [{ type: 'script', id: 'script_episode_1' }],
    chunkIds: ['rag_chunk_script_ep1_1'],
    updatedAt: now(),
  },
  {
    id: 'rag_doc_import_seed',
    sourceType: 'import_source',
    sourceId: 'import_seed_project',
    title: 'Starter manuscript import source',
    path: 'system/imports/staging/import_seed_project/source.md',
    entityRefs: [{ type: 'import_job', id: 'import_seed_project' }],
    chunkIds: ['rag_chunk_import_seed_1'],
    updatedAt: now(),
  },
];

const createStarterRagChunks = (): RagChunk[] => [
  {
    id: 'rag_chunk_scene_arrival_1',
    documentId: 'rag_doc_scene_arrival',
    text: 'Aria stepped off the lift into the Sky Dock haze, where the city smelled like cold copper and stormwater.',
    tokenCount: 18,
    keywords: ['aria', 'sky', 'dock', 'lift', 'city'],
    entityRefs: [{ type: 'scene', id: 'scene_arrival' }],
    sourcePath: 'writing/scenes/scene_arrival.md',
  },
  {
    id: 'rag_chunk_script_ep1_1',
    documentId: 'rag_doc_script_ep1',
    text: 'INT. SKY DOCK - DAWN. Aria steps out of the lift into cold copper haze.',
    tokenCount: 14,
    keywords: ['script', 'sky', 'dock', 'aria', 'dawn'],
    entityRefs: [{ type: 'script', id: 'script_episode_1' }],
    sourcePath: 'entities/scripts/script_episode_1.fountain',
  },
  {
    id: 'rag_chunk_import_seed_1',
    documentId: 'rag_doc_import_seed',
    text: '# Fractured Arrival ## Dockside Arrival Aria arrives at Asterfall and recruits Rowan.',
    tokenCount: 15,
    keywords: ['fractured', 'arrival', 'dockside', 'rowan', 'asterfall'],
    entityRefs: [{ type: 'import_job', id: 'import_seed_project' }],
    sourcePath: 'system/imports/staging/import_seed_project/source.md',
  },
];

const createStarterProposals = (): Proposal[] => [
  {
    id: 'proposal_graph_public_fallout',
    title: 'Convert public fallout note into timeline candidate',
    source: 'graph',
    kind: 'entity_update',
    description: 'Graph selection suggests a new event after the bridge intercept.',
    targetEntityType: 'timeline_event',
    targetEntityId: null,
    targetEntityRefs: [{ type: 'timeline_event', id: 'event_bridge' }],
    preview: 'Create event: Public Hearing After Bridge Collapse on branch Public Pressure.',
    proposedOperations: [
      {
        op: 'create',
        entityType: 'timeline_event',
        fields: {
          title: 'Public Hearing After Bridge Collapse',
          branchId: 'branch_public',
        },
      },
    ],
    reviewNotes: 'Derived from graph free-note and existing public pressure branch.',
    confidence: 0.84,
    payloadPath: 'system/runs/artifacts/proposal_graph_public_fallout.json',
    originTaskRunId: 'run_graph_sync_seed',
    reviewPolicy: 'manual_workbench',
    status: 'pending',
    createdAt: now(),
  },
  {
    id: 'proposal_consistency_fix_bridge',
    title: 'Resolve bridge location mismatch',
    source: 'consistency',
    kind: 'qa_fix',
    description: 'One note refers to South Bridge while every linked scene uses Glass Bridge.',
    targetEntityType: 'world_item',
    targetEntityId: 'loc_glass_bridge',
    targetEntityRefs: [{ type: 'world_item', id: 'loc_glass_bridge' }],
    preview: 'Update the inconsistent location reference to Glass Bridge.',
    proposedOperations: [
      {
        op: 'update',
        entityType: 'world_item',
        entityId: 'loc_glass_bridge',
        fields: { description: 'Glass Bridge remains the canonical location reference.' },
      },
    ],
    reviewNotes: 'Safe rename alignment across references.',
    confidence: 0.91,
    payloadPath: 'system/runs/artifacts/proposal_consistency_fix_bridge.json',
    originTaskRunId: 'run_graph_sync_seed',
    reviewPolicy: 'manual_workbench',
    status: 'pending',
    createdAt: now(),
  },
  {
    id: 'proposal_import_entities_seed',
    title: 'Review imported metadata candidates',
    source: 'import',
    kind: 'import_review',
    description: 'Imported manuscript suggests new entity candidates and link proposals.',
    targetEntityType: 'proposal',
    targetEntityId: null,
    targetEntityRefs: [{ type: 'import_job', id: 'import_seed_project' }],
    preview: 'Create import review batch for character, location, and organization candidates extracted from source manuscript.',
    proposedOperations: [
      {
        op: 'create',
        entityType: 'proposal',
        fields: { source: 'import', relatedImportJobId: 'import_seed_project' },
      },
    ],
    reviewNotes: 'Metadata extraction stayed in staging and has not modified canonical entities.',
    confidence: 0.72,
    payloadPath: 'system/imports/staging/import_seed_project/proposals.json',
    originTaskRunId: 'run_import_seed',
    reviewPolicy: 'manual_workbench',
    status: 'pending',
    createdAt: now(),
  },
];

const createStarterHistory = (): Proposal[] => [
  {
    id: 'proposal_hist_candidate',
    title: 'Promote courier witness into candidate profile',
    source: 'agent',
    kind: 'entity_update',
    description: 'Resolved earlier narrative import.',
    targetEntityType: 'candidate',
    targetEntityId: 'cand_mina',
    preview: 'Created candidate Mina Vale from scene witness notes.',
    reviewPolicy: 'manual_workbench',
    status: 'accepted',
    createdAt: now(),
    resolvedAt: now(),
  },
];

const createStarterIssues = (): ConsistencyIssue[] => [
  {
    id: 'issue_bridge_name',
    title: 'Bridge location mismatch',
    description: 'One note still references South Bridge while the canonical location is Glass Bridge.',
    severity: 'high',
    status: 'open',
    source: 'consistency',
    referenceIds: [
      { type: 'timeline_event', id: 'event_bridge' },
      { type: 'scene', id: 'scene_bridge' },
      { type: 'world_item', id: 'loc_glass_bridge' },
    ],
    originTaskRunId: 'run_graph_sync_seed',
    suggestedProposalIds: ['proposal_consistency_fix_bridge'],
    fixSuggestion: 'Create a Workbench fix proposal that rewrites the stale location reference to Glass Bridge.',
    visibility: 'default',
  },
  {
    id: 'issue_duplicate_market',
    title: 'Possible duplicate market route intel',
    description: 'A graph note and a lore note appear to describe the same hidden route network.',
    severity: 'medium',
    status: 'open',
    source: 'qa',
    referenceIds: [
      { type: 'world_item', id: 'note_open_questions' },
      { type: 'graph_node', id: 'graph_note_public' },
    ],
    fixSuggestion: 'Merge the duplicated route phrasing through Workbench before chapter three drafting.',
    visibility: 'default',
  },
  {
    id: 'issue_state_flag',
    title: 'Character state flag review',
    description: 'Vesper appears in one draft outline as deceased while all current scenes still use him as active.',
    severity: 'low',
    status: 'open',
    source: 'qa',
    referenceIds: [
      { type: 'character', id: 'char_vesper' },
      { type: 'scene', id: 'scene_bridge' },
    ],
    fixSuggestion: 'Keep Vesper alive for the current draft and move the death note to future branching notes.',
    visibility: 'default',
  },
];

const createStarterExports = (): ExportArtifact[] => [];

const createStarterCandidates = (): Candidate[] => [
  {
    id: 'cand_mina',
    name: 'Mina Vale',
    background: 'Courier witness tied to Rowan\'s old route network.',
    summary: 'Potential side-character who can anchor chapter three fallout.',
  },
];

const buildProject = (
  name: string,
  rootPath: string,
  locale: Locale,
  storageMode: NarrativeProject['metadata']['storageMode'],
  template: ProjectTemplate,
  body: Omit<NarrativeProject, 'metadata'>
): NarrativeProject => ({
  metadata: {
    schemaVersion: PROJECT_SCHEMA_VERSION,
    projectId: `project_${template}_${name.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
    name,
    description: template === 'starter-demo' ? 'A guided starter project for the acceptance walkthrough.' : 'A blank narrative project.',
    createdAt: now(),
    updatedAt: now(),
    version: 4,
    rootPath,
    storageMode,
    locale,
    template,
    capabilities: {
      import: true,
      rag: true,
      scripts: true,
      videoWorkflow: true,
      promptTemplates: true,
    },
    storageBackends: {
      canonical: 'project-folder-json',
      rag: 'project-folder-keyword-index',
    },
    futureBackends: ['sqlite', 'embedding-provider', 'video-provider'],
    lastOpenedModule: 'workbench',
    lastOpenedSceneId: body.scenes[0]?.id || null,
    lastOpenedBoardId: body.graphBoards[0]?.id || null,
  },
  ...body,
});

export const createStarterProject = (
  name = 'Starter Demo Project',
  rootPath = 'memory://starter-demo-project',
  locale: Locale = 'en',
  storageMode: NarrativeProject['metadata']['storageMode'] = 'memory'
): NarrativeProject =>
  buildProject(name, rootPath, locale, storageMode, 'starter-demo', {
    characters: createStarterCharacters(),
    characterTags: createStarterTags(),
    candidates: createStarterCandidates(),
    timelineBranches: createStarterBranches(),
    timelineEvents: createStarterEvents(),
    relationships: createStarterRelationships(),
    chapters: createStarterChapters(),
    scenes: createStarterScenes(),
    worldContainers: createWorldContainers(),
    worldItems: createWorldItems(),
    worldSettings: createWorldSettings(),
    worldMaps: createWorldMaps(),
    graphBoards: createStarterBoards(),
    betaPersonas: createStarterBetaPersonas(),
    betaRuns: createStarterBetaRuns(),
    simulationEngines: createSimulationEngines(),
    simulationLabs: createSimulationLabs(),
    simulationReviewers: createSimulationReviewers(),
    simulationRuns: createSimulationRuns(),
    taskRequests: createStarterTaskRequests(),
    taskRuns: createStarterTaskRuns(),
    taskArtifacts: createStarterTaskArtifacts(),
    taskRunLogs: createStarterTaskRunLogs(),
    importJobs: createStarterImportJobs(),
    promptTemplates: createStarterPromptTemplates(),
    ragDocuments: createStarterRagDocuments(),
    ragChunks: createStarterRagChunks(),
    ragManifest: {
      activeBackend: 'keyword',
      futureBackends: ['embedding'],
      storageBackend: 'project-folder-keyword-index',
    },
    retrievalHistory: [
      {
        requestId: 'retrieval_seed_1',
        backend: 'keyword',
        items: [
          {
            chunkId: 'rag_chunk_scene_arrival_1',
            documentId: 'rag_doc_scene_arrival',
            excerpt: 'Aria stepped off the lift into the Sky Dock haze...',
            score: 0.88,
            entityRefs: [{ type: 'scene', id: 'scene_arrival' }],
            sourcePath: 'writing/scenes/scene_arrival.md',
          },
        ],
      },
    ],
    scripts: createStarterScripts(),
    storyboards: createStarterStoryboards(),
    videoPackages: createStarterVideoPackages(),
    proposals: createStarterProposals(),
    proposalHistory: createStarterHistory(),
    issues: createStarterIssues(),
    exports: createStarterExports(),
    unreadUpdates: {
      activities: { workbench: true, graph: true, consistency: true, 'beta-reader': true },
      sections: { 'workbench.inbox': true, 'graph.narrative': true, 'consistency.issues': true },
      entities: { proposal_graph_public_fallout: true, issue_bridge_name: true },
    },
    archivedIds: [],
    metadataFiles: [],
    todos: [],
    uiState: createDefaultUiState(),
  });

export const createBlankProject = (
  name = 'Blank Narrative Project',
  rootPath = 'memory://blank-project',
  locale: Locale = 'en',
  storageMode: NarrativeProject['metadata']['storageMode'] = 'memory'
): NarrativeProject =>
  buildProject(name, rootPath, locale, storageMode, 'blank', {
    characters: [],
    characterTags: [],
    candidates: [],
    timelineBranches: [{ id: 'branch_main', name: 'Main Branch', description: 'Default story branch.', parentBranchId: null, forkEventId: null, mergeEventId: null, color: '#f59e0b', sortOrder: 0, collapsed: false }],
    timelineEvents: [],
    relationships: [],
    chapters: [
      {
        id: 'chap_1',
        title: 'Chapter 1',
        summary: 'Starting chapter.',
        goal: 'Draft the first scenes.',
        notes: 'Use this chapter as your entry point.',
        sceneIds: ['scene_1'],
        orderIndex: 0,
        status: 'draft',
      },
    ],
    scenes: [
      {
        id: 'scene_1',
        chapterId: 'chap_1',
        title: 'Scene 1',
        summary: 'An empty starting scene.',
        content: '',
        orderIndex: 0,
        povCharacterId: null,
        linkedCharacterIds: [],
        linkedEventIds: [],
        linkedWorldItemIds: [],
        status: 'draft',
      },
    ],
    worldContainers: createWorldContainers(),
    worldItems: [
      {
        id: 'map_city',
        containerId: 'cont_world_map',
        type: 'map',
        name: 'World Map',
        description: 'A blank map canvas for your project.',
        attributes: [{ key: 'Status', value: 'Empty' }],
        linkedCharacterIds: [],
        linkedEventIds: [],
        linkedSceneIds: [],
        mapMarkers: [],
        assetPath: defaultMapAsset,
        tagIds: ['map'],
      },
    ],
    worldSettings: {
      projectType: 'long-form serial novel',
      narrativePacing: 'to be defined',
      languageStyle: 'to be defined',
      narrativePerspective: 'to be defined',
      lengthStrategy: 'supports long-form expansion',
      worldRulesSummary: '',
    },
    worldMaps: [
      {
        id: 'map_city_primary',
        title: 'World Map',
        description: 'Default blank map for your project.',
        assetPath: defaultMapAsset,
        markerIds: [],
        sortOrder: 0,
      },
    ],
    graphBoards: [
      {
        id: 'board_main',
        name: 'Main Board',
        description: 'A blank mixed-mode board.',
        nodes: [],
        edges: [],
        view: { zoom: 1, panX: 0, panY: 0 },
        selectedNodeIds: [],
        sortOrder: 0,
      },
    ],
    betaPersonas: createStarterBetaPersonas(),
    betaRuns: [],
    simulationEngines: [],
    simulationLabs: [],
    simulationReviewers: [],
    simulationRuns: [],
    taskRequests: [],
    taskRuns: [],
    taskArtifacts: [],
    taskRunLogs: [],
    importJobs: [],
    promptTemplates: createStarterPromptTemplates(),
    ragDocuments: [],
    ragChunks: [],
    ragManifest: {
      activeBackend: 'keyword',
      futureBackends: ['embedding'],
      storageBackend: 'project-folder-keyword-index',
    },
    retrievalHistory: [],
    scripts: [],
    storyboards: [],
    videoPackages: [],
    proposals: [],
    proposalHistory: [],
    issues: [],
    exports: [],
    unreadUpdates: { activities: {}, sections: {}, entities: {} },
    archivedIds: [],
    metadataFiles: [],
    todos: [],
    uiState: createDefaultUiState(),
  });
