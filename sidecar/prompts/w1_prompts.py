"""W1 Import Workflow prompt templates.

All templates use Python .format() substitution. Curly braces that are part of
JSON examples are escaped as double braces {{}}.
"""

W1_EXTRACT_CHARACTERS: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to extract character information from this text chunk.

## Entity Registry (all characters identified so far)
{entity_registry_summary}

This registry contains canonical names and all known aliases. Before creating a new character entry,
check carefully whether the character already exists under a different name or alias.

## Text Chunk
{chunk_content}

## Instructions
Extract all characters mentioned in this chunk. For each character:
1. Check if they already exist in the Entity Registry by any alias or name variant
2. If they exist: output only new aliases or notes to add — do NOT repeat existing information
3. If they are new: create a full entry

Output format — respond with valid JSON only, no other text:
{{
  "existing_character_updates": [
    {{
      "canonical_id": "<id from registry>",
      "new_aliases": ["<alias if newly found>"],
      "new_notes": ["<observation about this character in this chunk>"]
    }}
  ],
  "new_characters": [
    {{
      "canonical_name": "<most formal or complete name>",
      "aliases": ["<all other names seen in this chunk>"],
      "notes": ["<physical description, role, relationships, traits seen here>"],
      "confidence": <0.6–1.0, lower if identity is uncertain>
    }}
  ]
}}

If no characters appear in this chunk, output: {{"existing_character_updates": [], "new_characters": []}}
"""

W1_EXTRACT_EVENTS: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to extract timeline events from this text chunk.
Character extraction has already been completed. Use the registry below for all character references.

## Entity Registry (use canonical_id values for all character references)
{entity_registry_summary}

## Text Chunk
{chunk_content}

## Instructions
Extract all significant plot events from this chunk. An event is a moment that:
- Changes the state of the world, a relationship, or a character's situation
- Would need to appear on a story timeline
- Is not purely descriptive or atmospheric

For each event, identify all participating characters by their canonical_id.

Output format — respond with valid JSON only, no other text:
{{
  "events": [
    {{
      "title": "<short descriptive title>",
      "description": "<one to two sentence summary>",
      "character_ids": ["<canonical_id>"],
      "location_hint": "<location name if mentioned, null if not>",
      "temporal_hint": "<any time reference in the text, null if none>",
      "chunk_position": "<early|middle|late — where in the chunk this occurs>",
      "confidence": <0.6–1.0>
    }}
  ]
}}

If no significant events occur in this chunk, output: {{"events": []}}
"""

W1_EXTRACT_WORLD: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to identify world-building elements: locations, organizations, objects, concepts, and rules.

## Already Known World Entries
{known_world_entries}

## Text Chunk
{chunk_content}

## Instructions
Identify world-building elements that are NOT already in the known entries list.
Focus on: named locations, named organizations or factions, significant named objects,
explicit world rules or magic system elements, cultural terms requiring explanation.

Output format — respond with valid JSON only, no other text:
{{
  "world_mentions": [
    {{
      "name": "<name as it appears in text>",
      "category": "<location|organization|object|concept|rule>",
      "description": "<one sentence from context>",
      "confidence": <0.6–1.0>
    }}
  ]
}}

If no new world elements appear, output: {{"world_mentions": []}}
"""

W1_EXTRACT_CHARACTERS_DEEP: str = """
You are DeepSeek V4 Pro acting as the W1 Import Character Compiler for a long-form novel.
You are processing chunk {chunk_id} of {total_chunks}. Your output feeds a reducer, not the user-facing canon.
Extract compact, reviewable character-card evidence while protecting the project from duplicate people,
wrong cast grouping, translated aliases, and bloated biographies.

## Project Digest Input Placeholders
The Text Chunk below is a packed compiler window. It may include multiple complete chapters and it begins
with PROJECT_STRUCTURE_DIGEST and PREVIOUS_VALIDATION_SUMMARY. Treat those sections as authoritative project
context, not story prose. They may include {{project_digest}}, {{project_character_digest}},
{{project_group_digest}}, and {{project_alias_digest}} style records.

## Entity Registry
{entity_registry_summary}

## Packed Text Window
{chunk_content}

## LANGUAGE RULE
All prose text fields MUST use the dominant language of the source text chunk.
- Do NOT translate Chinese names, sect titles, honorifics, or epithets into English.
- Do NOT mix English summaries into Chinese source chunks or Chinese summaries into English chunks.
- Preserve canonical surface forms exactly as the source writes them unless the registry already has a stronger canonical name.

