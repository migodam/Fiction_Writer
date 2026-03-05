# UI Page Content Specification

This file defines the **minimum required UI content for every page** in the Narrative IDE.

The goal is to ensure that the application never shows empty placeholder pages.

Every module must contain meaningful UI components even before user data exists.

---

# Workbench

Main purpose:
AI orchestration and prompt execution.

Workspace must include:

Agent Console
- scrollable output log
- timestamped entries
- colored status (info/warning/error)

Prompt Input
- multiline prompt box
- "Run Prompt" button
- "Retry" button
- "Show Raw Output"

Prompt Library
- saved prompts
- insert prompt button

System Logs
- backend events
- AI pipeline logs

---

# Characters

Workspace layout:

Left Panel
Character List

Center
Character Editor

Right
Inspector

Default state must include:
- 3 sample character cards (placeholder data)

Character Editor fields:

Name
Aliases
Background
Traits
Goals
Fears
Secrets
Tags

Buttons:

Save
Generate Traits
Generate Backstory
Link Timeline

Relationships Section:

Graph of relationships
Buttons:
Add Relationship
Edit Relationship
Delete Relationship

---

# Timeline

Workspace layout:

Top Toolbar
Center Timeline Canvas
Right Inspector

Toolbar buttons:

Add Event
Create Chapter
Filter Events
Zoom
Switch View

Timeline must show sample events if project empty:

Event 1
"Protagonist Born"

Event 2
"Inciting Incident"

Event nodes must display:

Title
Time
Participants

Inspector fields:

Title
Time
Location
Participants
Summary
Consequences
Tags

Buttons:

Save
Delete
Open Scene
Simulate Impact

---

# Graph

Workspace:

Graph Canvas

Default nodes (if empty project):

Character Node
Event Node
Location Node

Edges:

participates
causes
conflicts

Controls:

Add Node
Add Edge
Auto Layout
Run Analysis

Inspector must show node details.

---

# World Model

Sidebar modules:

Notebooks
Maps
Organizations
Magic System
Technology
Lore

Workspace:

Item List
Item Editor

Item fields:

Name
Description
Tags
Custom Fields

Buttons:

Add Item
Generate Detail
Link To Character
Link To Event

Maps module:

Image canvas
Pin markers

---

# Writing Studio

Layout:

Left
Chapter List

Center
Editor

Right
Context Panel

Default state:

Chapter 1 placeholder

Editor toolbar:

Generate Scene
Rewrite
Continue
Improve Dialogue

Context panel:

Characters in scene
Timeline events
World notes

Buttons:

Insert Character
Insert Event
Insert Lore

---

# Simulation

Workspace:

Simulation Graph

Right Panel:

Tension Curve
Conflict Density
Character Arc

Buttons:

Run Simulation
Reset
Compare Runs

---

# Consistency

Workspace:

Issue Table

Columns:

Issue Type
Location
Severity
Fix Action

Buttons:

Run Check
Auto Fix
Ignore
Send To Workbench

---

# Beta Reader

Reader Profiles

Examples:

Casual Reader
Critic
Genre Fan

Outputs:

Reader Reactions
Confusion Points
Engagement Curve

Buttons:

Run Reader Simulation
Compare Readers

---

# Publish

Workspace:

Book Preview
Metadata Editor

Buttons:

Generate Blurb
Generate Cover
Export EPUB
Export PDF

---

# Insights

Charts:

Word Count
Character Usage
Pacing Graph
Scene Density

Buttons:

Generate Report
Analyze Arc
Compare Chapters