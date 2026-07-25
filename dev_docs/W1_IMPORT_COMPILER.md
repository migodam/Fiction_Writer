# W1 Import Compiler

> For supervisor-mode operation (`use_supervisor=true`), see [W1_AGENTIC_IMPORT_SUPERVISOR.md](./W1_AGENTIC_IMPORT_SUPERVISOR.md).

## Durable Attempt, Resume, and Artifact Contract (Current 2026-07-25)

Each W1 execution has stable input-derived lineage/cache identity and a distinct
attempt directory under `system/imports/<lineage_id>/attempts/<attempt_id>/`.
Checkpoint receipts revalidate source and receipt hashes before recovery. A
legacy import can migrate only from a verified contiguous prefix; stale,
noncanonical, tampered, or source-mutated state fails closed. Every active
attempt owns a RuntimeStore lease and fencing token. Snapshot publication,
checkpoint publication, and resumable metadata require that current fence; a
stale worker cannot publish state for a later child attempt.

Staged manuscript packages use ArtifactRef v2: relative path, SHA-256, contract
version, lineage ID, and attempt ID. Workbench acceptance rejects uncontained
paths, lineage/attempt mismatch, symlinks, contract mismatch, or
hash/source-manifest mismatch before canonical mutation. Legacy migration is
journaled. Package persistence uses `projectTransaction` prepared manifests,
preimages, rename/commit markers, and idempotent recovery. The current bridge
has no `fsync`, so this is not a power-loss guarantee.

The runtime records tool intents/results and may mark post-restart calls
`unknown_outcome`. Recovery Center requires a durable, versioned human decision
to retry exactly once or cancel; recovery never repeats an unknown paid call by
default. An authorization is bound to the source attempt and exact provider
tool-call ID, then consumed atomically immediately before provider I/O. A
verified receipt is reused instead of calling the provider again.

### W1 Supervisor Snapshot Contract (2026-07-25)

`W1SupervisorSnapshot/v1` is the only resumable W1 snapshot reference. It
contains immutable lineage/attempt identity, source/config/artifact receipts,
validated parent checkpoint identity, and typed body-free resume state. The UI
may show an incomplete, invalid, or source-incompatible checkpoint as a preview
but cannot fork/resume it.

`W1ResumeState/v1` retains all proposal-writer dependencies: character merge
maps/updates, tags, relationships, World operations, organizer output,
chapters/scenes, and the complete timeline branch contract. Source-derived prose
is `W1SourceTextRef/v1` plus `SourceSpan` and is rebuilt only from verified raw
source. Snapshot JSON must not contain chapter/scene bodies, prompt text, hidden
reasoning, API keys, absolute project paths, or arbitrary opaque state.

Time Travel creates a child attempt from a stable parent checkpoint. It does not
mutate existing history or overwrite accepted canonical data. Resumed W1 output
returns to the proposal gate and stays `waiting_human`/`awaiting_acceptance`
until the user accepts a complete package.

### Server Budget and Live-Runner Contract (2026-07-25)

All W1 starts and resumes use the same server-side `W1BudgetPolicy` normalizer.
Flash is capped at USD 3 and Pro at USD 8; calls, input/output/total tokens,
pricing, and missing usage fail closed. Client resume configuration can only
tighten a stored policy and cannot introduce unknown fields or relax a ceiling.

The live 10-chapter runner must bind a durable RuntimeStore run/attempt/lease
and the product supervisor/Harness observer. It records intent before provider
I/O and advances its watchdog only on durable work activity. Cancellation or
timeout at an ambiguous provider boundary becomes `unknown_outcome`, releases
the lock/lease, and requires a human decision; it is not a completed canary.

### Provider Response Recovery Contract (2026-07-19)

Provider response reuse is keyed by a stable, sequence-independent operation
key. The key excludes `attemptId`, so an equivalent operation can be verified
and reused across attempts without treating a retry as a new provider call.
Response artifacts are content-addressed and stored project-locally with
permissions `0700` for containing directories and `0600` for artifact files.
Reuse requires verification of the artifact and operation identity; an
unverified or mismatched artifact is never accepted. Recovery coverage verifies
that five saved role responses are reused while only the sixth missing role
causes one provider call; per-process singleflight prevents duplicate concurrent
execution of the same operation.