## IDENTITY AND ALIAS RECONCILIATION
Before creating a new character, exhaustively check every registry entry for:
- exact canonical name matches
- aliases, nicknames, childhood names, courtesy names, translated names, romanizations, and title variants
- role or kinship epithets such as 三叔, 韩父, 韩母, 小妹, 墨大夫, 厉师兄
- sect ranks, professional titles, cultivation titles, honorifics, and enemy labels
- nearby relationship evidence that proves two surface forms refer to the same person

If a surface form can be reconciled to an existing character, put it in existing_character_updates.
Only create a new character when the chunk gives enough evidence that the person is distinct.
If uncertain, update the closest existing candidate with an open question instead of creating a duplicate.
Never create separate characters for translated aliases or title-only references to an already-known person.

## CONFIDENCE CALIBRATION
- 0.9–1.0: Named character with dialogue or direct action in this chunk
- 0.75–0.89: Named character mentioned in passing with context
- 0.6–0.74: Unnamed role (e.g. "an elder", "a servant") — use the role as canonical_name
- Below 0.6: Do not output this character

## STORY FUNCTION CLASSIFICATION
Every new character and every importance update MUST include story_function using exactly one of:
- protagonist: the main POV/central destiny driver
- mentor: teacher, guide, patron, trainer, elder who materially shapes the protagonist
- antagonist: active opposing force, coercer, villain, hostile rival, or hidden threat
- ally: helper, friend, family supporter, faction partner, rescuer, or loyal companion
- minor: background, one-scene, unnamed, utility, or low-recurrence figure

Do not confuse story_function with importance. A mentor can be major or supporting; an antagonist can be major
or minor. Use evidence from the chunk plus registry recurrence signals.

## IMPORTANCE AND GROUPKEY CALIBRATION
Use exactly one importance value: core | major | supporting | minor.
- core: protagonist or central POV character whose choices drive the imported arc
- major: recurring named character with repeated agency, plot leverage, or a meaningful arc
- supporting: named character with a defined function but limited agency or limited scene count
- minor: single-scene, background, kinship-only, title-only, or utility character

Every new character SHOULD include groupKey using one of:
- main_characters: core protagonist or central recurring arc driver
- mentors_antagonists: mentors, coercers, villains, hostile masters, major rivals, hidden threats
- allies_family: family, companions, benefactors, faction allies, friends
- minor_characters: background, single-scene, utility, unnamed, or low-recurrence characters

Wrong group hints are expensive. Do not put parents, unnamed siblings, servants, shopkeepers, or one-scene elders
in main_characters just because they appear near the protagonist. If groupKey is uncertain, choose minor_characters
and add an open question.

## COMPACT CHARACTER CARD RULE
Import is not a biography-writing pass. Output only a compact character card draft:
- identity and aliases
- story_function and groupKey
- source-grounded role_in_story
- one concise summary that can replace or improve the existing card, not append a biography
- up to 3 grounded traits/tags
- open questions only when identity, role, or motivation is uncertain

Do NOT invent deep psychology. Do NOT fill goals, fears, secrets, speech style, arc, or full background unless
the source text explicitly states them and the field is requested. Those belong to a later enrichment workflow.
Prefer empty strings and empty arrays over unsupported inference.

## LENGTH LIMITS (strictly enforced — truncate before output)
- summary: ≤ 1 sentence, ≤ 25 words
- role_in_story: ≤ 12 words
- physical_description: ≤ 1 sentence, ≤ 25 words
- notes: ≤ 3 bullets total
- grounded_tags: ≤ 3 tags total
- open_questions: ≤ 2 questions total

## ANTI-SUMMARY-BLOAT RULES
- Do not restate old registry summaries unless the chunk adds a new, stronger fact.
- Do not append long life histories across chunks.
- For an existing character, provide only the delta from this chunk.
- For a repeated fact, output no summary_update.
- If a prior English summary exists but the source chunk is Chinese, do not repeat or translate it.
- Avoid generic traits such as "brave", "kind", or "mysterious" unless the chunk directly proves them.

