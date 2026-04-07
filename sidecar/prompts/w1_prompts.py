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
Your job is to perform deep character extraction from this text chunk.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## Instructions
Extract ALL named characters from this chunk, including minor and background characters.
- Reuse an existing character when the identity clearly matches the registry
- Create a new character entry for EVERY distinct named person, even those with brief mentions
- For ALL fields: fill with reasonable inference from context rather than leaving empty
  - If a trait/goal/fear is not stated explicitly, infer the most likely value from context
  - For minor characters (siblings, servants, rivals): use their role, name, and interactions to fill fields
- Use empty strings or empty arrays only when there is truly no basis for inference
- Keep every field concise and factual

Output valid JSON only:
{{
  "existing_character_updates": [
    {{
      "canonical_id": "<existing registry id>",
      "new_aliases": ["<new alias found in this chunk>"],
      "new_notes": ["<new observation from this chunk>"],
      "summary_update": "<new short summary detail>",
      "background_update": "<new background detail>",
      "role_in_story_update": "<new role detail>",
      "physical_description_update": "<new appearance detail>",
      "new_personality_traits": ["<trait>"],
      "new_goals": ["<goal>"],
      "new_fears": ["<fear>"],
      "new_secrets": ["<secret>"],
      "speech_style_update": "<speech pattern or voice detail>",
      "arc_notes_update": "<arc or trajectory note>",
      "importance_update": "<lead|supporting|minor|background>",
      "confidence": <0.6-1.0>
    }}
  ],
  "new_characters": [
    {{
      "canonical_name": "<best canonical name>",
      "aliases": ["<alternate names in this chunk>"],
      "summary": "<1-2 sentence summary>",
      "background": "<backstory or social position known from this chunk>",
      "role_in_story": "<narrative role>",
      "physical_description": "<appearance cues if present>",
      "personality_traits": ["<trait>"],
      "goals": ["<goal>"],
      "fears": ["<fear>"],
      "secrets": ["<secret>"],
      "speech_style": "<voice or dialogue pattern>",
      "arc_notes": "<arc direction or pressure>",
      "importance": "<lead|supporting|minor|background>",
      "notes": ["<other grounded notes>"],
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

## Instructions
Extract significant events that matter to the story timeline.
- Prefer canonical character ids when the registry is sufficient
- If a character appears in the chunk but is not yet in the registry, include them in character_names
- Keep descriptions grounded in the text

Output valid JSON only:
{{
  "events": [
    {{
      "title": "<short event title>",
      "description": "<1-2 sentence summary>",
      "character_ids": ["<canonical_id if known>"],
      "character_names": ["<name if not yet resolved>"],
      "location_hint": "<location or empty string>",
      "temporal_hint": "<time clue or empty string>",
      "chunk_position": "<early|middle|late>",
      "stakes": "<why this matters>",
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
- Use canonical character ids only in the final output
- Include all relationships supported by at least 1 piece of evidence
- Deduplicate near-identical evidence and prefer the strongest supported interpretation
- Keep descriptions concise and grounded in the evidence

Output valid JSON only:
{{
  "relationships": [
    {{
      "source_id": "<canonical character id>",
      "target_id": "<canonical character id>",
      "type": "<relationship label>",
      "description": "<one sentence summary>",
      "category": "<alliance|conflict|family|romance|political|mentor|rivalry|other>",
      "directionality": "<bidirectional|source_to_target|target_to_source>",
      "status": "<active|strained|broken|unknown>",
      "strength": <1-10>,
      "evidence": ["<evidence 1>", "<evidence 2>"],
      "confidence": <0.6-1.0>
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
- Importance updates should use lead, supporting, minor, or background

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
      "importance": "<lead|supporting|minor|background>",
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