Unknown outcomes remain human-gated on both cache and network paths. The usage
ledger is rebuilt from unique cached operations and does not double-count an
operation within a session.

### Offline Legacy Replay Bridge (2026-07-25)

`tools/w1_offline_replay_attempt.py` is a zero-provider recovery tool for a
saved supervisor attempt. It validates source hash, continuous source spans,
attempt/lineage identity, usage ledger, and immutable evidence artifacts before
rebuilding only staged reviewer/proposal state. A legacy attempt that predates
per-domain `completed_domains` may bridge to runtime evidence only when exactly
one W1 runtime run has the same source hash and model, its tool usage exactly
matches the saved ledger, every tool result has a contained hash-verified
response artifact, and every expected window/domain has one durable start and
success event with no matching failure/cancel/unknown event. Differing runtime
and artifact lineage IDs are allowed solely through a recorded
`w1-legacy-identity-bridge/v1` receipt. Any missing or ambiguous proof blocks.

Dry-run does not write. `--apply` first writes an isolated backup/receipt and
may create only a new pending proposal package after the final deterministic
review and semantic gate pass; it never accepts canonical data. A replay
materializes its own manifest and verified usage ledger with a new attempt ID.
Before publication it replaces only stale pending W1 proposals from the same
lineage, then requires a non-empty pending package whose receipt count matches
an atomic proposal graph with no blocking edges. Scene-event links require
source-span overlap or an exact shared evidence receipt. A shared chunk alone
is not link evidence because a chunk can contain multiple scenes.

## Status
W1 import now uses a Hybrid Compiler spine for long novel imports. The runtime still starts from the existing Import modal and sidecar W1 endpoint, but imported material is staged through deterministic artifacts before proposals are written.

## Runtime Stages
1. Segment Manifest: split source text into stable chunk/segment records with hashes, spans, prompt profile, model, and artifact path.
2. Prompt Window Packing: pack complete chapter segments into 256k total-budget prompt windows for `deep` and `custom`, while reserving room for project digest, rolling validation, schema, and policy.
3. Scout Evidence: convert packed-window extraction output into non-canonical evidence cards. Evidence cards preserve source provenance and must not be treated as final project entities.
4. Rolling Cross-Validation Review: after each packed window, compare character, event, relationship, and scene outputs against the previous validation summary to flag duplicate characters/events, missing major characters, suspicious groups, contradictory aliases, and event merge recommendations for the next window.
5. Entity Reconciliation: compare imported candidates with existing project characters, tags, and relationships before creating proposals.
5b. Content Organizer: route world candidates to correct module containers, exclude module-contaminated and person/role-only entries, attach `categoryPath`/`parentId` hierarchy, detect merge candidates, and group surviving world items into `ProposalPackage`s by container key. Deterministic — no LLM calls.
6. Timeline Architect: deduplicate imported event candidates, classify dense/duplicate beats, infer semantic branches, assign branch-local `orderIndex`, and fill frontend-required timeline fields.
7. Proposal Review: write `review_report.json` with warnings, duplicate merges, failed chunks, safe batch-accept ids, low-confidence items, model/profile metadata, artifact paths, and proposal counts.
8. Proposal Write: only reviewed candidates become Workbench proposals.

## Artifact Contracts
- `ImportRunManifest`: `system/imports/<import_run_id>/manifest.json`; source hash, segments, prompt profile, model, and artifact directory.
- `W1SupervisorSnapshot`: immutable body-free snapshot directory with manifest,
  typed `W1ResumeState/v1`, source/config/receipt proofs, and a strict
  `W1SupervisorSnapshot/v1` reference. Source strings use `W1SourceTextRef/v1`
  and verified `SourceSpan`, never an embedded chapter body.
