import ollama
import json
import uuid
from typing import List, Dict, Any

class NarrativeWorkflow:
    def __init__(self, model: str = "llama3.1:8b"):
        self.model = model

    def generate_clarification_questions(self, idea: str, existing_facts: List[Dict], count: int = 10) -> List[str]:
        prompt = f"""
        Idea: {idea}
        Context: {json.dumps(existing_facts[:5])}
        
        Task: Act as a Narrative Researcher. Generate {count} probing questions to help the author expand this idea into a structured story.
        Rules: Return ONLY a JSON list of strings. No commentary.
        """
        try:
            response = ollama.generate(model=self.model, prompt=prompt, format="json")
            return json.loads(response['response'])[:count]
        except:
            return [f"Could you elaborate on part {i+1}?" for i in range(count)]

    def run_packager(self, idea: str, qa_results: List[Dict]) -> Dict:
        """
        Converts messy user input and Q&A into a structured GenerationRequest.
        """
        prompt = f"""
        User Idea: {idea}
        Clarifier Q&A: {json.dumps(qa_results)}
        
        Task: Create a structured GenerationRequest JSON.
        Output Schema:
        {{
          "intent": "string",
          "genre": "string|null",
          "target_output": "outline|chapter|scene|worldbuilding|character|mixed",
          "constraints": {{ "pov": "string|null", "tone": "string|null", "length": "short|medium|long|null", "avoid": [] }},
          "clarifier": {{ "used": true, "rounds": 1, "qa": [] }}
        }}
        Rules: Output ONLY JSON. No other text.
        """
        response = ollama.generate(model=self.model, prompt=prompt, format="json")
        return json.loads(response['response'])

    def run_core_agent(self, spec: Dict, memory_snapshot: Dict) -> Dict:
        """
        Generates content and structured project updates.
        """
        prompt = f"""
        Spec: {json.dumps(spec)}
        Memory: {json.dumps(memory_snapshot)}
        
        Task: Act as the Lead Narrative Scientist. Execute the spec.
        Output MUST be dual-part JSON:
        {{
          "user_output": {{ "title": "string", "content_markdown": "string", "next_suggestions": [] }},
          "project_updates": {{
            "characters": {{ "upsert": [], "delete": [] }},
            "relationships": {{ "upsert": [], "delete": [] }},
            "timeline_events": {{ "upsert": [], "delete": [] }},
            "setting_pages": {{ "upsert": [], "delete": [] }},
            "canon_facts": {{ "upsert": [], "delete": [] }}
          }}
        }}
        Rules: 
        - upsert items must have an 'id' (generate a uuid if new).
        - project_updates should reflect changes derived from your content generation.
        - Output ONLY strict JSON.
        """
        response = ollama.generate(model=self.model, prompt=prompt, format="json")
        return json.loads(response['response'])
