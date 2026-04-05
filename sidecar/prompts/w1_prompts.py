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