## Instructions
Extract named characters from this packed window using the alias-first rule above.
- Reuse an existing character (via existing_character_updates) whenever possible
- Create a new character only when identity is genuinely distinct
- Prefer empty strings or empty arrays over unsupported inference
- Keep every field concise, factual, and source-grounded
- Obey LENGTH LIMITS — do not write novel-length descriptions
- Include important missing major characters even if this chunk only strengthens their role; use existing updates
- Search across every SOURCE_CHAPTERS section before deciding a major character is absent
- Use PROJECT_STRUCTURE_DIGEST groups/tags/relationships to avoid putting family/background figures into main_characters
- Use PREVIOUS_VALIDATION_SUMMARY to correct prior duplicate, missing-major, or suspicious-group mistakes
- Mention the supporting chapter evidence in notes/open_questions when groupKey is uncertain

Output valid JSON only:
{{
  "existing_character_updates": [
    {{
      "canonical_id": "<existing registry id>",
      "new_aliases": ["<new alias found in this chunk>"],
      "new_notes": ["<brief evidence-grounded observation from this chunk>"],
      "summary_update": "<new short summary detail>",
      "role_in_story_update": "<directly supported role detail>",
      "physical_description_update": "<new appearance detail>",
      "new_personality_traits": ["<grounded tag or trait>"],
      "open_questions": ["<question for later review>"],
      "importance_update": "<core|major|supporting|minor>",
      "story_function_update": "<protagonist|mentor|antagonist|ally|minor>",
      "groupKey_update": "<main_characters|mentors_antagonists|allies_family|minor_characters>",
      "alias_reconciliation_rationale": "<brief reason this update belongs to the existing character>",
      "confidence": <0.6-1.0>
    }}
  ],
  "new_characters": [
    {{
      "canonical_name": "<best canonical name>",
      "aliases": ["<alternate names in this chunk>"],
      "summary": "<one sentence identity card>",
      "background": "",
      "role_in_story": "<directly supported narrative role>",
      "physical_description": "<appearance cues if present>",
      "personality_traits": ["<grounded tag or trait>"],
      "goals": [],
      "fears": [],
      "secrets": [],
      "speech_style": "",
      "arc_notes": "",
      "importance": "<core|major|supporting|minor>",
      "story_function": "<protagonist|mentor|antagonist|ally|minor>",
      "groupKey": "<main_characters|mentors_antagonists|allies_family|minor_characters>",
      "notes": ["<evidence-grounded note>"],
      "open_questions": ["<question for later enrichment>"],
      "alias_reconciliation_rationale": "<why this is not an existing character>",
      "confidence": <0.6-1.0>
    }}
  ]
}}

If there are no characters, return: {{"existing_character_updates": [], "new_characters": []}}
"""

W1_EXTRACT_EVENTS_DEEP: str = """
You are DeepSeek V4 Pro acting as the W1 Import Timeline Scout for a long-form novel.
You are processing chunk {chunk_id} of {total_chunks}. Your output feeds Timeline Architect,
which needs canonical-vs-scene-beat decisions, dedupe keys, branch hints, and causal topology.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## LANGUAGE RULE
All text fields (title, description, stakes) MUST be written in the same language as the source text chunk. Do NOT translate.

## PROJECT DIGEST PLACEHOLDERS
The Text Chunk below is a packed compiler window. It may include multiple complete chapters and it begins
with PROJECT_STRUCTURE_DIGEST and PREVIOUS_VALIDATION_SUMMARY. Treat those sections as project context, not
story events. The window may include {{project_digest}}, {{existing_event_digest}}, {{timeline_branch_digest}},
and {{chapter_digest}} style records. Use that context to avoid re-emitting accepted/candidate events.

## TEMPORAL ANCHOR RULE
Every event MUST include the most specific time reference available: chapter number, arc stage, cultivation milestone, season, or relative marker like "three days later". Use this as temporal_hint. If no anchor exists, use "unknown" — never leave temporal_hint empty.

## CANONICAL VS SCENE-BEAT DECISION
Every candidate MUST explicitly choose:
- timelineClass = canonical_event when the beat changes world state, relationship state, power status, faction alignment, major knowledge, survival stakes, or arc direction.
- timelineClass = scene_beat when it is travel, training repetition, conversation texture, atmosphere, minor tactical movement, repeated explanation, or a sub-beat inside a larger canonical event.

Only canonical_event candidates are expected to survive as timeline proposals. scene_beat candidates may be used
for merge recommendations or scene summaries. Do not promote every action to a canonical event.

