"""W2 Manuscript Sync prompt templates.

All templates use Python .format() substitution. JSON braces in examples are
escaped as double braces {{}}.
"""

W2_EXTRACT_FROM_CHAPTER: str = """
You are analyzing a manuscript chapter to identify entities and events for project synchronization.
Your output will be compared against the existing structured project data to find discrepancies.

## Existing Project Data Summary
### Characters
{characters_summary}

### Timeline Events (this chapter)
{timeline_events_summary}

### World Entries
{world_entries_summary}

## Chapter Content
{chapter_content}

## Instructions
Extract all entities and events mentioned in this chapter.
For each item, note whether it matches, contradicts, or extends the existing project data.

Output format — respond with valid JSON only, no other text:
{{
  "characters_found": [
    {{
      "name_in_text": "<name as written>",
      "matched_canonical_id": "<id if matches existing character, null if new>",
      "attributes_mentioned": {{"key": "value"}},
      "conflicts_with_project": "<description of conflict if any, null if none>"
    }}
  ],
  "events_found": [
    {{
      "title": "<short title>",
      "character_names": ["<name as written>"],
      "matched_event_id": "<id if matches existing event, null if new>",
      "conflicts_with_project": "<null if consistent>"
    }}
  ],
  "world_mentions": [
    {{
      "name": "<name>",
      "category": "<location|organization|object|concept>",
      "matched_entry_id": "<id if exists, null if new>"
    }}
  ]
}}
"""
