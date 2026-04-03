# LangGraph Architecture — Narrative IDE

> **This document is the single source of truth for the AI layer of Narrative IDE.**  
> It covers: storage architecture, tools, skills, shared infrastructure, all workflows (W0–W7), the Orchestrator interface, and implementation conventions.  
> When giving Claude Code a prompt, always reference this file first.

---

## 0. Guiding Principles

1. **The harness does not think. The model thinks.** LangGraph provides tools, context, and boundaries. Claude does the reasoning.
2. **No RAG for project data.** Structured JSON files are read directly. RAG is only used for unstructured Metadata references.
3. **Serial by default.** Workflow steps run serially unless explicitly marked parallel. Concurrency is a source of bugs, not speed, at this scale.
4. **Memory Writer is the only write path.** No workflow node writes to project files directly. All writes go through S2.
5. **Every workflow is headless-first.** No dependency on Electron. Workflows accept a `project_path` and run identically from UI or CLI.

---

## 1. Storage Architecture (Three Layers)

### Layer 1 — Structured Project Files (Direct JSON Read)

```
project-root/
  project.json           ← project metadata + entity registry index
  project.db             ← SQLite (World Model + complex entities)
  workflow.lock          ← mutex file (one workflow at a time)
  manuscript.json        ← chapter/scene ordering
  todos.json             ← Todo + Proposal Queue items
  metadata/
    index.json           ← MetadataFile records (id, title, status)
    {fileId}/
      chunks.json        ← chunked text
      original.{ext}     ← source file copy
  characters/
    {id}.json
  scenes/
    {id}.meta.json
    {id}.md
  timeline/
    branches.json
    events/
      {id}.json
```

**Read strategy:** ProjectContext Builder loads only what the current task needs.  
For index-style reads: load only `id + name + summary` fields first.  
Dive into full content only after anchoring on a specific entity ID.

### Layer 2 — World Model / Complex Entities (SQLite via `better-sqlite3`)

```sql
-- Titles-first query pattern (always)
SELECT id, title, category, summary FROM world_entries;

-- Dive into specific entry only when anchored
SELECT * FROM world_entries WHERE id = ?;
```

**Location:** `project-root/project.db`  
**Electron access:** `better-sqlite3` (synchronous, safe in IPC handlers)  
**Python access:** `aiosqlite` in sidecar

### Layer 3 — Metadata Reference Files (RAG / Vector Search)

Used **only** for unstructured reference files (novels, scripts, articles).  
Never used for project data reads.

```
Vector store: chromadb (local, embedded, no server)
Collection per project: narrative_{project_id}_metadata
Embedding model: text-embedding-3-small (OpenAI) or claude embed

Query pattern:
  1. semantic_search(query, top_k=5)       ← retrieve relevant chunks
  2. inject all 5 chunks into context      ← no further filtering
```

---

## 2. Entity Registry

The Entity Registry is the global disambiguation table built during Import and maintained across all workflows. It lives in `project.json` under the `entityRegistry` key and is mirrored into SQLite for fast lookup.

```typescript
interface EntityRegistry {
  characters: Record<string, CharacterEntry>;
  events: Record<string, EventEntry>;
  worldEntries: Record<string, WorldEntryRef>;
}

interface CharacterEntry {
  canonicalId: string;
  canonicalName: string;
  aliases: string[];          // all known names, nicknames, titles
  firstSeenChunk: number;
  notes: string[];            // appended per-chunk, never overwritten
  confidence: number;         // 0–1, entity recognition confidence
}
```

**Resolution rule:** Before registering a new character, check all existing `aliases` for fuzzy match. If match found → append alias + note, do not create new entry. If no match → create new entry with `confidence: 0.7`, flag for user review if below `0.6`.

---

## 3. Workflow Lock (Mutex)

**File:** `project-root/workflow.lock`

```json
{
  "workflowId": "import",
  "startedAt": "2026-04-01T12:00:00Z",
  "pid": 12345
}
```

**Acquire logic (Python sidecar):**
1. Check if `workflow.lock` exists
2. If exists → read PID → check if process alive
   - Alive: return `WORKFLOW_BUSY` error with current `workflowId`
   - Dead (stale lock): delete lock, proceed
3. Write lock → execute workflow → delete lock on completion or error

