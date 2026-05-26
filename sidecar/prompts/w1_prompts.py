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
      "category": "<location|organization|faction|item|artifact|rule|system|concept|culture|custom>",
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

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All prose text fields (summary, role_in_story, physical_description, personality_traits, notes, open_questions) MUST be written in {source_language_label}. Do NOT translate character names, sect titles, honorifics, or epithets into English.
Do NOT mix English summaries into non-English source chunks or vice versa.
Preserve canonical surface forms exactly as the source writes them unless the registry already has a stronger canonical name.
Fields that MUST remain in English (internal enum keys): importance, story_function, groupKey.

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

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (title, description, stakes, temporal_hint, location_hint) MUST be written in {source_language_label}. Do NOT translate.
Fields that MUST remain in English (enum/internal keys): eventClass, timelineClass, eventType, arcRole, causalRole, branchRole, forkMergeHint, arcId, timelineLaneHint, dedupeKey.

## PROJECT DIGEST PLACEHOLDERS
The Text Chunk below is a packed compiler window. It may include multiple complete chapters and it begins
with PROJECT_STRUCTURE_DIGEST and PREVIOUS_VALIDATION_SUMMARY. Treat those sections as project context, not
story events. The window may include {{project_digest}}, {{existing_event_digest}}, {{timeline_branch_digest}},
and {{chapter_digest}} style records. Use that context to avoid re-emitting accepted/candidate events.

## TEMPORAL ANCHOR RULE
Every event MUST include the most specific time reference available: chapter number, arc stage, cultivation milestone, season, or relative marker like "three days later". Use this as temporal_hint. If no anchor exists, use "unknown" — never leave temporal_hint empty.

## CANONICAL VS SCENE-BEAT DECISION
Every candidate MUST explicitly choose:
- eventClass/timelineClass = canonical_event when the beat changes world state, relationship state, power status, faction alignment, major knowledge, survival stakes, or arc direction.
- eventClass/timelineClass = scene_beat when it is travel, training repetition, conversation texture, atmosphere, minor tactical movement, repeated explanation, or a sub-beat inside a larger canonical event.
- eventClass/timelineClass = background_reference when it is past lore, explanation, or remembered context that should not become a timeline proposal.

Only canonical_event candidates are expected to survive as timeline proposals. scene_beat candidates may be used
for merge recommendations or scene summaries. Do not promote every action to a canonical event.

## EVENT CLASS TAXONOMY
Every event MUST include eventClass using exactly one:
 - canonical_event
 - scene_beat
 - background_reference

Use eventType for the optional story-beat taxonomy:
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
- arcRole should be one of mainline, protagonist, faction, organization, location, antagonist, training, power_progression, background, or side
- causalRole should be one of cause, effect, turning_point, setup, payoff, background, or unknown
- branchRole should be one of mainline, fork, merge, parallel, callback, side_lane, or unknown
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
      "eventClass": "<canonical_event|scene_beat|background_reference>",
      "timelineClass": "<canonical_event|scene_beat|background_reference>",
      "eventType": "<inciting_choice|journey_departure|test_or_trial|discovery|training_breakthrough|confrontation|betrayal_or_reveal|alliance_or_bond|power_shift|injury_or_death|escape_or_pursuit|faction_move|other>",
      "arcId": "<stable snake_case arc id>",
      "arcRole": "<mainline|protagonist|faction|organization|location|antagonist|training|power_progression|background|side>",
      "causalRole": "<cause|effect|turning_point|setup|payoff|background|unknown>",
      "branchRole": "<mainline|fork|merge|parallel|callback|side_lane|unknown>",
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

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (name, description, attributes values) MUST be written in {source_language_label}.
Fields that MUST remain in English (enum/internal keys): category, container_hint, attribute keys.