## EVENT CLASS TAXONOMY
Every event MUST include eventClass using exactly one:
- inciting_choice
- journey_departure
- test_or_trial
- discovery
- training_breakthrough
- confrontation
- betrayal_or_reveal
- alliance_or_bond
- power_shift
- injury_or_death
- escape_or_pursuit
- faction_move
- scene_beat
- other

## DEDUPE AND MERGE RULE
Do NOT emit a canonical event that is semantically equivalent to one already in the Entity Registry
(same participants + same action + same consequence), even if wording differs.
For near duplicates inside this chunk, emit one stronger event and list the weaker beat in mergeCandidateTitles.
Every event MUST include dedupeKey: a short stable key made from normalized participants, action, consequence, and chapterRange.
Use PREVIOUS_VALIDATION_SUMMARY as a rolling reviewer: if it says a prior event should be merged/demoted, do not
recreate it as a fresh canonical event in this window.

## STRUCTURAL BEATS ONLY
Extract only major plot-turning events: breakthroughs, confrontations, deaths, revelations, alliance formations, betrayals, power shifts, key arrivals/departures. Do NOT extract travel, daily training, minor conversations, or scene descriptions that do not directly advance the main conflict or a character arc.

## DENSITY LIMIT
Output at most 3 canonical_event candidates per source chapter and at most 12 total events per packed window.
If more qualify, select the highest-impact events by story consequence, causal leverage, and branch topology value.
For a 100-chapter novel the total canonical event count should be 20–40, not hundreds.

## CONFIDENCE FLOOR
Only output events with confidence ≥ 0.75. Skip anything below.

## Instructions
Extract only events that significantly advance the plot or mark a turning point.
- Prefer canonical character ids from the registry; fall back to character_names for unresolved references
- One event per distinct plot beat — do not split a single scene into multiple events
- Keep titles short and specific (max 6 words)
- Use arcId to group recurring lanes such as protagonist_origin, sect_entry, mentor_control, bottle_secret, cultivation_progress, faction_conflict, or antagonist_scheme
- timelineLaneHint should be a human-readable lane such as Main Arc, Mentor Threat, Sect Conflict, Bottle Mystery, Family Origin, or Rival Ally
- causalPredecessorHints should name earlier events/titles this event depends on, if visible in the chunk or registry
- forkMergeHint must be one of root, fork, merge, parallel, callback, unknown
- chapterRange must be an object with start and end strings, not a prose-only field
- importanceScore must be 1-100; 80+ means canonical story-turning event, 50-79 means useful branch event, below 50 should normally be scene_beat
- For multi-chapter windows, chapterRange must point to the specific source chapter(s), not the whole packed window
- Use arcId/timelineLaneHint consistently across chapters so Timeline Architect can build multi-lane topology

Output valid JSON only:
{{
  "events": [
    {{
      "title": "<short event title>",
      "description": "<1-2 sentence summary>",
      "eventClass": "<inciting_choice|journey_departure|test_or_trial|discovery|training_breakthrough|confrontation|betrayal_or_reveal|alliance_or_bond|power_shift|injury_or_death|escape_or_pursuit|faction_move|scene_beat|other>",
      "timelineClass": "<canonical_event|scene_beat>",
      "arcId": "<stable snake_case arc id>",
      "timelineLaneHint": "<branch/lane hint>",
      "causalPredecessorHints": ["<earlier event title or empty>"],
      "forkMergeHint": "<root|fork|merge|parallel|callback|unknown>",
      "dedupeKey": "<participants::action::consequence::chapterRange>",
      "chapterRange": {{"start": "<chapter/segment start>", "end": "<chapter/segment end>"}},
      "importanceScore": <1-100>,
      "character_ids": ["<canonical_id if known>"],
      "character_names": ["<name if not yet resolved>"],
      "location_hint": "<location or empty string>",
      "temporal_hint": "<chapter/arc/time anchor — required>",
      "chunk_position": "<early|middle|late>",
      "stakes": "<why this matters to the story>",
      "mergeCandidateTitles": ["<near-duplicate title from this chunk>"],
      "confidence": <0.6-1.0>
    }}
  ]
}}