- `ProjectStructureDigest`: `project_structure_digest.json`; compact existing-project context for import prompts, including characters, character groups/tags, relationships, timeline branches, world containers/items, and proposal/issue risk counts.
- `PromptWindows`: `prompt_windows.json` plus manifest `prompt_windows`; packed chapter-aware prompt input windows with one or more chunk ids, chapter range, total/source budget, estimated tokens, source chars/tokens, fill ratio, digest/validation token estimates, source span, and split reason.
- `EvidenceCard`: `evidence_cards.json`; raw candidate evidence with source segment, confidence, candidate names/ids, and uncertainty.
- `ReducerArtifact`: `reducer_artifact.json`; existing-project matches, skipped duplicates, dependency edges, and warnings.
- `CrossValidationArtifact`: `cross_validation.json`; duplicate characters/events, missing major characters, suspicious groups, contradictory aliases, event merge recommendations, and warnings.
- `TimelineArchitectureArtifact`: `timeline_architecture.json`; branch list, canonical events, event classifications, discarded duplicates, scene beats, background references, fork/merge anchors, density policy, fork/merge-ready branch metadata, and layout hints.
- `ImportReviewReport`: `review_report.json`; pass/warning/fail status, warnings/errors, proposal counts, safe accept ids, blocked ids, failed chunks, duplicate merges, low-confidence items, model/profile, and artifact paths.
- `UsageLedger`: `usage_ledger.json`; authoritative non-secret provider usage for the run: actual input/output/total tokens, `actual_calls` and `api_call_count` compatibility alias, cost, model/pricing, and budget-exhaustion status. It is atomically replaced in the run artifact directory. Budget preflight returns a caller-owned reservation token that is settled or released by identity after provider I/O, so differently sized concurrent calls can complete out of order without dropping the wrong in-flight call/token/cost allowance. The legacy boolean preflight API remains task-locally bound for compatibility. Live runs fail closed when a completed provider call omits usage and `fail_on_missing_usage` is enabled. The effective policy is server-normalized and resume may only tighten it.
- `PromptPolicyDecision`: `prompt_policy_decision.json`; deterministic Orchestrator policy choice, normalized PromptPolicyPatch knobs, directive keys, and zero-cost rationale for density/topology/world-scope decisions.
- `PromptProfile`: `fast`, `balanced`, `deep`, or `custom`; controls per-prompt text budget and is recorded in the manifest.

## Prompt Window Requirements
For `deep` and `custom`, W1 uses a 256k estimated-token total input budget per prompt window. The budget includes schema/prompt-policy reserve, `ProjectStructureDigest`, rolling previous validation summary, and source chapter text. W1 packs multiple complete chapters into one window until the next chapter would exceed the remaining source budget; target fill metadata records the 0.88 fill target, but the hard invariant is `estimated_tokens <= 256000`. Normal chapters must remain complete in a window whenever they fit after reserves; W1 must not head/tail truncate normal chapters. If a single chapter is oversized after reserves, W1 may split only that chapter by paragraph/scene boundaries and must record `split_reason: single_oversized_chapter_paragraph_split`.

## Timeline Requirements
Imported timeline event proposals must include `branchId`, branch-local `orderIndex`, `locationIds`, `participantCharacterIds`, `linkedSceneIds`, `linkedWorldItemIds`, and `tags`. If the project has no root branch, W1 proposes `branch_import_main` before event proposals. Dense imports must not put every event on the root branch when semantic branch signals are available.

Event extraction prompts must emit timeline-ready scout fields before architecture: `eventClass`, `timelineClass`, `eventType`, `arcId`, `arcRole`, `causalRole`, `branchRole`, `timelineLaneHint`, `causalPredecessorHints`, `forkMergeHint`, `dedupeKey`, `chapterRange`, `importanceScore`, and merge candidate hints. W1 normalizes `eventClass`/`timelineClass` through the deterministic Timeline Event Ontology before architecture; allowed values are `canonical_event`, `scene_beat`, `background_reference`, and `discarded_duplicate`. Legacy story-beat labels such as `confrontation` or `training_breakthrough` are preserved as `eventType` and coerced with warnings rather than passed through as event classes. The model must explicitly separate canonical story-turning events from scene beats so Timeline Architect can merge/demote duplicates instead of importing every beat as a root-branch event.

Timeline Architect must deterministically reduce event candidates before proposal write. It classifies candidates as `canonical_event`, `scene_beat`, or `background_reference`; merges duplicates by exact signature plus semantic signature built from `dedupeKey`, participants, chapter anchor, and normalized semantic title; and records explicit merge/discard reasons in `timeline_architecture.json`. Scene beats and background references are not written as canonical timeline proposals by default.

Topology branches must include `branchId`/`id`, `parentBranchId`, `forkEventId`, `mergeEventId`, `rankStart`, `rankEnd`, `laneId`, `sortOrder`, geometry, density, and layout hints where available. Branch/lane inference should prefer `arcId` and `timelineLaneHint`, then theme/faction/location/participant fallbacks. The root branch is reserved for mainline arc-level turning points or deterministic fallback when no semantic lane reaches the branch threshold.

