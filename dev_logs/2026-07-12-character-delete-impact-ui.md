# Character Delete Impact UI

- Changes: expanded `ArchiveImpactModal` to count World items, character tags, graph boards, scripts, storyboards, linked scenes, scene POV, relationships, and timeline events; hard delete is hidden whenever any supported reference exists.
- Files modified: `src/ui-react/components/ArchiveImpactModal.tsx`, `tests/e2e/p1/context_menu_completeness.spec.ts`.
- Test: targeted Playwright spec `tests/e2e/p1/context_menu_completeness.spec.ts`.
- Result: targeted Playwright spec passed (8 tests).