If no significant events occur, return: {{"events": []}}
"""

W1_EXTRACT_WORLD_DEEP: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to perform deep world extraction from this text chunk.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## Instructions
Extract named world-building elements and explicit world rules grounded in this chunk.
- Focus on locations, organizations, objects, concepts, cultures, and rules
- Prefer one entry per distinct mention
- Keep descriptions concise and text-grounded

Output valid JSON only:
{{
  "world_mentions": [
    {{
      "name": "<surface form from text>",
      "category": "<location|organization|object|concept|rule|culture>",
      "description": "<one sentence description>",
      "container_hint": "<locations|organizations|items|lore|rules or empty string>",
      "attributes": [
        {{"key": "<attribute name>", "value": "<attribute value>"}}
      ],
      "confidence": <0.6-1.0>
    }}
  ]
}}

If no world elements are found, return: {{"world_mentions": []}}
"""

W1_EXTRACT_RELATIONSHIPS_CHUNK: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to extract relationship evidence that helps cross-validate character identity,
role grouping, aliases, and timeline topology.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## Instructions
Extract relationship signals between characters mentioned in this chunk.
- Use character names, not ids, in this output
- Include only relationships supported by explicit interaction, dialogue, internal thought, or narration
- Evidence should be short, direct snippets or paraphrases from this chunk
- Include aliasEvidence when a kinship term, title, or epithet proves identity
- Include topologyRole so Timeline Architect can distinguish mentor pressure, antagonist conflict, ally support, and family background
- Flag contradictions when the chunk appears to use one alias for multiple people or multiple aliases for one person
- Use PROJECT_STRUCTURE_DIGEST and PREVIOUS_VALIDATION_SUMMARY inside the packed window to catch wrong character groups
  and alias collisions before they become proposals

Output valid JSON only:
{{
  "relationships": [
    {{
      "source_character_name": "<character name>",
      "target_character_name": "<character name>",
      "type": "<short relationship label>",
      "description": "<one sentence explanation>",
      "category": "<alliance|conflict|family|romance|political|mentor|rivalry|other>",
      "directionality": "<bidirectional|source_to_target|target_to_source>",
      "status": "<active|strained|broken|unknown>",
      "topologyRole": "<mentor_pressure|antagonist_conflict|ally_support|family_context|rival_pressure|faction_link|unknown>",
      "aliasEvidence": ["<title/kinship/epithet evidence linking identities>"],
      "contradictionHint": "<possible alias/group contradiction or empty string>",
      "evidence": ["<evidence 1>", "<evidence 2>"],
      "confidence": <0.6-1.0>
    }}
  ]
}}

If no relationship evidence appears, return: {{"relationships": []}}
"""

W1_EXTRACT_SCENE_SUMMARIES: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to identify scene boundaries and summarize scenes in this text chunk so cross-validation
can distinguish true timeline events from scene beats.

## Entity Registry
{entity_registry_summary}

## Existing Chapter Hint
{chapter_hint}

## Text Chunk
{chunk_content}

## Instructions
Infer one or more scene units from the chunk.
- Keep scenes in reading order
- If there is no clear chapter title, infer a practical chapter hint
- Use concise summaries grounded in the text
- If the packed window contains multiple SOURCE_CHAPTERS sections, keep scene chapterRange tied to the exact chapter
- Mark repetitive practice/travel/conversation as sceneBeatRefs unless it changes causal story state
- Include canonicalEventRefs for scene-level evidence that supports a canonical event title
- Include sceneBeatRefs for important but non-canonical beats that should merge into a larger event
- Include timelineLaneHint and arcId when the scene clearly belongs to a branch/lane
- Use chapterRange to preserve timeline-ready placement

Output valid JSON only:
{{
  "chapter_hint": "<chapter title or practical fallback label>",
  "scenes": [
    {{
      "title": "<scene title>",
      "summary": "<1-2 sentence summary>",
      "location_hint": "<location or empty string>",
      "time_hint": "<time clue or empty string>",
      "character_names": ["<characters in the scene>"],
      "arcId": "<stable snake_case arc id or empty string>",
      "timelineLaneHint": "<timeline lane hint or empty string>",
      "chapterRange": {{"start": "<chapter/segment start>", "end": "<chapter/segment end>"}},
      "canonicalEventRefs": ["<canonical event title supported by this scene>"],
      "sceneBeatRefs": ["<scene beat that should not become a standalone canonical event>"],
      "purpose": "<what the scene accomplishes>",
      "confidence": <0.6-1.0>
    }}
  ]
}}

If no clear scenes can be isolated, return:
{{"chapter_hint": "{chapter_hint}", "scenes": []}}
"""