Timeline Architect enforces a minimum canonical-event density when `converge_targets.expected_min_events`, `tool_operating_spec.event_density_target`, or chapter-level profile evidence indicates under-extraction. Scene beats may still be downgraded, but high-confidence turning-point evidence is promoted back to canonical events with warnings when a long import would otherwise collapse to a trivial mainline.

`ConvergeTarget` values are source-adaptive when supervisor mode is active: `_ensure_orchestrator_plan()` calls `select_granularity_profile()` and passes the result to `plan_converge_target()`, so character and event density targets reflect the actual source type (CJK webnovel, standard novel, short story) rather than the flat TOS default.

`ImportPlan` records the selected source type, window strategy, extraction tool domains, prompt policy, and cost policy before extraction. The current planner is deterministic and schema-first. Future LLM/RAG planners must produce a `PlannerProposal` (`sidecar/models/state.py`) and submit it through `planner_proposal_to_import_plan()` (`sidecar/supervisor/planner.py`), which validates the proposal with `validate_planner_proposal()` then converts it to an `ImportPlan` and validates the result with `validate_import_plan()`. The LLM may propose; the validator decides; the executor runs deterministically.

`PromptPolicyPatch` is the bounded prompt-adaptation surface inside a `PlannerProposal`. It accepts only fixed knobs such as existing-timeline emphasis, source-provenance requirement, canonical-event preference, minor-NPC suppression, relationship evidence requirement, world-boundary strictness, `event_density_strategy`, `topology_fidelity`, `world_model_scope`, and `timeline_label_granularity`. `prompt_policy.py` converts these knobs into static directive metadata stored on `ImportPlan.prompt_policy`; it does not accept raw prompt text. The deterministic Orchestrator may choose `sparse_turning_points`, `arc_level`, `chapter_level`, or `scene_level` from source profile and quality hints, then persists `prompt_policy_decision.json` so the user can review why an import used a specific event density.

When `event_density_strategy == "sparse_turning_points"`, W1 lowers converge targets and event caps to focus on irreversible state changes, branch/fork/merge anchors, and timeline-worthy causal turns. Scene beats remain eligible for manuscript notes, but should not become canonical timeline proposals merely to satisfy a static count.

**Source profiler**: `analyze_source_profile(chunks, source_language, prompt_profile)` in `sidecar/models/state.py` computes deterministic metadata — chapter count, avg chars per chapter, dialogue density hint, and named-entity density hint — then classifies source type using the same chapter/language thresholds as `select_granularity_profile()`. The `fast` profile override is intentionally omitted: the profiler is descriptive, not prescriptive. It has no LLM dependency. `_ensure_orchestrator_plan()` stores results in `state["source_profile"]` (`ImportSupervisorState.source_profile`), and `proposal_write` persists `source_profile.json` for benchmark review.

**Import plan validation**: `validate_import_plan(plan)` in `sidecar/models/state.py` enforces the W1 execution contract before plan execution. It accepts deterministic and future `llm_proposed` plans only when the plan uses known source/tool values, all required W1 tools are present and enabled, dynamic prompt edits are disabled, API 402 stop is enabled, and proposal-gate safety fields remain true. `_ensure_orchestrator_plan()` stores the result in `state["import_plan_validation"]`, and `proposal_write` persists `import_plan_validation.json`.

## World Ontology Requirements
W1 normalizes world entries with a deterministic World Ontology before proposal write. Allowed categories are `location`, `organization`, `faction`, `item`, `artifact`, `rule`, `system`, `cultivation_method`, `concept`, `culture`, and `custom`.

For Chinese source text, W1 preserves Chinese user-facing labels/descriptions and applies rule-based fallback mapping before trusting model categories: `门派`/`宗门`/`帮派` map to `organization`; `势力`/`阵营`/`联盟` map to `faction`; `功法`/`法术`/`术法`/`法诀` map to `cultivation_method`; `修炼体系` maps to `system`; `规则`/`法则` map to `rule`; `丹药`/`物品` map to `item`; `法器`/`宝物` map to `artifact`; `地名`/`地点` and place-like suffixes such as `堂`/`峰`/`谷`/`院` map to `location` unless explicit faction/organization context overrides them. Named organizations such as `七玄门` must be migrated out of character candidates into `world_detailed` and routed to organization/faction containers, not character proposals; person-like world entries must be skipped from world-item proposals.

