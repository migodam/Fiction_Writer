# P1 Characters and World Link Repairs

## Scope
- Updated `CharactersWorkspace.tsx`, `WorldWorkspace.tsx`, and P1 coverage only.
- Preserved concurrent dirty-worktree changes and did not touch Timeline implementation.

## Changes
- Added current-IA character actions for filtered Timeline Events and Relationship Graph navigation.
- Replaced stale `/timeline/timeline` targets in Character and World links with `/timeline/events`.
- Added stable map marker selectors and verified marker navigation preserves the location filter.
- Added an explicit tag selection selector so the search control is not confused with tag-tree drag/drop targets.
- Added coverage for nested imported World folders and category folders using the current Folder UI labels.

## Verification
- Pending: focused P1 specs, `npm run ui:lint`, and `npm run ui:build`.