**IPC handlers (Electron):**
- `workflow:status` → returns current lock state (polled every 2s by UI)
- `workflow:force-clear` → manual stale lock removal (shown in UI on error state)

**UI states:**
- `idle` → all workflow trigger buttons enabled
- `running` → progress bar + workflow name shown; other buttons disabled with tooltip
- `error` → error message + "Clear Lock" button

---

## 4. Proposal Queue & Dependency Graph

All AI-generated writes are staged as Proposals before touching project files.

```typescript
interface Proposal {
  id: string;
  type: "create" | "update" | "delete";
  entityType: "character" | "event" | "worldEntry" | "scene" | "todo" | "manuscript";
  entityId: string;            // provisional IDs use prefix: "provisional_char_003"
  data: Record<string, unknown>;
  dependsOn: string[];         // proposal IDs this one depends on
  conflictsWith: string[];     // proposal IDs that modify same field
  confidence: number;
  source: string;              // which workflow generated this
  status: "pending" | "accepted" | "rejected" | "blocked";
}
```

**Cascade on rejection:**
1. User rejects proposal P
2. Find all proposals where `dependsOn.includes(P.id)`
3. Mark them `blocked`, surface in UI as "Dependency rejected"
4. User can explicitly unblock by overriding

**UI (Workbench Inbox):**
- Each proposal card shows: "Depended on by N items" / "Depends on M items"
- Click → expand dependency chain (tree view)
- Batch accept/reject with cascade warning dialog

---

## 5. Tools

Tools are functions available to LangGraph nodes. All tools are pure functions: input → output, no side effects except through Memory Writer.

### 5.1 File I/O Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `project_reader` | `(project_path, entity_type, entity_id?)` → `dict` | Read any project entity JSON. If `entity_id` is None, returns index only (id+name+summary). |
| `manuscript_reader` | `(project_path, chapter_id?)` → `dict` | Read manuscript.json or specific chapter content. |
| `chunk_reader` | `(project_path, file_id, chunk_index?)` → `str` | Read metadata chunks. |
| `sqlite_query` | `(project_path, sql, params)` → `List[dict]` | Execute read-only SQLite query. Always titles-first. |

### 5.2 Text Processing Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `text_chunker` | `(text, config: ChunkConfig)` → `List[Chunk]` | Split text by strategy. See S3 Chunk Manager. |
| `entity_extractor` | `(chunk_text, registry: EntityRegistry)` → `ExtractionResult` | Extract characters + events from chunk, resolve against registry. Characters extracted first, events second. |
| `text_summarizer` | `(text, max_tokens: int)` → `str` | Generate short summary for context injection. |
| `alias_resolver` | `(name: str, registry: EntityRegistry)` → `str | None` | Fuzzy match name against all known aliases. Returns canonical_id or None. |

### 5.3 Analysis Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `timeline_analyzer` | `(events: List[Event])` → `List[TimelineIssue]` | Check temporal ordering and causal logic. |
| `character_tracker` | `(character_id, scenes: List[Scene])` → `List[ConsistencyIssue]` | Track attribute consistency across scenes. |
| `conflict_detector` | `(proposals: List[Proposal])` → `List[ConflictPair]` | Detect proposals modifying same fields. |
| `rag_search` | `(project_id, query, top_k=5)` → `List[MetadataChunk]` | Semantic search over Metadata vector store. |

### 5.4 Write Tools (All route through Memory Writer)

| Tool | Signature | Description |
|------|-----------|-------------|
| `propose_write` | `(operation: WriteOperation)` → `Proposal` | Stage a write as Proposal. Confidence gates auto-apply vs Inbox routing. |
| `enqueue_todo` | `(todo: TodoItem)` → `str` | Create a Todo item in todos.json. |
| `update_registry` | `(entry: CharacterEntry | EventEntry)` → `None` | Append alias/note to Entity Registry. Never overwrites. |

---

## 6. Skills (CLAUDE.md conventions for Claude Code)

Skills are conventions written into `CLAUDE.md` at project root. Claude Code reads this before every session.

### skill: project-schema
```
The project schema is defined in src/ui-react/models/project.ts (869 lines).
Key entities: Character, Scene, Chapter, TimelineEvent, WorldEntry, GraphBoard, Manuscript, MetadataFile, TodoItem, Proposal.
Entity Registry lives in project.json under entityRegistry.
World Model complex entries live in project.db (SQLite).
Always read models/project.ts before touching any data model code.
```

