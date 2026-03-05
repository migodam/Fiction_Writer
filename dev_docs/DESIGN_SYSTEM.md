# Narrative IDE — Design System v1 (Dark, Product-grade)
Source of truth for ALL UI styling and interaction primitives.
Goal: consistent VSCode/Premiere-like desktop IDE.

------------------------------------------------------------
0) Principles (Non-negotiable)
- Single source of truth: tokens -> components -> pages.
- No hard-coded colors in components. Use tokens only.
- Layout is IDE: Activity Bar + Sidebar + Workspace + Inspector + Status Bar.
- Every page must have meaningful empty states (never blank).
- Selection is global: selected entity drives Inspector + highlights across views.
- Candidate workflow: grey until confirmed; Confirm is explicit, always visible.

------------------------------------------------------------
1) Design Tokens (CSS Variables)
Use these tokens in index.css and map them to Tailwind/theme if applicable.

1.1 Color — Surfaces
--bg: #0B0F14
--bg-elev-1: #0F1620
--bg-elev-2: #121B26
--panel: #0F1620
--card: #101826
--card-2: #0E1520

1.2 Color — Borders / Lines
--border: rgba(255,255,255,0.08)
--border-2: rgba(255,255,255,0.12)
--divider: rgba(255,255,255,0.06)

1.3 Color — Text
--text: rgba(255,255,255,0.92)
--text-2: rgba(255,255,255,0.70)
--text-3: rgba(255,255,255,0.52)
--text-invert: #0B0F14

1.4 Color — Brand / Accents
--brand: #7C3AED        (primary purple)
--brand-2: #A78BFA      (soft purple)
--blue: #3B82F6         (secondary action)
--green: #22C55E        (confirm)
--red: #EF4444          (danger)
--amber: #F59E0B        (warnings)
--cyan: #06B6D4         (info)

1.5 Color — States
--focus: rgba(124,58,237,0.55)
--hover: rgba(255,255,255,0.04)
--active: rgba(124,58,237,0.12)
--selected: rgba(124,58,237,0.18)
--update-glow: rgba(245,158,11,0.18)

1.6 Radius
--r-xs: 8px
--r-sm: 10px
--r-md: 12px
--r-lg: 16px

1.7 Shadow (subtle, modern)
--shadow-1: 0 10px 30px rgba(0,0,0,0.35)
--shadow-2: 0 16px 50px rgba(0,0,0,0.45)

1.8 Typography
Font: Inter, system-ui, -apple-system, Segoe UI, Arial
Mono: ui-monospace, SFMono-Regular, Menlo, Consolas

Type scale:
- H1: 24/32, 700
- H2: 18/24, 650
- Body: 14/20, 450
- Small: 12/16, 450
- Micro: 11/14, 450

------------------------------------------------------------
2) Layout System (IDE)
2.1 Fixed regions
- Top Toolbar: 48px height
- Status Bar: 28px height
- Activity Bar: 64px width
- Sidebar: 280px width (resizable 240–360)
- Inspector: 360px width (resizable 320–420)
- Workspace: fills the rest

2.2 Grid rules inside Workspace
- Default: 12-col grid
- Standard padding: 20px
- Card gap: 16px
- Section gap: 24px

2.3 Page skeleton
Workspace pages MUST follow:
Header row (title + actions)
Main content (primary)
Secondary content (tabs or split)
Inspector always present (right panel)

------------------------------------------------------------
3) Core Components (Specs)
3.1 Buttons
Primary (brand):
- bg: --brand, text: white, radius: --r-sm
- hover: brighten 6%, active: --active
Secondary:
- bg: transparent, border: --border-2, text: --text
Ghost:
- bg: transparent, text: --text-2, hover: --hover
Danger:
- bg: transparent, border: rgba(239,68,68,0.5), text: --red
Confirm:
- bg: --green, text: --text-invert

Button sizes:
- sm: 28px height
- md: 34px height (default)
- lg: 40px height

3.2 Cards / Panels
Card:
- bg: --card, border: --border, radius: --r-md, padding: 16px
Panel:
- bg: --panel, border: --border, radius: --r-md
Section header inside card:
- small label uppercase, color --text-3, letterspacing 0.06em

3.3 Inputs
Text input / textarea:
- bg: rgba(255,255,255,0.03)
- border: --border
- focus ring: 0 0 0 3px --focus
- text: --text, placeholder: --text-3
Select:
- same as input, with chevron

