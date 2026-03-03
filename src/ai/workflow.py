import json
import uuid
import os
from typing import List, Dict, Any
from src.ai.openai_client import OpenAIClient

class NarrativeWorkflow:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", language: str = "English"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.client = OpenAIClient(api_key=api_key, model=model) if api_key else None
        self.prompts = self._load_prompts()

    def _load_prompts(self):
        path = "config/prompts.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _ensure_client(self):
        if not self.client:
            raise ValueError("OpenAI API Key is missing.")

    def generate_clarification_questions(self, idea: str, existing_facts: List[Dict], history: List[Dict] = None, count: int = 10) -> List[str]:
        self._ensure_client()
        history_str = json.dumps(history) if history else "No history yet."
        system_p = self.prompts.get("clarifier_prompt", "You are a professional Narrative Architect.")
        
        prompt = f"""
        Role Instruction: {system_p}
        Language: {self.language}
        Input Idea: {idea}
        Interview History: {history_str}
        Task: Generate exactly {count} deep, probing questions.
        """
        messages = [
            {"role": "system", "content": f"{system_p}. You speak and output JSON in {self.language}."},
            {"role": "user", "content": prompt}
        ]
        resp = self.client.chat(messages)
        clean = resp.strip().replace("```json", "").replace("```", "")
        return json.loads(clean)[:count]

    def run_packager(self, idea: str, qa_history: List[Dict]) -> Dict:
        self._ensure_client()
        system_p = self.prompts.get("packager_prompt", "You are a requirements analyst.")
        prompt = f"""
        Role: {system_p}
        Input: {idea}
        QA: {json.dumps(qa_history)}
        Language: {self.language}
        """
        messages = [{"role": "system", "content": "Output ONLY JSON."}, {"role": "user", "content": prompt}]
        resp = self.client.chat(messages)
        return json.loads(resp.strip().replace("```json", "").replace("```", ""))

    def run_core_agent(self, idea: str, qa_history: List[Dict], memory_snapshot: Dict) -> Dict:
        self._ensure_client()
        system_p = self.prompts.get("core_agent_prompt", "You are a world architect.")
        prompt = f"""
        Role: {system_p}
        Language: {self.language}
        Input Idea: {idea}
        Interview Context: {json.dumps(qa_history)}
        Memory: {json.dumps(memory_snapshot)}
        """
        messages = [{"role": "system", "content": f"{system_p}. Output strictly in {self.language}."}, {"role": "user", "content": prompt}]
        resp = self.client.chat(messages)
        return json.loads(resp.strip().replace("```json", "").replace("```", ""))

    def generate_pov_timeline(self, char_name: str, events: List[Dict]) -> List[Dict]:
        self._ensure_client()
        prompt = f"""
        Character: {char_name}
        Events: {json.dumps(events)}
        
        Task: For each event, describe:
        1. What the character knows.
        2. What they want.
        3. How they changed.
        
        Language: {self.language}
        Output Schema: [{"event_id": "...", "perspective": "..."}]
        """
        messages = [{"role": "system", "content": f"Output ONLY JSON in {self.language}."}, {"role": "user", "content": prompt}]
        resp = self.client.chat(messages)
        return json.loads(resp.strip().replace("```json", "").replace("```", ""))