### skill: chunk-strategy
```
ChunkConfig strategies:
  "chapter"   → split at chapter boundaries (preferred for Import)
  "paragraph" → split at paragraph boundaries, soft size limit
  "fixed"     → hard character limit (use for Metadata ingestion only)

Default chunk_size: 500_000 chars
Default overlap: 50_000 chars (10%)
Every chunk carries: chunk_id, char_start, char_end, chapter_hint, entity_mentions[]
Overlap exists to catch entities mentioned near chunk boundaries.
```

### skill: memory-writer-rules
```
Confidence thresholds for Memory Writer (S2):
  >= 0.85 AND auto_apply=True  → write directly, Inbox shows as "Applied"
  0.60 – 0.85                  → stage as Proposal, route to Inbox
  < 0.60                       → stage as Proposal, flagged "Needs Review"

No workflow node writes project files directly.
All writes must call propose_write() tool.
Entity Registry updates use update_registry() — append only, never overwrite.
```

### skill: workflow-conventions
```
Every workflow State must include:
  project_path: str
  workflow_id: str
  progress: float          (0.0–1.0, for UI progress bar)
  errors: List[str]        (non-fatal errors, surfaced to UI)
  proposals: List[Proposal] (staged writes)

Every workflow entry point accepts:
  project_path: str
  config: dict             (includes hitl_mode, scope, target_id etc.)

Workflows must be runnable without Electron (headless-first).
```

### skill: file-io-patterns
```
Project root path is always passed in from Electron via IPC or CLI arg.
Never hardcode paths.
File read pattern: aiofiles.open(path, 'r', encoding='utf-8')
SQLite pattern: aiosqlite.connect(project_path / 'project.db')
Lock file: project_path / 'workflow.lock'
Metadata vector store: chromadb client pointing to project_path / '.chroma'
```

---

## 7. Shared Infrastructure Nodes

### S1 — ProjectContext Builder

Builds a precisely scoped context object for any workflow. Never loads more than the task needs.

```python
class ProjectContext(TypedDict):
    characters: List[CharacterSummary]      # always summary-only unless anchored
    scenes: List[SceneSummary]
    timeline_events: List[EventSummary]
    world_entries: List[WorldEntrySummary]  # titles-first from SQLite
    active_todos: List[TodoItem]
    entity_registry: EntityRegistry
    # full detail fields, populated only when anchored:
    anchored_character: Optional[CharacterFull]
    anchored_scene: Optional[SceneFull]
    anchored_world_entry: Optional[WorldEntryFull]

# Context profiles per workflow type:
CONTEXT_PROFILES = {
    "writing":      ["pov_character_full", "scene_summaries_same_chapter",
                     "related_timeline_events", "active_todos_top5"],
    "consistency":  ["all_character_summaries", "timeline_skeleton",
                     "world_entry_titles"],
    "simulation":   ["full_character_motivations", "full_timeline",
                     "world_rules"],
    "import":       [],   # write-only mode, no project read needed
    "beta_reader":  ["chapter_content", "persona_profile"],
}
```

### S2 — Memory Writer

The sole write path. All workflow nodes call `propose_write()` which routes here.

```python
class WriteOperation(TypedDict):
    op_type: Literal["create", "update", "delete"]
    entity_type: str
    entity_id: Optional[str]
    data: dict
    source_workflow: str
    confidence: float
    auto_apply: bool
    depends_on: List[str]       # provisional proposal IDs

def memory_writer(op: WriteOperation) -> Proposal:
    if op.confidence >= 0.85 and op.auto_apply:
        apply_to_file(op)
        return Proposal(status="applied", ...)
    else:
        proposal = stage_proposal(op)
        push_to_inbox(proposal)
        return proposal
```

### S3 — Chunk Manager

```python
class ChunkConfig(TypedDict):
    strategy: Literal["chapter", "paragraph", "fixed"]
    chunk_size: int         # default 500_000
    overlap: int            # default 50_000
    
class Chunk(TypedDict):
    chunk_id: int
    char_start: int
    char_end: int
    content: str
    chapter_hint: Optional[str]
    entity_mentions: List[str]   # populated after extraction pass

# Pipeline: text → chunks → serial extraction → entity registry updates
# Each chunk extraction receives the current EntityRegistry state
# and returns an updated registry + new proposals
```

