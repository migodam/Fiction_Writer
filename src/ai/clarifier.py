import ollama
import json
from typing import List, Dict, Any

__all__ = ["CORE_SLOTS", "analyze_coverage_from_memory", "ClarifierAgent"]

CORE_SLOTS = {
    "premise": {"label": "Logline / Core Premise", "weight": 2.0},
    "character": {"label": "Main Character's Goal & Fear", "weight": 1.5},
    "conflict": {"label": "Main Antagonist / Conflict", "weight": 1.8},
    "world": {"label": "World Rules / Magic System", "weight": 1.2},
    "tone": {"label": "POV / Narrative Style", "weight": 1.0},
    "ending": {"label": "Ending Tendency", "weight": 1.0},
}

def analyze_coverage_from_memory(facts: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Analyzes how much of the narrative blueprint is covered by the current facts.
    """
    coverage = {k: 0.0 for k in CORE_SLOTS.keys()}
    for fact in facts:
        cat = fact.get("category", "general")
        if cat in coverage:
            coverage[cat] += 0.25
    for k in coverage:
        coverage[k] = min(1.0, coverage[k])
    return coverage

class ClarifierAgent:
    def __init__(self, model: str = "llama3.1:8b"):
        self.model = model

    def generate_questions(self, facts: List[Dict[str, Any]], coverage: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        AI asks questions about the largest narrative gaps.
        """
        # Pick the most underserved slots (highest weight * low coverage)
        missing = sorted(
            [(k, v) for k, v in coverage.items() if v < 0.8],
            key=lambda x: CORE_SLOTS[x[0]]["weight"] * (1 - x[1]),
            reverse=True
        )
        
        if not missing:
            return []

        target_slot = missing[0][0]
        context = "\n".join([f"- {f['content']}" for f in facts if f['category'] == target_slot])
        
        prompt = f"""
        Role: Senior Narrative Researcher
        Goal: Ask 1 highly specific question to help the author clarify the '{CORE_SLOTS[target_slot]['label']}' of their story.
        Existing Setting for this category:
        {context if context else "(None yet)"}
        
        Rules:
        - Be insightful, not generic.
        - Encourage depth in world-building or psychological motivation.
        - Ask ONLY ONE question.
        - Return ONLY the question text.
        """
        
        try:
            response = ollama.generate(model=self.model, prompt=prompt)
            return [{
                "slot": target_slot,
                "label": CORE_SLOTS[target_slot]["label"],
                "question": response['response'].strip()
            }]
        except Exception as e:
            return [{"slot": target_slot, "label": CORE_SLOTS[target_slot]["label"], "question": f"Ollama error: {str(e)}"}]

    def extract_new_facts(self, slot: str, user_answer: str) -> List[Dict[str, str]]:
        """
        Extract structured narrative facts from a raw user answer.
        """
        prompt = f"""
        Extract all core 'Canon Facts' from the following user text regarding the story's '{CORE_SLOTS[slot]['label']}'.
        Return them as a JSON list of strings.
        
        User Text: "{user_answer}"
        
        Format:
        ["Fact 1", "Fact 2"]
        """
        
        try:
            response = ollama.generate(model=self.model, prompt=prompt, format="json")
            fact_list = json.loads(response['response'])
            return [{"content": f, "category": slot} for f in fact_list]
        except:
            # Fallback if AI fails to return JSON
            return [{"content": user_answer, "category": slot}]
