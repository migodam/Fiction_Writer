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
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to extract REVIEWABLE CHARACTER CARD DRAFTS from this text chunk.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## LANGUAGE RULE
All text fields MUST be written in the same language as the source text chunk. Do NOT translate or add parallel translations.

## ALIAS-FIRST RULE
Before creating any new character, check ALL existing registry entries for any name, alias, title, or honorific match. In cultivation novels a single character may appear under: childhood name, courtesy name, cultivation title (e.g. 炼气期弟子), sect rank, given name + surname, and nicknames — these ALL refer to ONE entity. Only create a new character if the reference genuinely cannot be reconciled with any registry entry after exhaustive checking.

## CONFIDENCE CALIBRATION
- 0.9–1.0: Named character with dialogue or direct action in this chunk
- 0.75–0.89: Named character mentioned in passing with context
- 0.6–0.74: Unnamed role (e.g. "an elder", "a servant") — use the role as canonical_name
- Below 0.6: Do not output this character

## CHARACTER CARD RULE
Import is not a biography-writing pass. Output only a compact character card draft:
- identity and aliases
- story function or role if directly supported
- first evidence seen in this chunk
- up to 3 grounded tags/traits
- open questions when identity, role, or motivation is uncertain

Do NOT invent deep psychology. Do NOT fill goals, fears, secrets, speech style, arc, or full background unless the source text explicitly states them. Those belong to a later enrichment workflow.

## LENGTH LIMITS (strictly enforced — truncate before output)
- summary: ≤ 1 sentence, ≤ 25 words
- role_in_story: ≤ 12 words
- physical_description: ≤ 1 sentence, ≤ 25 words
- notes: ≤ 3 bullets total
- grounded_tags: ≤ 3 tags total
- open_questions: ≤ 2 questions total

## IMPORTANCE VALUES
Use exactly one of: core | major | supporting | minor
- core: protagonist or POV character present in >50% of chapters
- major: recurring named character with a significant arc
- supporting: named character with a defined role but limited scenes
- minor: named but single-scene or purely functional character

## Instructions
Extract named characters from this chunk using the alias-first rule above.
- Reuse an existing character (via existing_character_updates) whenever possible
- Create a new character only when identity is genuinely distinct
- Prefer empty strings or empty arrays over unsupported inference
- Keep every field concise, factual, and source-grounded
- Obey LENGTH LIMITS — do not write novel-length descriptions

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
      "notes": ["<evidence-grounded note>"],
      "open_questions": ["<question for later enrichment>"],
      "confidence": <0.6-1.0>
    }}
  ]
}}

If there are no characters, return: {{"existing_character_updates": [], "new_characters": []}}
"""

W1_EXTRACT_EVENTS_DEEP: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to perform deep event extraction from this text chunk.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## LANGUAGE RULE
All text fields (title, description, stakes) MUST be written in the same language as the source text chunk. Do NOT translate.

## TEMPORAL ANCHOR RULE
Every event MUST include the most specific time reference available: chapter number, arc stage, cultivation milestone, season, or relative marker like "three days later". Use this as temporal_hint. If no anchor exists, use "unknown" — never leave temporal_hint empty.

## DEDUP RULE
Do NOT emit an event that is semantically equivalent to one already in the Entity Registry (same participants + same action). If this chunk adds new detail to an existing registry event, skip it — updating existing events is not supported at this stage.

## STRUCTURAL BEATS ONLY
Extract only major plot-turning events: breakthroughs, confrontations, deaths, revelations, alliance formations, betrayals, power shifts, key arrivals/departures. Do NOT extract travel, daily training, minor conversations, or scene descriptions that do not directly advance the main conflict or a character arc.

## DENSITY LIMIT
Output at most 3 events per chunk. If more than 3 qualify, select the 3 highest-impact ones by confidence. For a 100-chapter novel the total event count should be 20–40, not hundreds.

## CONFIDENCE FLOOR
Only output events with confidence ≥ 0.75. Skip anything below.

## Instructions
Extract only events that significantly advance the plot or mark a turning point.
- Prefer canonical character ids from the registry; fall back to character_names for unresolved references
- One event per distinct plot beat — do not split a single scene into multiple events
- Keep titles short and specific (max 6 words)

Output valid JSON only:
{{
  "events": [
    {{
      "title": "<short event title>",
      "description": "<1-2 sentence summary>",
      "character_ids": ["<canonical_id if known>"],
      "character_names": ["<name if not yet resolved>"],
      "location_hint": "<location or empty string>",
      "temporal_hint": "<chapter/arc/time anchor — required>",
      "chunk_position": "<early|middle|late>",
      "stakes": "<why this matters to the story>",
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
Your job is to extract relationship evidence from this text chunk.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## Instructions
Extract relationship signals between characters mentioned in this chunk.
- Use character names, not ids, in this output
- Include only relationships supported by explicit interaction, dialogue, internal thought, or narration
- Evidence should be short, direct snippets or paraphrases from this chunk

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
      "evidence": ["<evidence 1>", "<evidence 2>"],
      "confidence": <0.6-1.0>
    }}
  ]
}}

If no relationship evidence appears, return: {{"relationships": []}}
"""

W1_EXTRACT_SCENE_SUMMARIES: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to identify scene boundaries and summarize scenes in this text chunk.

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
      "purpose": "<what the scene accomplishes>",
      "confidence": <0.6-1.0>
    }}
  ]
}}

If no clear scenes can be isolated, return:
{{"chapter_hint": "{chapter_hint}", "scenes": []}}
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
