import json
import uuid
from typing import List, Dict, Any
from src.ai.openai_client import OpenAIClient

class NarrativeWorkflow:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", language: str = "English"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.client = OpenAIClient(api_key=api_key, model=model) if api_key else None

    def _ensure_client(self):
        if not self.client:
            raise ValueError("OpenAI API Key is missing. Please configure it in the App page.")

    def generate_clarification_questions(self, idea: str, existing_facts: List[Dict], count: int = 10) -> List[str]:
        self._ensure_client()
        prompt = f"""
        Idea: {idea}
        Task: You are a professional Narrative Architect. 
        Generate {count} specific questions in {self.language}.
        Rules: Return ONLY a JSON list of strings.
        """
        messages = [{"role": "system", "content": f"You are a professional Narrative Architect in {self.language}."},
                    {"role": "user", "content": prompt}]
        response_text = self.client.chat(messages)
        clean_json = response_text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)[:count]

    def run_packager(self, idea: str, qa_results: List[Dict]) -> Dict:
        self._ensure_client()
        prompt = f"""
        User Idea: {idea}
        Q&A: {json.dumps(qa_results)}
        Task: Create a structured GenerationRequest in {self.language}.
        Output Schema: {{ "intent": "...", "target_output": "outline|chapter|scene", "timeline_granularity": 20 }}
        """
        messages = [{"role": "system", "content": "You output only JSON."},
                    {"role": "user", "content": prompt}]
        response_text = self.client.chat(messages)
        return json.loads(response_text.strip().replace("```json", "").replace("```", ""))

    def run_core_agent(self, spec: Dict, memory_snapshot: Dict) -> Dict:
        self._ensure_client()
        granularity = spec.get("timeline_granularity", 20)
        
        prompt = f"""
        Execute Spec: {json.dumps(spec)}
        Context: {json.dumps(memory_snapshot)}
        
        Rules for PROJECT_UPDATES:
        1. Timeline: Generate EXACTLY {granularity} events for a fine-grained chronology.
        2. Characters: ALL new characters MUST have "status": "candidate".
        3. Settings: Use 'setting_pages' structure with 'upsert_pages' and 'upsert_items'. Items must have 'fields' (dict).
        4. Language: Everything must be in {self.language}.
        
        Output MUST be dual-part JSON:
        {{
          "user_output": {{ "title": "...", "content_markdown": "..." }},
          "project_updates": {{
            "timeline_events": {{ "upsert": [] }},
            "characters": {{ "upsert": [] }},
            "setting_pages": {{ "upsert_pages": [], "upsert_items": [] }}
          }}
        }}
        """
        messages = [{"role": "system", "content": f"You are a Lead Narrative Scientist. Output ONLY strict JSON in {self.language}."},
                    {"role": "user", "content": prompt}]
        response_text = self.client.chat(messages)
        return json.loads(response_text.strip().replace("```json", "").replace("```", ""))