W1_CROSS_VALIDATE_IMPORT: str = """
You are DeepSeek V4 Pro acting as the W1 Import Cross-Validation Reviewer.
You receive compact artifacts from character, event, relationship, scene, reducer, and timeline passes.
Your job is not to create canon. Your job is to identify merge risks and missing high-value entities before
Workbench proposals are accepted.

## Project Digest Placeholders
- {{project_digest}}: existing project characters, groups, aliases, timeline branches, and accepted events
- {{character_candidates_json}}: character card candidates and existing updates
- {{event_candidates_json}}: timeline event candidates with eventClass, timelineClass, dedupeKey, arcId, and chapterRange
- {{relationship_candidates_json}}: relationship evidence and alias evidence
- {{scene_candidates_json}}: scene summaries with canonicalEventRefs and sceneBeatRefs
- {{reducer_artifact_json}}: deterministic reducer matches and warnings
- {{timeline_architecture_json}}: branch assignments, discarded duplicates, and density warnings

## Review Rules
- duplicate_characters: flag likely same-person records caused by aliases, translations, titles, kinship terms, or romanization drift.
- duplicate_events: flag semantically repeated events even if titles differ or chunks overlap.
- missing_major_characters: flag characters who appear central in events/relationships/scenes but are absent, minor, or misclassified.
- suspicious_groups: flag wrong groupKey or importance hints, especially minor family/background figures in main_characters or mentors/antagonists hidden as minor.
- contradictory_aliases: flag one alias assigned to multiple people or mutually inconsistent names for one canonical person.
- event_merge_recommendations: recommend canonical event merges, scene-beat demotions, branch/lane changes, and causal predecessor corrections.
- Use conservative evidence labels. If uncertain, say why and keep confidence below 0.75.
- Keep all rationale in the source language when tied to source text; field names stay English.

Output valid JSON only:
{{
  "duplicate_characters": [
    {{
      "candidate_ids": ["<character id or candidate name>"],
      "canonical_preference": "<preferred id/name>",
      "reason": "<why they likely duplicate>",
      "evidence": ["<alias/title/relationship clue>"],
      "confidence": <0.0-1.0>
    }}
  ],
  "duplicate_events": [
    {{
      "event_ids": ["<event id/title>"],
      "dedupeKey": "<shared or recommended dedupe key>",
      "canonical_preference": "<preferred event id/title>",
      "reason": "<same participants/action/consequence/chapterRange>",
      "confidence": <0.0-1.0>
    }}
  ],
  "missing_major_characters": [
    {{
      "name_or_alias": "<missing or underclassified character>",
      "observed_role": "<protagonist|mentor|antagonist|ally|minor>",
      "suggested_importance": "<core|major|supporting|minor>",
      "suggested_groupKey": "<main_characters|mentors_antagonists|allies_family|minor_characters>",
      "evidence": ["<event/relationship/scene clue>"],
      "confidence": <0.0-1.0>
    }}
  ],
  "suspicious_groups": [
    {{
      "character_id_or_name": "<character id/name>",
      "current_groupKey": "<current group>",
      "suggested_groupKey": "<suggested group>",
      "reason": "<why group or importance looks wrong>",
      "confidence": <0.0-1.0>
    }}
  ],
  "contradictory_aliases": [
    {{
      "alias": "<alias/title/epithet>",
      "conflicting_ids_or_names": ["<id/name>"],
      "reason": "<contradiction>",
      "confidence": <0.0-1.0>
    }}
  ],
  "event_merge_recommendations": [
    {{
      "primary_event_id_or_title": "<event to keep>",
      "merge_event_ids_or_titles": ["<events to merge/demote>"],
      "recommended_timelineClass": "<canonical_event|scene_beat>",
      "recommended_arcId": "<arc id>",
      "recommended_timelineLaneHint": "<lane hint>",
      "causalPredecessorHints": ["<predecessor title>"],
      "reason": "<merge/topology rationale>",
      "confidence": <0.0-1.0>
    }}
  ],
  "warnings": ["<review-level warning>"]
}}
"""