### S4 — Proposal Queue

Thin wrapper around `todos.json` for the Proposal routing logic.

```python
def push_to_inbox(proposal: Proposal) -> None:
    todos = read_todos_json()
    todos["proposals"].append(proposal)
    write_todos_json(todos)

def apply_proposal(proposal_id: str) -> None:
    proposal = get_proposal(proposal_id)
    check_dependencies_accepted(proposal)   # raise if blocked
    apply_to_file(proposal)
    cascade_unblock(proposal_id)            # unblock anything waiting on this

def reject_proposal(proposal_id: str) -> None:
    cascade_block(proposal_id)              # block all dependents
    mark_rejected(proposal_id)
```

---

## 8. Workflows

### W0 — Orchestrator (Autonomous CLI Agent)

The top-level workflow. Accepts a high-level goal and recursively plans and executes W1–W7.

**Interface:**

```python
class OrchestratorState(TypedDict):
    project_path: str
    goal: str                           # natural language goal from user
    plan: List[OrchestratorStep]        # generated plan
    current_step: int
    step_results: List[StepResult]
    pending_permission: Optional[PermissionRequest]
    status: Literal["planning", "executing", "waiting_permission", "done", "error"]
    progress: float
    errors: List[str]
    proposals: List[Proposal]

class OrchestratorStep(TypedDict):
    step_id: str
    workflow: str                       # "W1"–"W7"
    config: dict                        # passed to sub-workflow
    rationale: str                      # why this step is needed
    requires_permission: bool

class PermissionRequest(TypedDict):
    step_id: str
    description: str                    # human-readable: "About to rewrite Chapter 3"
    risk_level: Literal["low", "medium", "high"]
    affected_entities: List[str]
```

**Graph:**

```
parse_goal
    ↓
plan_workflow_sequence        ← decides which W1–W7 to call and in what order
    ↓
[LOOP]:
  check_permission_needed
      ↓ (if needed)
  request_permission          ← interrupt: push PermissionRequest to Inbox, wait
      ↓ (accepted)
  execute_step                ← invoke sub-workflow via HTTP to sidecar
      ↓
  evaluate_result             ← did it succeed? does plan need revision?
      ↓
  [revise_plan OR next_step OR done]
```

**CLI invocation (future):**

```bash
narrative-cli orchestrate \
  --project ./my-novel \
  --goal "完成第三卷，每章至少一个转折点，参考metadata里的金庸风格" \
  --auto-apply-threshold 0.85
```

**Permission gate triggers:**
- Any `delete` operation
- Writing more than 10 new entities in one step
- Overwriting existing scene content
- First time a new workflow type is invoked in the session

---

### W1 — Import Workflow

Bootstraps a blank project from an existing novel file. Most complex workflow.

```python
class ImportState(TypedDict):
    project_path: str
    source_file_path: str
    chunks: List[Chunk]
    entity_registry: EntityRegistry     # grows with each chunk
    chunk_results: List[ChunkExtraction]
    manuscript_chapters: List[ManuscriptChapter]
    proposals: List[Proposal]
    progress: float
    errors: List[str]

class ChunkExtraction(TypedDict):
    chunk_id: int
    new_characters: List[CharacterEntry]
    updated_aliases: List[AliasUpdate]
    events: List[EventEntry]            # references canonical character IDs
    world_mentions: List[str]
    manuscript_content: str             # raw text for this chunk
    notes: List[str]                    # extractor notes for review
```

**Graph (fully serial):**

```
validate_file
    ↓
split_chunks (S3)
    ↓
[FOR EACH CHUNK — serial]:
    extract_characters          ← updates EntityRegistry
        ↓
    extract_events              ← references canonical IDs from updated registry
        ↓
    extract_world_mentions
        ↓
    update_entity_registry      ← append aliases/notes, never overwrite
        ↓
    buffer_manuscript_content
    ↓
resolve_conflicts               ← entities with confidence < 0.6 flagged
    ↓
build_manuscript                ← assemble ManuscriptChapters from buffered content
    ↓
generate_todos                  ← flag unresolved entities, open plot threads
    ↓
write_to_project (S2)          ← all proposals at once, dependency-ordered
```

**Failure handling:** On any chunk failure, log to `errors[]`, skip chunk, continue. Surface all errors to UI at end. User can re-run failed chunks individually.