## Instructions
Extract named world-building elements and explicit world rules grounded in this chunk.
- Focus on locations, organizations/factions, items/artifacts, rules/systems, concepts, cultures, and custom terms
- Normalize common Chinese fiction terms deterministically:
  门派/宗门/帮派 -> organization; 势力/阵营/联盟 -> faction; 功法/法术/修炼体系 -> system; 规则/法则 -> rule; 丹药/物品 -> item; 法器/宝物 -> artifact; 地名/地点 -> location.
- Named sects such as 七玄门 are organizations or factions, never characters and never locations.
- Prefer one entry per distinct mention
- Include a dedupeKey for each entry: lowercase NFC-normalized name, two colons, then the category. Example: 七玄门::organization. Use this key consistently across chunks for the same entity.
- Keep descriptions concise and text-grounded

Output valid JSON only:
{{
  "world_mentions": [
    {{
      "name": "<surface form from text>",
      "category": "<location|organization|faction|item|artifact|rule|system|concept|culture|custom>",
      "dedupeKey": "<normalized_name::category — lowercase, no spaces, NFC-normalized. E.g. 七玄门::organization>",
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

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (type, description, aliasEvidence, contradictionHint, evidence) MUST be written in {source_language_label}.
Fields that MUST remain in English (enum/internal keys): category, directionality, status, topologyRole.

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

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (chapter_hint, title, summary, location_hint, time_hint, purpose, character_names) MUST be written in {source_language_label}.
Fields that MUST remain in English (internal keys): arcId (snake_case arc identifier). canonicalEventRefs and sceneBeatRefs reference event titles — use the same language as those event titles.

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

# ── Extraction Variant Prompt Constants (B1) ──────────────────────────────────
# 12 new constants (3 per domain) for B2 dispatch via ImportGranularityProfile.
# Built from independent V2 PRE/POST/POLICY fragments.
# Existing constants above (W1_EXTRACT_CHARACTERS_DEEP etc.) are NOT modified.
# B2 dispatch (extract_window) will select among these. Until then, all existing
# callers continue using the unchanged constants above.

# ─── Character Variants ────────────────────────────────────────────────────────

_CHAR_V2_PRE: str = """
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

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All prose text fields (summary, role_in_story, physical_description, personality_traits, notes, open_questions) MUST be written in {source_language_label}. Do NOT translate character names, sect titles, honorifics, or epithets into English.
Do NOT mix English summaries into non-English source chunks or vice versa.
Preserve canonical surface forms exactly as the source writes them unless the registry already has a stronger canonical name.
Fields that MUST remain in English (internal enum keys): importance, story_function, groupKey.
"""

_CHAR_POLICY_WEBNOVEL: str = """
## EXTRACTION POLICY
character_granularity=major_only — WEBNOVEL / EPIC SCOPE

INCLUDE a character ONLY if they meet ≥1 of these criteria:
  • The character appears in ≥3 chapters of this window's chapter range
  • The character is a named direct peer, master, mentor, or rival of the protagonist
  • The character's story_function is: protagonist | antagonist | deuteragonist | foil

EXCLUDE the following — do NOT create new_characters entries for them:
  • Guards, gatekeepers, shopkeepers, market vendors, inn staff
  • Unnamed or titled-only disciples (e.g. "a disciple of the sect", "the third elder")
  • Single-scene villagers, passersby, nameless crowd members
  • Characters mentioned only in third-person narration with no dialogue or direct action in this window

Hard caps (strictly enforced):
  • Output ≤5 entries in new_characters per window. If more qualify, keep the highest-confidence 5.
  • summary: ≤15 words
  • Omit the `notes` key entirely — do not include it in any new_characters entry
  • Omit the `open_questions` key entirely — do not include it in any new_characters entry
"""

_CHAR_POLICY_BALANCED: str = """
## EXTRACTION POLICY
character_granularity=named_only — STANDARD NOVEL

INCLUDE:
  • All named characters who have dialogue, direct action, or explicit plot influence in this window
  • Characters with a named title or epithet that identifies them as distinct individuals

EXCLUDE:
  • Unnamed background NPCs with no title and no individual action
  • Characters mentioned only in passing narration with neither dialogue nor action

Hard caps:
  • Output ≤12 entries in new_characters per window
  • All standard LENGTH LIMITS apply (summary ≤25 words, role_in_story ≤12 words)
"""

_CHAR_POLICY_FINE: str = """
## EXTRACTION POLICY
character_granularity=all — SHORT STORY / DENSE LITERARY

INCLUDE:
  • All named characters regardless of scene count
  • Named-by-role characters with clear individual function (e.g. "the village elder", "her mother")
  • Socially meaningful unnamed characters who recur or whose role materially affects the protagonist

EXCLUDE:
  • Only truly incidental background extras with zero social function and no expectation of return appearance
    (e.g. "a passerby", "the crowd", "a few servants" with no individual identity)

Hard caps:
  • Output ≤25 entries in new_characters per window
  • All standard LENGTH LIMITS apply
"""

_CHAR_V2_POST: str = """
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

W1_EXTRACT_CHARACTERS_DEEP_WEBNOVEL: str = _CHAR_V2_PRE + _CHAR_POLICY_WEBNOVEL + _CHAR_V2_POST
W1_EXTRACT_CHARACTERS_DEEP_BALANCED: str = _CHAR_V2_PRE + _CHAR_POLICY_BALANCED + _CHAR_V2_POST
W1_EXTRACT_CHARACTERS_DEEP_FINE: str = _CHAR_V2_PRE + _CHAR_POLICY_FINE + _CHAR_V2_POST

# ─── Event / Timeline Variants ─────────────────────────────────────────────────

_EVENT_V2_PRE: str = """
You are DeepSeek V4 Pro acting as the W1 Import Timeline Scout for a long-form novel.
You are processing chunk {chunk_id} of {total_chunks}. Your output feeds Timeline Architect,
which needs canonical-vs-scene-beat decisions, dedupe keys, branch hints, and causal topology.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (title, description, stakes, temporal_hint, location_hint) MUST be written in {source_language_label}. Do NOT translate.
Fields that MUST remain in English (enum/internal keys): eventClass, timelineClass, eventType, arcRole, causalRole, branchRole, forkMergeHint, arcId, timelineLaneHint, dedupeKey.
"""

_EVENT_POLICY_ARC: str = """
## EXTRACTION POLICY
event_density=arc_level — EPIC / WEBNOVEL ARC-LEVEL ONLY

INCLUDE only events that meet ≥1 of these criteria:
  • Arc-turning-point: the event permanently changes faction alignment, power status, realm level, or protagonist life phase
  • Irreversible status change: realm breakthrough, major character death, sect destruction, alliance sealing, betrayal revealed
  • Protagonist phase transition: leaving homeland, entering sect, completing major trial, facing final antagonist

EXCLUDE — do NOT emit these as canonical_event:
  • Chapter-level training sessions, sparring bouts without status change
  • Travel scenes, arrival/departure without consequence
  • Dialogue-only scenes that do not change power balance or alliance state
  • Repetitive battles where the outcome is predetermined and state does not change

Hard caps (strictly enforced):
  • ≤6 canonical_event entries per window total
  • confidence ≥ 0.85 — skip anything below
  • Scene beats and background references are still welcome but must be clearly classified as such
"""

_EVENT_POLICY_CHAPTER: str = """
## EXTRACTION POLICY
event_density=chapter_level — STANDARD NOVEL

INCLUDE:
  • 1–3 significant events per chapter that advance plot, change character status, or reveal information
  • Recurring status-changing events (confrontations, discoveries, power shifts, alliance formations)

EXCLUDE:
  • Repetitive scene beats with no state change
  • Minor inter-chapter transitions and travel with no story consequence

Hard caps:
  • ≤3 canonical_event candidates per source chapter
  • ≤12 total events per packed window
  • confidence ≥ 0.75
"""

_EVENT_POLICY_DENSE: str = """
## EXTRACTION POLICY
event_density=scene_level — DENSE LITERARY / SHORT STORY

INCLUDE:
  • All causally-significant scene transitions including emotional turning points
  • Dialogue-driven discoveries and revelations
  • Internal-monologue decisions that change the character's course
  • Subtle relationship shifts with causal weight

EXCLUDE:
  • Pure atmosphere or description with absolutely zero causal change
  • Scene-setting paragraphs with no action or decision

Hard caps:
  • ≤5 canonical_event candidates per chapter
  • ≤40 total events per packed window
  • confidence ≥ 0.65
"""

_EVENT_V2_POST: str = """
## PROJECT DIGEST PLACEHOLDERS
The Text Chunk below is a packed compiler window. It may include multiple complete chapters and it begins
with PROJECT_STRUCTURE_DIGEST and PREVIOUS_VALIDATION_SUMMARY. Treat those sections as project context, not
story events. The window may include {{project_digest}}, {{existing_event_digest}}, {{timeline_branch_digest}},
and {{chapter_digest}} style records. Use that context to avoid re-emitting accepted/candidate events.

## TEMPORAL ANCHOR RULE
Every event MUST include the most specific time reference available: chapter number, arc stage, cultivation milestone, season, or relative marker like "three days later". Use this as temporal_hint. If no anchor exists, use "unknown" — never leave temporal_hint empty.

## CANONICAL VS SCENE-BEAT DECISION
Every candidate MUST explicitly choose:
- eventClass/timelineClass = canonical_event when the beat changes world state, relationship state, power status, faction alignment, major knowledge, survival stakes, or arc direction.
- eventClass/timelineClass = scene_beat when it is travel, training repetition, conversation texture, atmosphere, minor tactical movement, repeated explanation, or a sub-beat inside a larger canonical event.
- eventClass/timelineClass = background_reference when it is past lore, explanation, or remembered context that should not become a timeline proposal.

Only canonical_event candidates are expected to survive as timeline proposals. scene_beat candidates may be used
for merge recommendations or scene summaries. Do not promote every action to a canonical event.

## EVENT CLASS TAXONOMY
Every event MUST include eventClass using exactly one:
 - canonical_event
 - scene_beat
 - background_reference

Use eventType for the optional story-beat taxonomy:
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

## CONFIDENCE FLOOR
Only output events matching the confidence floor in the EXTRACTION POLICY above. Skip anything below.

## Instructions
Extract only events that significantly advance the plot or mark a turning point.
- Prefer canonical character ids from the registry; fall back to character_names for unresolved references
- One event per distinct plot beat — do not split a single scene into multiple events
- Keep titles short and specific (max 6 words)
- Use arcId to group recurring lanes such as protagonist_origin, sect_entry, mentor_control, bottle_secret, cultivation_progress, faction_conflict, or antagonist_scheme
- timelineLaneHint should be a human-readable lane such as Main Arc, Mentor Threat, Sect Conflict, Bottle Mystery, Family Origin, or Rival Ally
- arcRole should be one of mainline, protagonist, faction, organization, location, antagonist, training, power_progression, background, or side
- causalRole should be one of cause, effect, turning_point, setup, payoff, background, or unknown
- branchRole should be one of mainline, fork, merge, parallel, callback, side_lane, or unknown
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
      "eventClass": "<canonical_event|scene_beat|background_reference>",
      "timelineClass": "<canonical_event|scene_beat|background_reference>",
      "eventType": "<inciting_choice|journey_departure|test_or_trial|discovery|training_breakthrough|confrontation|betrayal_or_reveal|alliance_or_bond|power_shift|injury_or_death|escape_or_pursuit|faction_move|other>",
      "arcId": "<stable snake_case arc id>",
      "arcRole": "<mainline|protagonist|faction|organization|location|antagonist|training|power_progression|background|side>",
      "causalRole": "<cause|effect|turning_point|setup|payoff|background|unknown>",
      "branchRole": "<mainline|fork|merge|parallel|callback|side_lane|unknown>",
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

W1_EXTRACT_EVENTS_DEEP_ARC: str = _EVENT_V2_PRE + _EVENT_POLICY_ARC + _EVENT_V2_POST
W1_EXTRACT_EVENTS_DEEP_CHAPTER: str = _EVENT_V2_PRE + _EVENT_POLICY_CHAPTER + _EVENT_V2_POST
W1_EXTRACT_EVENTS_DEEP_DENSE: str = _EVENT_V2_PRE + _EVENT_POLICY_DENSE + _EVENT_V2_POST

# ─── World Variants ────────────────────────────────────────────────────────────

_WORLD_V2_PRE: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to perform deep world extraction from this text chunk.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (name, description, attributes values) MUST be written in {source_language_label}.
Fields that MUST remain in English (enum/internal keys): category, container_hint, attribute keys.
"""

_WORLD_POLICY_SPARSE: str = """
## EXTRACTION POLICY
world_density=named_only — WEBNOVEL / SPARSE

INCLUDE only world entities that meet ≥1 of these criteria:
  • A major named location (city, region, sect headquarters, dungeon) that appears in ≥3 chapters of this window
  • A named organization or faction with ≥3 chapter mentions in this window
  • An item or artifact that is central to the plot arc (protagonist carries it, antagonist seeks it, it changes status)

EXCLUDE:
  • Single-mention locations named only once in passing
  • Minor factions or sub-groups with no independent role
  • Power system details, technique names, cultivation trivia
  • Cultural flavor notes and background world rules not directly referenced in action

Hard caps (strictly enforced):
  • ≤2 world_mentions entries per chapter in this window
  • Output name + category + 1-sentence description only
  • Omit the `attributes` key entirely — do not include it in any world_mentions entry
"""

_WORLD_POLICY_STRUCTURAL: str = """
## EXTRACTION POLICY
world_density=structural — STANDARD NOVEL

INCLUDE:
  • All named locations and organizations mentioned with context
  • Items and artifacts with narrative function (used, sought, or described)
  • Key system rules and power tiers explicitly mentioned in this chunk
  • Sects, factions, and cultural groups with at least one sentence of description

EXCLUDE:
  • Background flavor notes that add no story-relevant information
  • Entries that are already well-represented in the Entity Registry

Hard caps:
  • ≤3 world_mentions entries per chapter in this window
  • Include description + container_hint; include `attributes` with up to 3 key-value pairs
"""

_WORLD_POLICY_LORE: str = """
## EXTRACTION POLICY
world_density=full_lore — DENSE LITERARY / MAXIMUM CAPTURE

INCLUDE:
  • All named world entities regardless of mention frequency
  • All system components (cultivation realms, technique tiers, rule variants)
  • All cultural terms with any description in the source
  • Flavor entries that carry explicit world rules even if not plot-critical

EXCLUDE:
  • Nothing with a name and any context — capture everything

Hard caps:
  • ≤5 world_mentions entries per chapter in this window
  • Include full attributes dict with all key-value pairs the source provides
"""

_WORLD_V2_POST: str = """
## Instructions
Extract named world-building elements and explicit world rules grounded in this chunk.
- Focus on locations, organizations/factions, items/artifacts, rules/systems, concepts, cultures, and custom terms
- Normalize common Chinese fiction terms deterministically:
  门派/宗门/帮派 -> organization; 势力/阵营/联盟 -> faction; 功法/法术/修炼体系 -> system; 规则/法则 -> rule; 丹药/物品 -> item; 法器/宝物 -> artifact; 地名/地点 -> location.
- Named sects such as 七玄门 are organizations or factions, never characters and never locations.
- Prefer one entry per distinct mention
- Include a dedupeKey for each entry: lowercase NFC-normalized name, two colons, then the category. Example: 七玄门::organization. Use this key consistently across chunks for the same entity.
- Keep descriptions concise and text-grounded

Output valid JSON only:
{{
  "world_mentions": [
    {{
      "name": "<surface form from text>",
      "category": "<location|organization|faction|item|artifact|rule|system|concept|culture|custom>",
      "dedupeKey": "<normalized_name::category — lowercase, no spaces, NFC-normalized. E.g. 七玄门::organization>",
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

W1_EXTRACT_WORLD_DEEP_SPARSE: str = _WORLD_V2_PRE + _WORLD_POLICY_SPARSE + _WORLD_V2_POST
W1_EXTRACT_WORLD_DEEP_STRUCTURAL: str = _WORLD_V2_PRE + _WORLD_POLICY_STRUCTURAL + _WORLD_V2_POST
W1_EXTRACT_WORLD_DEEP_LORE: str = _WORLD_V2_PRE + _WORLD_POLICY_LORE + _WORLD_V2_POST

# ─── Relationship Variants ─────────────────────────────────────────────────────

_REL_V2_PRE: str = """
You are processing chunk {chunk_id} of {total_chunks} from a novel import pipeline.
Your job is to extract relationship evidence that helps cross-validate character identity,
role grouping, aliases, and timeline topology.

## Entity Registry
{entity_registry_summary}

## Text Chunk
{chunk_content}

## OUTPUT LANGUAGE
[language_policy={language_policy}] OUTPUT LANGUAGE: {source_language_label}
All user-visible text fields (type, description, aliasEvidence, contradictionHint, evidence) MUST be written in {source_language_label}.
Fields that MUST remain in English (enum/internal keys): category, directionality, status, topologyRole.
"""

_REL_POLICY_CORE: str = """
## EXTRACTION POLICY
relationship_depth=core — WEBNOVEL / MAJOR BONDS ONLY

INCLUDE only relationships of the following types:
  • Parent-child and named sibling bonds
  • Master-disciple and named teacher-student bonds
  • Major romantic pairs with explicit narrative acknowledgment
  • Named direct rivals or antagonists with sustained conflict across chapters

EXCLUDE:
  • Transient interactions (characters who meet once)
  • Acquaintance-level or passing social interactions
  • Faction membership bonds without direct personal dynamics
  • Unnamed relationship categories (e.g. "fellow disciples")

Hard cap:
  • ≤3 relationship entries per window
"""

_REL_POLICY_RECURRING: str = """
## EXTRACTION POLICY
relationship_depth=recurring — STANDARD NOVEL

INCLUDE:
  • All relationships supported by explicit interaction, dialogue, internal thought, or narration in this chunk
  • Recurring dynamics between named characters with evidence across multiple scenes

EXCLUDE:
  • Relationships based only on faction membership without direct personal interaction evidence
  • Pure speculation not grounded in text evidence from this chunk
"""

_REL_POLICY_DENSE: str = """
## EXTRACTION POLICY
relationship_depth=dense — SHORT STORY / MAXIMUM COVERAGE

INCLUDE:
  • All named-to-named character interactions including one-time meetings
  • Implied relationships supported by internal monologue, reported speech, or third-person narration
  • All aliasEvidence chains that help cross-validate identity

EXCLUDE:
  • Only completely ungrounded speculation with zero textual support
"""

_REL_V2_POST: str = """
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

W1_EXTRACT_RELATIONSHIPS_CORE: str = _REL_V2_PRE + _REL_POLICY_CORE + _REL_V2_POST
W1_EXTRACT_RELATIONSHIPS_RECURRING: str = _REL_V2_PRE + _REL_POLICY_RECURRING + _REL_V2_POST
W1_EXTRACT_RELATIONSHIPS_DENSE: str = _REL_V2_PRE + _REL_POLICY_DENSE + _REL_V2_POST

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

## Language Rule
All user-facing `name` and `description` fields MUST be in {source_language_label} (matching the source text language).
Internal keys such as `type` and `mode` may remain in English.

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
