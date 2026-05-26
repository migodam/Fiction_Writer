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
- `PromptProfile`: `fast`, `balanced`, `deep`, or `custom`; controls per-prompt text budget and is recorded in the manifest.

## Prompt Window Requirements
For `deep` and `custom`, W1 uses a 256k estimated-token total input budget per prompt window. The budget includes schema/prompt-policy reserve, `ProjectStructureDigest`, rolling previous validation summary, and source chapter text. W1 packs multiple complete chapters into one window until the next chapter would exceed the remaining source budget; target fill metadata records the 0.88 fill target, but the hard invariant is `estimated_tokens <= 256000`. Normal chapters must remain complete in a window whenever they fit after reserves; W1 must not head/tail truncate normal chapters. If a single chapter is oversized after reserves, W1 may split only that chapter by paragraph/scene boundaries and must record `split_reason: single_oversized_chapter_paragraph_split`.

## Timeline Requirements
Imported timeline event proposals must include `branchId`, branch-local `orderIndex`, `locationIds`, `participantCharacterIds`, `linkedSceneIds`, `linkedWorldItemIds`, and `tags`. If the project has no root branch, W1 proposes `branch_import_main` before event proposals. Dense imports must not put every event on the root branch when semantic branch signals are available.

Event extraction prompts must emit timeline-ready scout fields before architecture: `eventClass`, `timelineClass`, `eventType`, `arcId`, `arcRole`, `causalRole`, `branchRole`, `timelineLaneHint`, `causalPredecessorHints`, `forkMergeHint`, `dedupeKey`, `chapterRange`, `importanceScore`, and merge candidate hints. W1 normalizes `eventClass`/`timelineClass` through the deterministic Timeline Event Ontology before architecture; allowed values are `canonical_event`, `scene_beat`, `background_reference`, and `discarded_duplicate`. Legacy story-beat labels such as `confrontation` or `training_breakthrough` are preserved as `eventType` and coerced with warnings rather than passed through as event classes. The model must explicitly separate canonical story-turning events from scene beats so Timeline Architect can merge/demote duplicates instead of importing every beat as a root-branch event.

Timeline Architect must deterministically reduce event candidates before proposal write. It classifies candidates as `canonical_event`, `scene_beat`, or `background_reference`; merges duplicates by exact signature plus semantic signature built from `dedupeKey`, participants, chapter anchor, and normalized semantic title; and records explicit merge/discard reasons in `timeline_architecture.json`. Scene beats and background references are not written as canonical timeline proposals by default.

Topology branches must include `branchId`/`id`, `parentBranchId`, `forkEventId`, `mergeEventId`, `rankStart`, `rankEnd`, `laneId`, `sortOrder`, geometry, density, and layout hints where available. Branch/lane inference should prefer `arcId` and `timelineLaneHint`, then theme/faction/location/participant fallbacks. The root branch is reserved for mainline arc-level turning points or deterministic fallback when no semantic lane reaches the branch threshold.

Timeline Architect enforces a minimum canonical-event density when `converge_targets.expected_min_events`, `tool_operating_spec.event_density_target`, or chapter-level profile evidence indicates under-extraction. Scene beats may still be downgraded, but high-confidence turning-point evidence is promoted back to canonical events with warnings when a long import would otherwise collapse to a trivial mainline.

## World Ontology Requirements
W1 normalizes world entries with a deterministic World Ontology before proposal write. Allowed categories are `location`, `organization`, `faction`, `item`, `artifact`, `rule`, `system`, `concept`, `culture`, and `custom`.

For Chinese source text, W1 preserves Chinese user-facing labels/descriptions and applies rule-based fallback mapping before trusting model categories: `门派`/`宗门`/`帮派` map to `organization`; `势力`/`阵营`/`联盟` map to `faction`; `功法`/`法术`/`修炼体系` map to `system`; `规则`/`法则` map to `rule`; `丹药`/`物品` map to `item`; `法器`/`宝物` map to `artifact`; `地名`/`地点` map to `location`. Named organizations such as `七玄门` must be migrated out of character candidates into `world_detailed` and routed to organization/faction containers, not character or location proposals.

## Character Card Requirements
W1 import creates compact character-card drafts only. It may fill identity, aliases, role, concise summary, grounded tags/traits, evidence notes, confidence, and open questions. Deep fields such as goals, fears, secrets, speech style, and arc should remain empty unless a later enrichment workflow explicitly owns them.

Character extraction prompts must include project digest placeholders, alias/epithet reconciliation, source-language normalization, protagonist/mentor/antagonist/ally/minor story-function classification, `groupKey` hints, importance calibration, and anti-summary-bloat rules. Group hints are advisory until reducer/workflow plumbing consumes them, but the prompt contract must preserve `main_characters`, `mentors_antagonists`, `allies_family`, and `minor_characters`.

All five deep extraction prompts require `source_language_label` and `language_policy` template variables injected at call time from `state["source_language"]` and `tool_operating_spec["language_policy"]` respectively. This applies to both the supervisor path (`extract_window` in `sidecar/supervisor/tools.py`) and the legacy LangGraph path (`node_process_chunks` in `sidecar/workflows/w1_import.py`).

**Extraction granularity dispatch**: in the supervisor path only, `extract_window` calls `_select_extraction_prompts(state)` before each gather. If `state["import_granularity_profile"]` is populated, the matching variant constant is used per domain (character / event / world / relationship). If the profile is absent or a specific field is unset, the original constant is used as the fallback. Scene summaries (`W1_EXTRACT_SCENE_SUMMARIES`) are not dispatched and remain constant regardless of profile. The legacy LangGraph path continues to use the original deep prompt constants. The `minor_repair` tool strips personality traits containing ≥4 consecutive Latin characters when `source_language == "zh"`, aligned with the `_symptom_flags` detection threshold.

## Cross-Validation Requirements
Cross-validation is wired into the packed-window scout loop. After each packed window, W1 runs the reviewer prompt against that window's character, event, relationship, and scene outputs plus the current project digest and previous validation summary. The merged `cross_validation.json` artifact is fed into the next window as `PREVIOUS_VALIDATION_SUMMARY`. It must report:
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