**Resume support:** Each chunk result is checkpointed to `import_progress.json` at project root. Re-running import skips already-completed chunks.

---

### W2 — Manuscript Sync

Three trigger modes, same graph with mode config.

```python
class ManuscriptSyncState(TypedDict):
    project_path: str
    mode: Literal["single_chapter", "post_import", "draft_only"]
    target_chapter_id: Optional[str]
    extracted_entities: List[Entity]
    diff: List[DiffItem]
    proposals: List[Proposal]
    progress: float
    errors: List[str]
```

**Graph:**

```
[mode == "post_import"]:  skip to write_manuscript (Import already built it)
[mode == "draft_only"]:   skip to done (no sync, just store)
[mode == "single_chapter"]:
    load_chapter_content
        ↓
    extract_entities_from_chapter
        ↓
    diff_with_project_data
        ↓
    generate_proposals (S2)
        ↓
    push_to_inbox (S4)
```

**Annotation markers (for UI rich text):**
```typescript
type AnnotationType = "character" | "location" | "item" | "todo" | "conflict";
// Stored as TipTap marks on manuscript content
// Clicking a mark navigates to corresponding entity in sidebar
```

---

### W3 — Writing Assistant

Highest frequency workflow. Two modes controlled by `hitl_mode` config.

```python
class WritingState(TypedDict):
    project_path: str
    scene_id: str
    task: Literal["continue", "rewrite", "expand", "improve_dialogue", "summarize"]
    context: ProjectContext              # built by S1, writing profile
    active_todos: List[TodoItem]
    metadata_style: Optional[str]       # metadata file_id, if user selected one
    metadata_chunks: List[str]          # top-5 RAG results from metadata
    hitl_mode: Literal["three_options", "direct_output"]
    # three_options mode:
    options: List[str]
    selected_option: Optional[int]
    # both modes:
    output: str
    new_entities: List[Entity]          # entities created during writing
    proposals: List[Proposal]
    progress: float
    errors: List[str]
```

**Graph:**

```
build_context (S1, writing profile)
    ↓
load_active_todos
    ↓
load_metadata_style         ← if metadata_file_id set: rag_search() top-5 chunks
    ↓
generate_content            ← produces options[] (3) or output directly
    ↓
[hitl_mode == "three_options"]:
    INTERRUPT: wait_for_selection
        ↓ (user selects)
    expand_selected
[hitl_mode == "direct_output"]:
    output already in state
    ↓
lightweight_consistency_check   ← character_tracker on current scene only
    ↓
extract_new_entities
    ↓
push_proposals (S2 + S4)
```

---

### W4 — Consistency Check

```python
class ConsistencyState(TypedDict):
    project_path: str
    scope: Literal["scene", "chapter", "full"]
    target_id: str
    context: ProjectContext
    issues: List[ConsistencyIssue]
    severity_counts: Dict[str, int]     # HIGH / MED / LOW
    proposals: List[Proposal]           # suggested fixes
    progress: float
    errors: List[str]

class ConsistencyIssue(TypedDict):
    issue_id: str
    type: Literal["timeline", "character", "world_rule", "item_tracking"]
    severity: Literal["HIGH", "MED", "LOW"]
    description: str
    scene_id: str
    entity_ids: List[str]
    suggested_fix: Optional[str]
```

**Graph:**

```
build_context (S1, consistency profile)
    ↓
[scope determines context depth]
    ↓
[SERIAL — 4 checkers]:
    timeline_checker
        ↓
    character_checker
        ↓
    world_rule_checker
        ↓
    item_tracker
    ↓
merge_issues
    ↓
rank_severity
    ↓
push_to_consistency_ui      ← direct UI update, no Inbox (read-only analysis)
generate_fix_proposals      ← optional: create Proposals for suggested fixes
```

**Silent mode** (background, during Writing Assistant):
- Only `character_checker` + `item_tracker`
- Scope: current scene only
- Output: TipTap inline annotations, not Inbox

---

### W5 — Simulation Engine

```python
class SimulationState(TypedDict):
    project_path: str
    scenario_variable: str              # "主角第三章没拿到解药"
    affected_chapter_ids: List[str]
    engines_selected: List[EngineType]
    context: ProjectContext
    engine_results: Dict[str, EngineOutput]
    report: SimulationReport
    progress: float
    errors: List[str]

EngineType = Literal["scenario", "character", "author", "reader", "logic"]
```

