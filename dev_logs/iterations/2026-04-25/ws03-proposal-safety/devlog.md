# WS-03 Proposal Safety Dev Log

- Date: 2026-04-25
- Branch: `codex/ws03-proposal-safety`
- Target: Proposal Acceptance and Canonical Data Safety Closure

## Multi-Agent Workflow
- Explorer role: subagent inspected proposal data model, Workbench UI, store actions, and `projectService`; no edits.
- Implementer role: local implementation in owned paths plus focused tests.
- Reviewer role: requested subagent review, but it hit usage limits; performed local reviewer pass for reference safety, shared-surface drift, and missing tests.

## Audit Findings
- Accept/reject entered through `WorkbenchWorkspace` and delegated to `projectService.resolveProposal`.
- Previous accept flow moved proposals to history before proving canonical changes were applied.
- Update proposals with `entityId` but no `fields.id` were marked accepted without mutating canonical data.
- Issue cleanup mixed open issues with `dismissedAt` on reject and kept stale proposal references.
- Workbench history/runs/prompts containers lacked stable selectors used by existing smoke coverage.

## Changes Made
- Added transaction-style proposal application for supported canonical create/update/delete operations.
- Added reference validation before accepting proposal-created or proposal-updated canonical records.
- Blocked unsupported or unapplied canonical operations by keeping the proposal pending and surfacing a Workbench issue.
- Updated issue cleanup so accepted linked issues move to history, rejected linked issues remain open, and stale `suggestedProposalIds` are removed.
- Cleared proposal, target entity, and origin issue unread flags on accepted resolution.
- Added stable per-proposal accept/reject selectors and missing Workbench list selectors.
- Added focused Playwright coverage for accepted, rejected, and blocked proposal paths.

## Files Modified
- `src/ui-react/components/WorkbenchWorkspace.tsx`
- `src/ui-react/services/projectService.ts`
- `tests/e2e/p1/cross_page_links.spec.ts`
- `tests/e2e/p1/workbench_proposal_safety.spec.ts`
- `dev_logs/iterations/2026-04-25/ws03-proposal-safety/devlog.md`

## Shared Surfaces Touched
- `src/ui-react/services/projectService.ts` (explicitly owned/shared in WS-03 task pack)
- No edits to `src/ui-react/store.ts`, `src/ui-react/models/project.ts`, or canonical docs.

## Tests
- `npm run ui:build` -> PASS
- `npx playwright test tests/e2e/p1/workbench_proposal_safety.spec.ts --config tests/playwright.config.ts` -> PASS (3/3)
- `npx playwright test tests/e2e/p0/navigation.spec.ts --config tests/playwright.config.ts` -> PASS (1/1)
- `npx playwright test tests/e2e/smoke.spec.ts -g "workbench routes expose imports runs and prompts" --config tests/playwright.config.ts` -> PASS (1/1)
- `npx playwright test tests/e2e/p1/cross_page_links.spec.ts --config tests/playwright.config.ts` -> PARTIAL: Workbench proposal test passed; two older non-WS-03 tests timed out on missing character/world selectors outside owned scope.

## Remaining Risks
- `link`/`unlink` proposal operations are intentionally blocked until a dedicated canonical reference mutator exists.
- Unsupported entity proposal types remain pending with a surfaced issue rather than being accepted as no-ops.
- Existing cross-page selector drift in Characters/World remains outside this workstream.
