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
        Existing Context Facts: {json.dumps(existing_facts[:5])}
        
        Task: You are a professional Narrative Architect. 
        Analyze the author's idea and generate {count} diverse, probing, and specific questions.
        These questions should uncover gaps in:
        1. Character motivations/fears
        2. World-building logic/consequences
        3. Core conflict/stakes
        4. Plot twists/pacing
        
        Rules:
        - Return ONLY a JSON list of strings.
        - LANGUAGE: You MUST ask these questions in {self.language}.
        - NO conversational filler.
        - Each question must be unique and highly relevant to the provided idea.
        """
        try:
            messages = [{"role": "system", "content": f"You are a professional Narrative Architect. You communicate strictly in {self.language}."},
                        {"role": "user", "content": prompt}]
            response_text = self.client.chat(messages)
            
            clean_json = response_text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean_json)[:count]
        except Exception as e:
            return [f"Error generating questions: {str(e)}", "Please check your API key and connection."]

    def run_packager(self, idea: str, qa_results: List[Dict]) -> Dict:
        self._ensure_client()
        prompt = f"""
        Task: Convert raw input into a structured Narrative Specification.
        User Idea: {idea}
        Interview Q&A: {json.dumps(qa_results)}
        
        Rules:
        - Output EXACTLY this JSON schema.
        - Ensure any natural language descriptions within the JSON (like intent) are in {self.language}.
        
        Schema:
        {{
          "intent": "main goal of the story",
          "genre": "fantasy|sci-fi|mystery|etc",
          "target_output": "outline|chapter|scene|worldbuilding",
          "constraints": {{ "pov": "1st/3rd", "tone": "dark/light", "length": "short/long", "avoid": [] }},
          "clarifier": {{ "used": true, "rounds": 1, "qa": [...] }}
        }}
        """
        messages = [{"role": "system", "content": f"You output only structured JSON. All narrative content must be in {self.language}."},
                    {"role": "user", "content": prompt}]
        response_text = self.client.chat(messages)
        clean_json = response_text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)

    def run_core_agent(self, spec: Dict, memory_snapshot: Dict) -> Dict:
        self._ensure_client()
        prompt = f"""
        You are the Lead Narrative Scientist. Execute the following specification.
        Spec: {json.dumps(spec)}
        Context Snapshot: {json.dumps(memory_snapshot)}
        
        Rules:
        - All content in 'user_output' (title, markdown, suggestions) MUST be written in {self.language}.
        - All 'project_updates' content (names, descriptions, traits, etc.) MUST be written in {self.language}.
        
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
        """
        messages = [{"role": "system", "content": f"You are a Narrative Scientist. Output ONLY JSON. All narrative text must be in {self.language}."},
                    {"role": "user", "content": prompt}]
        response_text = self.client.chat(messages)
        clean_json = response_text.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_json)