**Graph:**

```
setup_scenario
    ↓
load_affected_context (S1, simulation profile)
    ↓
chunk_affected_chapters (S3)    ← affected chapters may be large
    ↓
[SERIAL — selected engines only]:
    scenario_engine     → 3 branching plot predictions
        ↓
    character_engine    → decision-making simulation per character
        ↓
    author_engine       → narrative structure suggestions
        ↓
    reader_engine       → reader reaction prediction (uses metadata RAG)
        ↓
    logic_engine        → logical completeness check
    ↓
synthesize_results
    ↓
generate_report         ← markdown report pushed to Simulation UI
```

---

### W6 — Beta Reader

```python
class BetaReaderState(TypedDict):
    project_path: str
    persona: PersonaProfile
    target_chapter_ids: List[str]
    chunks: List[Chunk]
    feedback_items: List[FeedbackItem]
    report: BetaReaderReport
    progress: float
    errors: List[str]

class PersonaProfile(TypedDict):
    persona_id: str
    name: str
    type: Literal["scholar", "shipper", "casual", "custom"]
    traits: List[str]
    focus_areas: List[str]          # ["pacing", "romance", "logic", "world_building"]
    metadata_reference_id: Optional[str]  # optional: ground persona in metadata

class FeedbackItem(TypedDict):
    chapter_id: str
    dimension: Literal["engagement", "pacing", "character", "logic", "world"]
    score: int                      # 1–10
    comment: str
    excerpt_reference: Optional[str]
```

**Graph:**

```
select_persona
    ↓
load_target_chapters
    ↓
chunk_chapters (S3)             ← chapters may exceed context
    ↓
[FOR EACH CHUNK — serial]:
    read_as_persona
        ↓
    generate_chunk_feedback
    ↓
aggregate_feedback
    ↓
generate_structured_report
    ↓
push_to_betareader_ui
```

---

### W7 — Metadata Ingestion

```python
class MetadataIngestionState(TypedDict):
    project_path: str
    source_file_path: str
    file_type: Literal["novel", "script", "news", "essay", "draft", "other"]
    file_id: str
    chunks: List[Chunk]
    style_profile: StyleProfile
    knowledge_profile: KnowledgeProfile
    vector_store_updated: bool
    progress: float
    errors: List[str]

class StyleProfile(TypedDict):
    avg_sentence_length: float
    dialogue_ratio: float
    pov_style: str
    pacing_descriptor: str
    vocabulary_notes: List[str]

class KnowledgeProfile(TypedDict):
    key_facts: List[str]
    named_entities: List[str]
    domain_tags: List[str]
```

**Graph:**

```
detect_file_type
    ↓
copy_to_metadata_folder
    ↓
chunk_source_file (S3, fixed strategy)
    ↓
[SERIAL]:
    extract_style_features
        ↓
    extract_vocabulary
        ↓
    extract_structural_patterns
        ↓
    extract_knowledge_facts
    ↓
build_profiles
    ↓
embed_and_store_chunks          ← chromadb, collection: narrative_{project_id}_metadata
    ↓
update_metadata_index           ← write metadata/index.json entry
```

---

## 9. Python Sidecar Architecture

### Process Management

```
Per-project sidecar process:
  - Spawned by Electron main process when project opens
  - Binds to random available port (saved to ~/.narrative-ide/processes/{project_id}.json)
  - Killed when project window closes
  - All sidecars killed on app exit (Electron will-quit hook)

PID file: ~/.narrative-ide/processes/{project_id}.json
  { "pid": 12345, "port": 54231, "projectPath": "/path/to/project" }

Crash recovery: If sidecar PID not alive on project open → spawn fresh
```

### FastAPI Structure

```
sidecar/
  main.py                  ← FastAPI app + uvicorn entry
  routers/
    workflows.py           ← POST /workflow/{workflow_id}/start
    status.py              ← GET /workflow/status
    proposals.py           ← POST /proposals/{id}/accept|reject
    metadata.py            ← POST /metadata/ingest
  workflows/
    w0_orchestrator.py
    w1_import.py
    w2_manuscript_sync.py
    w3_writing_assistant.py
    w4_consistency_check.py
    w5_simulation.py
    w6_beta_reader.py
    w7_metadata_ingestion.py
  shared/
    s1_context_builder.py
    s2_memory_writer.py
    s3_chunk_manager.py
    s4_proposal_queue.py
  tools/
    file_io.py
    text_processing.py
    analysis.py
    rag.py
  models/
    state.py               ← all TypedDict State schemas
    proposals.py
    registry.py
```

