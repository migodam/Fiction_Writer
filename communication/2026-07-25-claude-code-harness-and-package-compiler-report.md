# Claude Code Harness Research And W1 Package Compiler Repair

Date: 2026-07-25
Branch: `codex/agent-runtime-resilience`

## Executive Result

- The official public Claude Code repository was cloned to
  `/Volumes/migodam's-external-brain/Development/Claude Code/anthropics-claude-code`.
- The repository is public, but its license says "All rights reserved" and points
  to Anthropic's Commercial Terms. The 2026 source-map disclosure did not turn
  leaked core code into open-source software. This work therefore studies only
  the official public repository and does not copy leaked or proprietary code.
- W1 package acceptance now consumes an explicit compiled execution plan instead
  of independently guessing an entity-type order in React.
- Incomplete package selections can no longer fall through to ordinary proposal
  acceptance. A package is accepted atomically or remains pending.
- Legacy projection repair now resolves attempt-isolated artifacts under
  `system/imports/<lineageId>/attempts/<attemptId>/`.
- `Import Text 18` was backed up, recompiled, repaired, accepted in place, and
  reopened successfully. It now has zero pending proposals and 108 accepted
  history entries.
- No DeepSeek request was made for this repair.

Official references:

- [Anthropic Claude Code public repository](https://github.com/anthropics/claude-code)
- [Claude Code repository license](https://raw.githubusercontent.com/anthropics/claude-code/main/LICENSE.md)
- [Report on the 2026 source-map disclosure](https://www.heise.de/en/news/Claude-Code-unintentionally-open-source-Source-map-reveals-all-11242079.html)

## Root Cause

The repeated package failures were not caused by one bad entity. They came from
three contract splits:

1. Python compiled the proposal dependency graph and persisted
   `orderedProposalIds`, but the React acceptance layer ignored that order and
   sorted proposals again by a fixed entity-type priority.
2. Producer identity was not identical across layers. Some proposals create an
   entity through `operation.entityId`, some through `operation.fields.id`, and
   older proposals rely on `targetEntityId`.
3. The legacy projection repair assumed a flat run directory even though durable
   W1 writes artifacts into attempt directories. Valid files were therefore
   reported as missing.

A fourth bug made migrations look successful while leaving the Inbox stale:
the re-review tool persisted the pre-compile proposal list instead of the
compiler's normalized proposals.

## Package Compiler V2

The package compiler is now the source of truth for execution order.

```text
Inbox proposals
  -> normalize producer identity
  -> validate required references
  -> build typed dependency graph
  -> collapse permitted SCCs
  -> deterministic topological order
  -> persist w1-package-graph-v2 metadata
  -> React validates and executes that exact order
  -> one project transaction commits or rolls back the package
```

Each compiled proposal carries:

```json
{
  "packageCompiler": {
    "contractVersion": "w1-package-graph-v2",
    "order": 0,
    "proposalCount": 108,
    "orderedProposalIds": ["..."]
  }
}
```

The compiler also publishes a typed `executionPlan`. The acceptance layer uses
the v2 plan only when every proposal agrees on the complete package membership
and order. Old packages use a deterministic compatibility graph compiler.

Safety boundaries:

- conflicting producer IDs block before canonical writes;
- duplicate or missing required producers remain compiler errors;
- update/link operations depend on their same-package create producer;
- partial selection returns an actionable package error;
- validation and application use the same ordered proposal list;
- artifact repair preserves lineage and attempt identity;
- symlink, traversal, hash, manifest, source, chapter, and scene checks remain
  fail-closed.

## Import Text 18 Evidence

Project:

`/Volumes/migodam's-external-brain/home/narrative_ide/import_test18`

Full pre-repair backup:

`/Volumes/migodam's-external-brain/home/narrative_ide/import_test18.backup-before-package-compiler-20260725`

Migration receipt root:

`system/migrations/w1-pending-semantic-rereview/20260724T183027560043Z`

Electron acceptance result:

`/tmp/narrative-ide-import-compiler-result-1784917866491/result.json`

Final state:

| Check | Result |
|---|---:|
| Pending Inbox proposals | 0 |
| Accepted history proposals | 108 |
| Chapters | 10 |
| Scenes | 10 |
| Manuscript nodes | 20 |
| Characters | 27 |
| Timeline events | 5 |
| World items | 28 |
| Restart persistence | Passed |
| New provider calls | 0 |
| New provider cost | $0 |

The repaired staged artifact no longer stores the legacy absolute
`source_file_path`. Its `source_ref` is project-relative, retains the original
source SHA-256, and identifies the real attempt.

## Harness Findings From The Official Repository

The public repository exposes plugins, commands, agents, skills, hooks, and
examples, but not a complete proprietary Claude Code core runtime. The useful
patterns are:

1. Manifest-driven extension discovery instead of a central hard-coded registry.
2. Declarative Agent definitions with explicit tool allowlists.
3. Separate Command, Agent, Skill, Policy, and Hook responsibilities.
4. Lifecycle hooks around tool use, stop, session start, and session end.
5. Startup validators for manifests, agents, hooks, scopes, and schemas.
6. Bounded loops with completion predicates, iteration limits, and persistent
   state.
7. User-visible workflow commands that submit typed durable tasks instead of
   writing canonical data from the UI.

Recommended bounded follow-up architecture:

```text
sidecar/extensions/<extension>/
  manifest.json
  commands/
  agents/
  skills/
  tools/
  policies/
  hooks/
```

Each task should carry `allowedTools`, `readSet`, `writeSet`, `maxCost`,
`requiresApproval`, and an output contract. A unified Hook Bus should enforce
package compilation, artifact verification, budget checks, and canonical
acceptance at deterministic boundaries.

Narrative IDE should retain its existing SQLite runtime, attempt isolation,
checkpoints, leases, and human decisions. Those durable capabilities are
already stronger than what the official public Claude Code repository exposes.

## Reviewer Gate

The implementation is acceptable only when all of these remain green:

- proposal graph and migration unit tests;
- W1/runtime targeted pytest;
- Workbench package Playwright tests;
- full P0/P1 Playwright;
- UI lint and build;
- headed Electron package acceptance and restart persistence;
- secret scan and `git diff --check`.

The real project backup must remain untouched until the user explicitly chooses
to remove it.

## Final Verification

| Gate | Result |
|---|---|
| W1/runtime targeted pytest | 805 passed |
| Full browser P0/P1/smoke Playwright | 279 passed |
| Focused Workbench package Playwright | 34 passed after independent review hardening |
| UI lint | Passed |
| UI production build | Passed |
| Electron native bridge smoke | Passed |
| Import Text 18 in-place accept and restart | Passed |
| `git diff --check` | Passed |
| Changed-file credential scan | No matches |

The Vite build still reports its existing large-bundle warning. This is a
performance follow-up, not an import correctness failure.

An independent low-cost SubAgent review found no P0/P1. Its only immediate
hardening recommendation was to verify each proposal's declared compiler
`order` against the shared ordered ID list. That validation and a tampered
metadata fallback test were added before the final 34-test focused pass.