The World organizer stage must exclude module-owned content from World Model proposals. Relationship graphs, event timelines, single scene beats, and person/role-only entries remain owned by Relationship, Timeline, Manuscript, or Character modules. W1 import world containers use localized semantic containers such as `地理位置`, `门派组织`, `功法与术法`, `修炼境界与制度`, and `文化与习俗`; empty English starter containers are removed during package acceptance. World proposals may include compatibility fields `categoryPath` and `parentId` for hierarchy display until a full tree model is introduced.

## Semantic Reconciliation Contracts

Character matches produce an `EntityMergeDecision/v1` in `reducer_artifact.json`. It records field-by-field union/append/preserve actions for aliases, background, experience entries, traits, notes, confidence, physical description, speech style, and arc notes. Existing canonical fields are never silently overwritten; divergent text is retained as evidence and reported in `semantic_conflicts`.

For Chinese projects, character tag names must be Chinese. Known English editorial labels are translated while retaining `sourceName` and normalization metadata; unmapped English labels are rejected into `tag_rejections`, never blanked or proposed. The Chinese relationship ontology permits only normalized semantic categories with explicit `ontologyDirection`: mentor/political links are directed, while family, romance, rivalry, sworn-bond, conflict, and alliance links are symmetric. Event/action labels such as `解惑`/`选拔` and descriptive phrases such as `冷冰冰的师兄` are evidence or notes, not relationship types.

Organizer container targets are deterministic: each emitted notebook has a stable `world_container_<container_key>` ID and every world item references it through `containerId` (with `parentId` reserved for a future folder tree). A candidate can occupy one normalized category/container only; person, rank, relationship, timeline, and manuscript contamination is excluded before placement.

## Stage 5b: Content Organizer

`sidecar/supervisor/organizer.py` — called after Entity Reconciliation, before Timeline Architect.

### Input
`OrganizerInput` (TypedDict): `characters`, `events`, `relationships`, `world_candidates`, `manuscript_notes`, `timeline_architecture`, `project_digest`, `source_language`.

### Output
`OrganizerOutput` (TypedDict): `world_containers`, `world_items`, `excluded_items`, `merge_candidates`, `proposal_packages`, `warnings`.

### Classification Pipeline (priority order, first match wins)

| Priority | Check | Action | Reason code |
|----------|-------|--------|-------------|
| 1 | Name in `_CONTAMINATION_NAMES` or matches contamination pattern | `ExcludedItem` | `module_contamination` |
| 2 | Name is a known character name OR candidate role is character/person | `ExcludedItem` | `person_name` |
| 3 | Name in `_IDENTITY_RANK_NAMES` (记名弟子/内门弟子/外门弟子/etc.) | `ExcludedItem` | `identity_rank` |
| 4 | Rank title AND raw category is `cultivation_method` | `ExcludedItem` | `role_rank` |
| 5 | Pass — normalize category, build `categoryPath`, emit `WorldItemProposal` | — | — |

### Module Ownership Rules
- **Relationship module** owns: 人物关系图, 关系网络, relationship graph strings.
- **Timeline module** owns: 事件时间线, timeline strings.
- **Character module** owns: person names that exist in `entity_registry["characters"]`.
- **Manuscript module** owns: identity/institutional ranks (记名弟子, 护法, 堂主, etc.).
- **World Model** owns: named locations, organizations, factions, items, artifacts, cultivation methods, rules, systems, concepts, culture.

### Ambiguity Handling
Names ending in `堂` or `院` with no explicit organization context default to `location` and emit a `warnings` entry. The Lead integration step or a future LLM disambiguation pass may override.

### ProposalPackage Grouping
Surviving world items are grouped by `container_key` into `ProposalPackage` entries. Empty containers are not emitted. Package IDs are `org_{container_key}_{random_hex8}`.

