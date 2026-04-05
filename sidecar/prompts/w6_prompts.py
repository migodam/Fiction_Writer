"""W6 Beta Reader prompt templates.

All templates use Python .format() substitution.
Curly braces that are part of JSON examples are escaped as double braces {{}}.
"""

W6_READ_AS_PERSONA: str = """You are simulating a specific type of reader experiencing a story chunk for the first time.

Reader persona:
- Name: {persona_name}
- Type: {persona_type}
- Traits: {persona_traits}
- Focus areas: {focus_areas}

Read the following story chunk from this reader's perspective. Note their genuine reactions,
questions that arise while reading, emotional moments that resonate or fail to resonate,
and any points of confusion.

Story chunk:
{chunk_content}

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "reactions": [
    "Authentic reaction this reader would have"
  ],
  "questions_raised": [
    "Question this reader would be asking while reading"
  ],
  "emotional_moments": [
    "Moment that would have emotional impact on this reader (positive or negative)"
  ],
  "confusion_points": [
    "Something that confused or lost this reader"
  ]
}}

Be authentic to the persona type. A scholar notices plot logic; a shipper tracks relationships;
a casual reader cares about entertainment value. Use empty arrays where applicable."""


W6_GENERATE_FEEDBACK: str = """You are synthesizing reader feedback from a persona's reactions into structured scores.

Reader persona name: {persona_name}

Reactions from reading (JSON):
{chunk_reactions_json}

Chapter being reviewed: {chapter_id}

Based on these reactions, generate structured feedback scores across five dimensions.
Each score reflects how this reader would rate that aspect on a scale of 1-10.

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "feedback": [
    {{
      "dimension": "engagement",
      "score": 7,
      "comment": "Specific comment about engagement based on the reactions",
      "excerpt_reference": "A short quote or reference from the chunk, or null"
    }},
    {{
      "dimension": "pacing",
      "score": 6,
      "comment": "Specific comment about pacing",
      "excerpt_reference": null
    }},
    {{
      "dimension": "character",
      "score": 8,
      "comment": "Specific comment about character portrayal",
      "excerpt_reference": null
    }},
    {{
      "dimension": "logic",
      "score": 7,
      "comment": "Specific comment about logical consistency",
      "excerpt_reference": null
    }},
    {{
      "dimension": "world",
      "score": 6,
      "comment": "Specific comment about world-building",
      "excerpt_reference": null
    }}
  ]
}}

Dimension values: "engagement", "pacing", "character", "logic", "world".
Score range: 1 (very poor) to 10 (excellent). Include all five dimensions."""