3.4 Tabs
Tabs are always in-page (not route-level).
Tab style:
- inactive: --text-2
- active: underline 2px in --brand-2 + text --text
Tabs never reset user-entered values.

3.5 Badges
Tag badge:
- bg: rgba(124,58,237,0.15)
- border: rgba(124,58,237,0.35)
- text: --brand-2
Status badge:
- Candidate: bg rgba(255,255,255,0.06), text --text-2
- Active: bg rgba(34,197,94,0.15), text --green
- Warning: bg rgba(245,158,11,0.15), text --amber

3.6 Suggestion Box (AI Suggestions)
Container:
- bg: rgba(124,58,237,0.08)
- border: rgba(124,58,237,0.35)
- radius: --r-md
Card types:
- Contradiction alert: left border --amber
- Relationship gap: left border --cyan
- Enhancement: left border --brand
Actions:
- "Apply tweak" (secondary) and "Link character" (primary/brand)

3.7 Lists
List row:
- height: 40px, padding: 10px 12px
- hover: --hover
- selected: --selected + left 3px brand bar
Row metadata:
- name (bold), micro tags, optional update dot

3.8 Candidate Approval Header (must match screenshot intent)
Top-right sticky actions:
- Reject (danger outline)
- Confirm Candidate (green solid)
Visible on Candidates and Character detail when status=candidate.

------------------------------------------------------------
4) Page Blueprints (Key pages)
4.1 Characters (like your screenshot)
Layout:
- Sidebar: Candidates / Active Roster + counters
- Workspace header: "Character: {name}" + status chip + created time
- Main: Tabs [Profile | Relationships | Timeline | POV Insights]
- Profile Tab: 3-column card grid
  - Left card: Core Identity (name, role, archetype, physical, tags)
  - Middle card: Internal Mechanics (goal, fear, secret, trait sliders)
  - Right column: Metadata card + AI Suggestions panel (stack)
- Inspector: shows currently focused sub-entity (e.g., selected relationship/event)

4.2 Timeline
Two modes:
- "Editor" (list + inspector) and "Graph" (lane-based)
Lane-based timeline:
- top controls: zoom, snap, filter, layer selector
- lanes: Global + per character layer (toggle)
Event node:
- title, time, location, participants chips
Interactions:
- click -> inspector
- drag -> reorder/time adjust
- right click -> context menu (edit/open scene/simulate/delete)

4.3 Graph
Canvas center, Sidebar selects graph type, Inspector edits node/edge.
Graph layers:
- Scenes, Characters, Locations, World items
Edge inspector:
- type, causal strength, hidden truth flag

4.4 Writing Studio
- left: chapter list (tree)
- center: editor + inline AI tools
- right: context panel (events/characters/world notes)
Bottom: scene-linked timeline snippet + involved entities.

4.5 Workbench
- console log timeline (runs)
- prompt runner
- failure analysis (P0/P1)
- retry pipeline with preserved context

------------------------------------------------------------
5) Interaction Laws (Global)
- Selection sync: click anywhere sets global selection.
- No page “blank”: empty state always includes 2 buttons:
  (Create) + (Generate with AI)
- Confirm gating: candidate entities never used in generation until confirmed.
- Update glow: if ui_metadata.is_new_update=true
  - sidebar item shows ✨
  - list row shows amber glow (bg --update-glow + left border amber)
  - on open -> auto-clear flag (immediate visual removal)
- Undo/redo: required for edits to character/timeline/world/writing.

------------------------------------------------------------
6) Implementation Constraints (for dev)
- Keep tokens in one place (index.css).
- Components use tokens only.
- Pages compose components; no page-specific colors.
- Add data-testid for all interactive elements for Playwright.

Required test ids (minimum):
activity-workbench
activity-characters
activity-timeline
activity-graph
activity-world
activity-writing
activity-simulation
activity-consistency
activity-publish
activity-insights
btn-confirm-candidate
btn-reject-candidate
tabs-profile / tabs-relationships / tabs-timeline / tabs-pov
timeline-add-event
graph-add-node
writing-generate-scene
workbench-run-prompt

------------------------------------------------------------
7) Done Criteria (Visual)
- All pages share identical spacing, typography, cards.
- Sidebar/Inspector feel native and consistent.
- Characters page matches the screenshot vibe:
  dark, calm, structured, with purple AI suggestion panels and clear confirm/reject.