# W1 Import Compiler

## Status
W1 import now uses a Hybrid Compiler spine for long novel imports. The runtime still starts from the existing Import modal and sidecar W1 endpoint, but imported material is staged through deterministic artifacts before proposals are written.

## Runtime Stages
1. Segment Manifest: split source text into stable chunk/segment records with hashes, spans, prompt profile, model, and artifact path.
2. Scout Evidence: convert chunk extraction output into non-canonical evidence cards. Evidence cards preserve source provenance and must not be treated as final project entities.
3. Entity Reconciliation: compare imported candidates with existing project characters, tags, and relationships before creating proposals.
4. Timeline Architect: deduplicate imported event candidates, attach them to a root branch, assign `orderIndex`, and fill frontend-required timeline fields.
5. Proposal Review: write `review_report.json` with warnings, duplicate merges, low-confidence items, and proposal counts.
6. Proposal Write: only reviewed candidates become Workbench proposals.

## Artifact Contracts
- `ImportRunManifest`: `system/imports/<import_run_id>/manifest.json`; source hash, segments, prompt profile, model, and artifact directory.
- `EvidenceCard`: `evidence_cards.json`; raw candidate evidence with source segment, confidence, candidate names/ids, and uncertainty.
- `ReducerArtifact`: `reducer_artifact.json`; existing-project matches, skipped duplicates, dependency edges, and warnings.
- `TimelineArchitectureArtifact`: `timeline_architecture.json`; branch list, canonical events, discarded duplicate events, and density policy.
- `ImportReviewReport`: `review_report.json`; pass/warning/fail status, warnings/errors, proposal counts, duplicate merges, and low-confidence items.
- `PromptProfile`: `fast`, `balanced`, `deep`, or `custom`; controls per-prompt text budget and is recorded in the manifest.

## Timeline Requirements
Imported timeline event proposals must include `branchId`, `orderIndex`, `locationIds`, `participantCharacterIds`, `linkedSceneIds`, `linkedWorldItemIds`, and `tags`. If the project has no root branch, W1 proposes `branch_import_main` before event proposals.

## Parallel Workstream Handoff
Future branches should treat this file and the artifact JSON files as the integration contract.

- Entity workstreams may extend `ReducerArtifact`, but must not bypass evidence cards.
- Timeline workstreams may improve branch/fork/merge inference, but must keep required event fields populated.
- Prompt/performance workstreams may add richer profile behavior, but must keep prompt profile values compatible with the four current values.