W1_SYNTHESIZE_RELATIONSHIPS: str = """
You are consolidating raw relationship candidates from a novel import pipeline.

## Entity Registry JSON
{entity_registry_json}

## Relationship Candidates JSON
{relationship_candidates_json}

## Instructions
Merge duplicate relationship candidates into canonical relationship entities.
- `source_id` and `target_id` MUST be canonical character IDs from the Entity Registry. If a candidate uses a name that does not map to any registry ID, skip that candidate.
- Include relationships supported by at least 1 piece of evidence
- Deduplicate near-identical evidence; prefer the strongest supported interpretation
- Keep descriptions concise (source language only)

## Relationship Type Taxonomy
Use EXACTLY one of these categories:
- `family` — blood or adoptive family (parent/child/sibling/spouse)
- `romantic` — romantic interest, lovers, betrothed
- `rivalry` — competing peers, enemies of equal standing
- `mentor_disciple` — teacher/master → student/apprentice (cultivation context: sect hierarchy)
- `sworn_brothers` — sworn bond, blood oath, kuòlaoméng (结拜)
- `political` — alliance, submission, lord/vassal, faction membership
- `conflict` — active hostility without rivalry framing (assassination, war, vendetta)
- `unknown` — insufficient evidence to categorise

Output valid JSON only:
{{
  "relationships": [
    {{
      "source_id": "<canonical character id from registry>",
      "target_id": "<canonical character id from registry>",
      "type": "<short label in source language>",
      "description": "<one sentence summary>",
      "category": "<family|romantic|rivalry|mentor_disciple|sworn_brothers|political|conflict|unknown>",
      "directionality": "<bidirectional|source_to_target|target_to_source>",
      "status": "<active|strained|broken|unknown>",
      "strength": <0.1-1.0>,
      "evidence": ["<evidence 1>", "<evidence 2>"],
      "importConfidence": <0.6-1.0>
    }}
  ]
}}

If no relationship has enough support, return: {{"relationships": []}}
"""

W1_CLASSIFY_CHARACTER_TAGS: str = """
You are classifying imported characters into high-value editorial tags.

## Characters JSON
{characters_json}

## Instructions
Group characters into a compact, useful tag system for a fiction project.
- Prefer 3-8 tags total unless the cast is extremely large
- Tags should help navigation and editorial reasoning, not restate names
- Every tag must include character_ids
- Importance updates MUST use exactly one of: core | major | supporting | minor
  - core: protagonist or POV character present throughout
  - major: recurring named character with significant arc
  - supporting: named character with defined role but limited scenes
  - minor: named but single-scene or purely functional

Output valid JSON only:
{{
  "tags": [
    {{
      "name": "<tag name>",
      "description": "<what this tag means>",
      "color": "<hex color like #f59e0b>",
      "character_ids": ["<canonical id>"]
    }}
  ],
  "character_importance_updates": [
    {{
      "character_id": "<canonical id>",
      "importance": "<core|major|supporting|minor>",
      "rationale": "<brief reason>"
    }}
  ]
}}

If no useful tags can be inferred, return:
{{"tags": [], "character_importance_updates": []}}
"""

W1_INFER_WORLD_SETTINGS: str = """
You are inferring project-wide world settings from imported fiction text.

## Text Sample
{text_sample}

## Instructions
Infer project-level settings and structural suggestions from the sample.
- Keep every field concise and specific
- Timeline branches should reflect major narrative lanes, not every event
- World containers should reflect practical project organization

Output valid JSON only:
{{
  "world_settings": {{
    "projectType": "<genre or project type>",
    "narrativePacing": "<pacing summary>",
    "languageStyle": "<style summary>",
    "narrativePerspective": "<perspective summary>",
    "lengthStrategy": "<length or expansion strategy>",
    "worldRulesSummary": "<world rules summary>"
  }},
  "inferred_timeline_branches": [
    {{
      "name": "<branch name>",
      "description": "<branch purpose>",
      "mode": "<root|forked|independent>",
      "parent_branch_name": "<parent branch name or empty string>",
      "color": "<hex color>",
      "confidence": <0.6-1.0>
    }}
  ],
  "suggested_world_containers": [
    {{
      "name": "<container name>",
      "type": "<notebook|graph|timeline|map>",
      "is_default": <true|false>,
      "description": "<why this container exists>",
      "confidence": <0.6-1.0>
    }}
  ]
}}

If uncertain, still return the best grounded guess with empty lists where needed.
"""