### Integration Call-site (applied by Lead)
```python
# AFTER node_reconcile_entities, BEFORE node_architect_timeline
from sidecar.supervisor.organizer import organize_project_content, OrganizerInput

_org_input: OrganizerInput = {
    "characters": state.get("entity_registry", {}).get("characters", {}),
    "events": list(state.get("entity_registry", {}).get("events", {}).values()),
    "relationships": state.get("relationships", []),
    "world_candidates": state.get("entity_registry", {}).get("world_detailed", {}),
    "manuscript_notes": [],
    "timeline_architecture": state.get("timeline_architecture", {}),
    "project_digest": state.get("project_structure_digest", {}),
    "source_language": state.get("source_language", "zh"),
}
_org_out = organize_project_content(_org_input)
state["entity_registry"]["world_detailed"] = {
    item["name"]: item for item in _org_out["world_items"]
}
# Persist artifact: _save_artifact(artifact_dir, "organizer_output.json", _org_out)
```

## Inbox Package Acceptance
W1 import proposals are grouped by `importRunId` into package-level Workbench cards. Accepting a package applies all same-run chapter, scene, branch, event, character, relationship, world-container, and world-item proposals as one transaction. A partial package selection is rejected and cannot fall through to ordinary proposal acceptance. The transaction pre-registers same-package IDs as valid references and rolls back the whole package if any blocking edge remains.

Before the package is exposed to Workbench, `sidecar/shared/proposal_graph.py` compiles its typed reference graph. Timeline Architect is the only event-identity authority; proposal writing must not run a second fuzzy event-dedupe pass. The compiler registers same-package `create` producers plus typed canonical IDs, derives loser-to-survivor event remaps from `mergedEventIds`, rewrites every supported scalar/list/nested reference, and records all rewrites or dropped optional backlinks in `proposal_graph.json`. Producer identity uses the shared precedence `operation.entityId`, `operation.fields.id`, then `proposal.targetEntityId`; conflicting explicit IDs are blocking compiler errors.

Required structural edges include event-to-branch, scene-to-chapter, relationship endpoints, and world-item-to-container. Missing required edges, duplicate producers, or required-edge cycles make the package non-atomic and remove the whole staged run before review. Optional backlinks may be remapped or dropped with diagnostics. Tarjan SCC analysis permits backlink cycles such as character-to-event-to-character; Kahn ordering over the SCC condensation graph produces a deterministic proposal order.

Package graph contract `w1-package-graph-v2` persists the complete `orderedProposalIds` and typed execution plan on every normalized proposal. The React acceptance layer consumes this order for both validation and application; it does not re-sort a v2 package by entity type. It accepts the v2 plan only when every pending proposal agrees on package count, membership, and order. A deterministic dependency-graph compiler remains as compatibility fallback for legacy packages. Only same-package `create` operations may provide new IDs; updates never masquerade as producers.

Package-level blocked reasons must name the culprit proposal and blocking edge, for example a missing event, missing branch, schema mismatch, duplicate merge, or unsupported operation. Previously blocked packages remain retryable so a user can accept again after code/data fixes without manually clearing stale `lastBlockReason`.

## Character Card Requirements
W1 import creates compact character-card drafts only. It may fill identity, aliases, role, concise summary, grounded tags/traits, evidence notes, confidence, and open questions. Deep fields such as goals, fears, secrets, speech style, and arc should remain empty unless a later enrichment workflow explicitly owns them.

Character extraction prompts must include project digest placeholders, alias/epithet reconciliation, source-language normalization, protagonist/mentor/antagonist/ally/minor story-function classification, `groupKey` hints, importance calibration, and anti-summary-bloat rules. Group hints are advisory until reducer/workflow plumbing consumes them, but the prompt contract must preserve `main_characters`, `mentors_antagonists`, `allies_family`, and `minor_characters`.

All five deep extraction prompts require `source_language_label` and `language_policy` template variables injected at call time from `state["source_language"]` and `tool_operating_spec["language_policy"]` respectively. This applies to both the supervisor path (`extract_window` in `sidecar/supervisor/tools.py`) and the legacy LangGraph path (`node_process_chunks` in `sidecar/workflows/w1_import.py`).

**Extraction granularity dispatch**: in the supervisor path only, `extract_window` calls `_select_extraction_prompts(state)` before each gather. If `state["import_granularity_profile"]` is populated, the matching variant constant is used per domain (character / event / world / relationship). If the profile is absent or a specific field is unset, the original constant is used as the fallback. Scene summaries (`W1_EXTRACT_SCENE_SUMMARIES`) are not dispatched and remain constant regardless of profile. The legacy LangGraph path continues to use the original deep prompt constants. The `minor_repair` tool strips personality traits containing ≥4 consecutive Latin characters when `source_language == "zh"`, aligned with the `_symptom_flags` detection threshold.

