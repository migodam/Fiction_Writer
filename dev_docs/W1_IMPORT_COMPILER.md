# W1 Import Compiler

> For supervisor-mode operation (`use_supervisor=true`), see [W1_AGENTIC_IMPORT_SUPERVISOR.md](./W1_AGENTIC_IMPORT_SUPERVISOR.md).

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
- `ProjectStructureDigest`: `project_structure_digest.json`; compact existing-project context for import prompts, including characters, character groups/tags, relationships, timeline branches, world containers/items, and proposal/issue risk counts.
- `PromptWindows`: `prompt_windows.json` plus manifest `prompt_windows`; packed chapter-aware prompt input windows with one or more chunk ids, chapter range, total/source budget, estimated tokens, source chars/tokens, fill ratio, digest/validation token estimates, source span, and split reason.
- `EvidenceCard`: `evidence_cards.json`; raw candidate evidence with source segment, confidence, candidate names/ids, and uncertainty.
- `ReducerArtifact`: `reducer_artifact.json`; existing-project matches, skipped duplicates, dependency edges, and warnings.
- `CrossValidationArtifact`: `cross_validation.json`; duplicate characters/events, missing major characters, suspicious groups, contradictory aliases, event merge recommendations, and warnings.
- `TimelineArchitectureArtifact`: `timeline_architecture.json`; branch list, canonical events, event classifications, discarded duplicates, scene beats, background references, fork/merge anchors, density policy, fork/merge-ready branch metadata, and layout hints.
- `ImportReviewReport`: `review_report.json`; pass/warning/fail status, warnings/errors, proposal counts, safe accept ids, blocked ids, failed chunks, duplicate merges, low-confidence items, model/profile, and artifact paths.
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
W1 import proposals are grouped by `importRunId` into package-level Workbench cards. Accepting a package applies all same-run chapter, scene, branch, event, character, relationship, world-container, and world-item proposals as one transaction. The transaction pre-registers same-package IDs as valid references, applies operations by dependency priority, and rolls back the whole package if any blocking edge remains.

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
