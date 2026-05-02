# W1 Import Compiler

## Status
W1 import now uses a Hybrid Compiler spine for long novel imports. The runtime still starts from the existing Import modal and sidecar W1 endpoint, but imported material is staged through deterministic artifacts before proposals are written.

## Runtime Stages
1. Segment Manifest: split source text into stable chunk/segment records with hashes, spans, prompt profile, model, and artifact path.
2. Scout Evidence: convert chunk extraction output into non-canonical evidence cards. Evidence cards preserve source provenance and must not be treated as final project entities.
3. Entity Reconciliation: compare imported candidates with existing project characters, tags, and relationships before creating proposals.
4. Timeline Architect: deduplicate imported event candidates, classify dense/duplicate beats, infer semantic branches, assign branch-local `orderIndex`, and fill frontend-required timeline fields.
5. Proposal Review: write `review_report.json` with warnings, duplicate merges, failed chunks, safe batch-accept ids, low-confidence items, model/profile metadata, artifact paths, and proposal counts.
6. Proposal Write: only reviewed candidates become Workbench proposals.

## Artifact Contracts
- `ImportRunManifest`: `system/imports/<import_run_id>/manifest.json`; source hash, segments, prompt profile, model, and artifact directory.
- `ProjectStructureDigest`: `project_structure_digest.json`; compact existing-project context for import prompts, including characters, character groups/tags, relationships, timeline branches, world containers/items, and proposal/issue risk counts.
- `PromptWindows`: `prompt_windows.json` plus manifest `prompt_windows`; chapter-aware prompt input windows with chunk ids, chapter range, estimated tokens, source chars, digest/validation token estimates, source span, and split reason.
- `EvidenceCard`: `evidence_cards.json`; raw candidate evidence with source segment, confidence, candidate names/ids, and uncertainty.
- `ReducerArtifact`: `reducer_artifact.json`; existing-project matches, skipped duplicates, dependency edges, and warnings.
- `TimelineArchitectureArtifact`: `timeline_architecture.json`; branch list, canonical events, discarded duplicate/scene-beat events, density policy, fork/merge-ready branch metadata, and layout hints.
- `ImportReviewReport`: `review_report.json`; pass/warning/fail status, warnings/errors, proposal counts, safe accept ids, blocked ids, failed chunks, duplicate merges, low-confidence items, model/profile, and artifact paths.
- `PromptProfile`: `fast`, `balanced`, `deep`, or `custom`; controls per-prompt text budget and is recorded in the manifest.

## Prompt Window Requirements
For `deep` and `custom`, W1 uses a 256k estimated-token total input budget per prompt window. The budget includes schema/prompt-policy reserve, `ProjectStructureDigest`, previous validation summary, and source chapter text. Normal chapters must remain complete in a window whenever they fit after reserves; W1 must not head/tail truncate normal chapters. If a single chapter is oversized after reserves, W1 may split only that chapter by paragraph/scene boundaries and must record `split_reason: single_oversized_chapter_paragraph_split`.

## Timeline Requirements
Imported timeline event proposals must include `branchId`, branch-local `orderIndex`, `locationIds`, `participantCharacterIds`, `linkedSceneIds`, `linkedWorldItemIds`, and `tags`. If the project has no root branch, W1 proposes `branch_import_main` before event proposals. Dense imports must not put every event on the root branch when semantic branch signals are available.

## Character Card Requirements
W1 import creates compact character-card drafts only. It may fill identity, aliases, role, concise summary, grounded tags/traits, evidence notes, confidence, and open questions. Deep fields such as goals, fears, secrets, speech style, and arc should remain empty unless a later enrichment workflow explicitly owns them.

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