`extract_window` writes the selected prompt variant manifest into each window artifact. `proposal_write` also writes `import_granularity_profile.json`, `import_plan.json`, and `extraction_prompt_variants.json` before proposal writes begin so benchmark validation can prove which profile and prompt variants were active.

## Cross-Validation Requirements
Cross-validation is wired into the packed-window scout loop. After each packed window, W1 runs the reviewer prompt against that window's character, event, relationship, and scene outputs plus the current project digest and previous validation summary. In supervisor mode, `extract_window` dynamically prepends the current `PROJECT_STRUCTURE_DIGEST`, rolling registry summary, `PREVIOUS_VALIDATION_SUMMARY`, and `IMPORT_PLAN_CONTEXT` at call time; this prevents the chunk reassembly path from dropping window context. The merged `cross_validation.json` artifact is fed into later windows as `PREVIOUS_VALIDATION_SUMMARY`. It must report:
- `duplicate_characters`
- `duplicate_events`
- `missing_major_characters`
- `suspicious_groups`
- `contradictory_aliases`
- `event_merge_recommendations`
- `warnings`

The review is non-canonical: it may recommend merges, demotions, group corrections, and missing major entities, but it must not directly mutate project storage or bypass Workbench proposal review.

## JSON Robustness Requirements
Chunk prompt parsing must tolerate fenced JSON, trailing commas, and recoverable malformed model output. Failed extraction categories must write failure artifacts and must not be cached as successful empty prompt outputs.

## Source Provenance And Manuscript Staging
`SourceSpan` is the canonical W1 provenance shape: `raw_source_hash`, `absolute_start`, `absolute_end`, and `substring_hash`. `make_source_span()`, `validate_source_span()`, and `reconstruct_source_span()` validate spans against the original raw source using Python character offsets. Segment, chapter, and staged scene projections must carry valid spans; `node_build_manuscript()` derives chapter bodies only from raw source chunks, never from LLM extraction output.

Before Workbench acceptance, W1 writes `staged_manuscript_projection.json` under `system/imports/<lineage_id>/attempts/<attempt_id>/`. It contains the deterministic chapter, ManuscriptNode, and scene-document payloads plus `acceptance_required: true`; W1 must not write canonical `manuscript.json`, `writing/manuscript/nodes.json`, or scene Markdown files. Chapter and scene proposals include `stagedManuscriptProjection` with a project-relative ArtifactRef, contract version, lineage ID, attempt ID, chapter id, and scene id so the acceptance layer can apply the projection transactionally. One-version legacy repair supports both the old flat run layout and attempt-isolated layout, but verifies containment, real paths, manifest/source hashes, chapters, and scenes before rewriting descriptors.

`PlannerProposal.next_action` is a bounded optional hint. It may request a registered supervisor tool, `stop`, or a named-window `rerun`. Validation rejects unknown tools and malformed actions. `resolve_planner_next_action()` applies deterministic fallback and refuses reruns after the iteration cap or API-402 budget stop; a validated `stop` ends before supervisor tools begin. The proposal gate, validator sequence, and normal fixed pipeline remain deterministic.

## Parallel Workstream Handoff
Future branches should treat this file and the artifact JSON files as the integration contract.

- Entity workstreams may extend `ReducerArtifact`, but must not bypass evidence cards.
- Timeline workstreams may improve branch/fork/merge inference, but must keep required event fields populated.
- Prompt/performance workstreams may add richer profile behavior, but must keep prompt profile values compatible with the four current values.

## Import Quality Diagnostics
Run the diagnostics tool directly against a Narrative IDE project when reviewing long-import quality:

```bash
python tools/w1_import_diagnostics.py /path/to/project --import-run-id import_x --format both
```

The command reads `system/inbox.json` plus the selected `system/imports/<import_run_id>/` artifacts and reports proposal counts, character-card compactness, trait noise, branch density, scene-beat discards, duplicate event clusters, and Import_Test6 symptom flags. Default diagnostics exit `0`; malformed input exits `2`; `--fail-on-threshold` exits `1` when any symptom flag is present.
