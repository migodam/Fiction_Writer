# Narrative IDE Test Plan

Test Framework: Playwright  
Selectors: see TEST_SELECTORS.txt

---

# P0 BLOCKERS

These tests must pass before any release.

## P0-1 Application Launch

- App window opens
- Layout elements visible

Check:

top-toolbar  
activity-bar  
sidebar  
workspace  
inspector  
status-bar

---

## P0-2 Activity Navigation

Test all Activity Bar buttons.

Steps:

click activity-btn-characters  
assert character-list visible

click activity-btn-timeline  
assert timeline-canvas visible

click activity-btn-writing  
assert writing-editor visible

repeat for all activities.

---

## P0-3 Sidebar Switching

Switch sidebar sections inside Timeline.

events → locations → chapters → branches

Assertions:

workspace remains timeline  
no blank page  
inspector remains visible

---

## P0-4 Character Creation

Steps:

click new-character-btn  
fill character-name-input  
fill character-background-input  
click inspector-save

Assertions:

toast Saved  
character-card appears

---

## P0-5 Candidate Confirmation

Steps:

open characters candidates  
click candidate-confirm-btn

Assertions:

candidate removed from queue  
character added to roster

---

## P0-6 Timeline Event Creation

Steps:

click add-event-btn  
fill event-title-input  
fill event-summary-input  
click inspector-save

Assertions:

timeline-node appears

---

## P0-7 Timeline Drag Reorder

Steps:

drag timeline-node-A after timeline-node-B

Assertions:

visual order updated  
refresh → order persists

---

## P0-8 Writing Autosave

Steps:

open writing studio  
type text into writing-editor

Assertions:

status shows Saving → Saved  
refresh → text remains

---

## P0-9 Timeline → Writing Link

Steps:

right click event  
select open scene

Assertions:

navigate to writing studio  
correct scene visible

---

# P1 CORE FEATURES

## P1-1 Graph Layout Persistence

Steps:

click graph-auto-layout-btn  
drag graph-node  
refresh

Assertions:

position persisted

---

## P1-2 Graph Reset Layout

Steps:

click graph-reset-layout-btn

Assertions:

nodes return to baseline

---

## P1-3 World Container Creation

Steps:

click create-container-btn  
select type  
enter container-name-input

Assertions:

world-container appears

---

## P1-4 World Item Creation

Steps:

click add-world-item-btn  
fill world-item-name-input  
fill description  
add dynamic-field

Assertions:

item saved

---

## P1-5 Consistency Run

Steps:

click consistency-run-check

Assertions:

issue list visible  
no crash

---

## P1-6 Workbench AI Run

Steps:

click run-prompt-btn

Assertions:

agent-console logs appear

---

## P1-7 Publish Preview

Steps:

open publish-preview

Assertions:

preview rendered

---

## P1-8 Insights Dashboard

Assertions:

insight-wordcount visible  
insight-character-usage visible

---

# P2 ADVANCED UX

## P2-1 Timeline Branch Drag

drag event across branches

---

## P2-2 Context Panel Insert

insert character reference  
insert event reference

---

## P2-3 Delete Confirm Modal

delete character  
cancel → still exists  
confirm → removed

---

## P2-4 Keyboard Shortcuts

Ctrl+F → search focus  
Ctrl+S → save

---

# P3 OPTIONAL

- Simulation scenarios
- Beta reader comparison
- Export EPUB/PDF

---