### Key API Endpoints

```
POST   /workflow/{id}/start        body: { project_path, config }
GET    /workflow/status            returns: { workflowId, progress, status }
POST   /workflow/cancel            clears lock, marks cancelled
POST   /proposals/{id}/accept
POST   /proposals/{id}/reject
GET    /proposals/list             returns: pending proposals
POST   /metadata/ingest            body: { project_path, file_path, file_type }
POST   /orchestrator/start         body: { project_path, goal, config }
GET    /orchestrator/status
POST   /orchestrator/permission/{step_id}/grant
POST   /orchestrator/permission/{step_id}/deny
```

### SSE for Progress (Streaming)

```
GET    /workflow/stream            Server-Sent Events stream
  events:
    progress  { workflow_id, progress: 0.0–1.0, message }
    proposal  { proposal }          ← new proposal ready for Inbox
    error     { message }
    done      { workflow_id }
```

Electron IPC handler subscribes to SSE stream and forwards to renderer via `ipcRenderer.send`.

---

## 10. Python Dependencies

```toml
# pyproject.toml (or requirements.txt)
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
langgraph>=0.1.0
langchain-anthropic>=0.1.0
langchain-core>=0.2.0
aiosqlite>=0.20.0
aiofiles>=23.2.0
chromadb>=0.5.0
tiktoken>=0.7.0
pydantic>=2.7.0
watchdog>=4.0.0          # for file change detection (Manuscript Sync trigger)
python-multipart>=0.0.9  # for file upload endpoints
```

---

## 11. Electron / Node.js Dependencies to Add

```json
"better-sqlite3": "^9.0.0",
"chokidar": "^3.6.0"
```

---

## 12. Implementation Order

```
Phase 0 — Sidecar Skeleton
  [ ] FastAPI app + uvicorn bootstrap
  [ ] Electron spawn/kill sidecar logic
  [ ] IPC ↔ HTTP bridge
  [ ] workflow.lock implementation
  [ ] SSE progress stream

Phase 1 — Frontend Features (prerequisite for all AI)
  [ ] Manuscript (frontend + backend)
  [ ] Metadata (frontend + backend)
  [ ] Todo / Proposal Inbox (frontend + backend)
  [ ] Timeline bug fixes

Phase 2 — Shared Infrastructure
  [ ] S3 Chunk Manager
  [ ] S1 ProjectContext Builder
  [ ] S2 Memory Writer + confidence routing
  [ ] S4 Proposal Queue + dependency graph

Phase 3 — First Workflow (Writing Assistant W3)
  [ ] W3 minimal: continue scene, direct_output mode
  [ ] W3 full: three_options mode + metadata style

Phase 4 — Import
  [ ] W1 serial pipeline
  [ ] Resume/checkpoint support
  [ ] Entity Registry build

Phase 5 — Manuscript Sync
  [ ] W2 post-import mode
  [ ] W2 single-chapter mode
  [ ] TipTap annotation marks

Phase 6 — Analysis
  [ ] W4 Consistency Check
  [ ] W7 Metadata Ingestion + chromadb

Phase 7 — Advanced
  [ ] W5 Simulation Engine
  [ ] W6 Beta Reader

Phase 8 — Orchestrator + CLI
  [ ] W0 Orchestrator graph
  [ ] CLI Mode 1 (command mirror)
  [ ] CLI Mode 2 (autonomous, uses W0)
```

---

## 13. Writing Prompts for Claude Code

When implementing any workflow, give Claude Code this preamble:

```
Read these files before starting:
  - CLAUDE.md (skills and conventions)
  - src/ui-react/models/project.ts (schema)
  - sidecar/models/state.py (State schemas)
  - LangGraph.md (this document — architecture reference)

Then implement [specific node/workflow] following the conventions in CLAUDE.md.
Do not deviate from the State schemas defined in LangGraph.md.
Do not write directly to project files — always use propose_write().
Plan only first, ask if you find conflicts with existing code.
```
