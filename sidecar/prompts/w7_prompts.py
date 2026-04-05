"""W7 Metadata Ingestion prompt templates.

All templates use Python .format() substitution.
Curly braces that are part of JSON examples are escaped as double braces {{}}.
"""

W7_EXTRACT_STYLE: str = """You are a literary style analyst extracting writing style metrics from a text chunk.

File type: {file_type}

Analyze the following text chunk and extract objective writing style metrics.

Text chunk:
{chunk_content}

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "avg_sentence_length": 18.5,
  "dialogue_ratio": 0.35,
  "pov_style": "third-person limited",
  "pacing_descriptor": "fast-paced with short punchy sentences"
}}

avg_sentence_length: average number of words per sentence (float).
dialogue_ratio: fraction of text that is dialogue (0.0 to 1.0).
pov_style: e.g. "first-person", "third-person limited", "third-person omniscient", "second-person".
pacing_descriptor: a brief phrase describing the overall rhythm and pace."""


W7_EXTRACT_VOCABULARY: str = """You are a linguistic analyst identifying distinctive vocabulary patterns in a text chunk.

File type: {file_type}

Analyze the following text chunk and identify its vocabulary characteristics.

Text chunk:
{chunk_content}

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "distinctive_words": ["word1", "word2", "word3"],
  "phrase_patterns": ["recurring phrase pattern 1", "recurring phrase pattern 2"],
  "register": "literary"
}}

distinctive_words: up to 10 unusual, characteristic, or frequently-used words.
phrase_patterns: up to 5 recurring syntactic or stylistic patterns (e.g. "X of Y constructions",
  "rhetorical questions", "em-dash interruptions").
register values: "formal", "casual", "literary", "colloquial"."""


W7_EXTRACT_STRUCTURE: str = """You are a narrative structure analyst examining story architecture in a text chunk.

File type: {file_type}

Analyze the following text chunk and describe its structural and organizational patterns.

Text chunk:
{chunk_content}

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "chapter_structure_notes": "How chapters or sections are organized and signposted",
  "scene_transition_style": "How the author moves between scenes or time periods",
  "narrative_rhythm": "The overall rhythm pattern (e.g. action-reflection alternation)"
}}

Be specific and descriptive. These notes will be used to help match writing style."""


W7_EXTRACT_KNOWLEDGE: str = """You are a knowledge extraction specialist identifying factual content in a text chunk.

File type: {file_type}

Analyze the following text chunk and extract key factual knowledge relevant to this file type.
For a novel: character facts, world facts, historical references.
For news/essay: key claims, named people/organizations, topics.
For a script: scene locations, character relationships, plot facts.

Text chunk:
{chunk_content}

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "key_facts": [
    "A specific factual claim or established fact from this chunk"
  ],
  "named_entities": [
    "A named person, place, organization, or object"
  ],
  "domain_tags": [
    "A topic or domain tag (e.g. 'medieval fantasy', 'detective fiction', 'political thriller')"
  ]
}}

Keep lists concise (up to 10 items each). Focus on facts that would be useful for
style reference and retrieval."""
