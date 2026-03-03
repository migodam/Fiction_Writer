import streamlit as st
import json
import os

DEFAULT_PROMPTS = {
  "clarifier_prompt": "You are a professional Narrative Architect. Generate exactly 10 probing, deep questions to clarify the story. Focus on logic gaps, character secrets, and world consequences. Output ONLY a JSON list of strings.",
  "packager_prompt": "You are a requirements analyst. Convert the user's raw idea and the interview history into a structured GenerationRequest JSON spec. Output ONLY JSON.",
  "core_agent_prompt": "You are a narrative world architect and story planner. Generate a comprehensive narrative plan and structured project updates. Requirements: 5-8 new characters (status: candidate) with realistic names (e.g., Silas Vane); 15-30 dense timeline events with locations and consequences; structured relationships with hidden truths; at least 2 setting pages with 3 items each. Output MUST be dual-part JSON: {user_output: {...}, project_updates: {...}}.",
  "extractor_prompt": "Extract structured narrative facts from the text. Focus on entities and their attributes. Output ONLY JSON.",
  "timeline_prompt": "Generate a detailed chronology of events. Include time, title, location, participants, summary, stakes, consequences.",
  "character_prompt": "Create detailed character profiles including traits, goals, fears, secrets, speech_style, arc, and affiliations."
}

def render(memory):
    st.header("Prompt Manager")
    st.caption("Customize and tune the AI's personas and behaviors.")

    path = "config/prompts.json"
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PROMPTS, f, indent=2)

    with open(path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    for key, val in prompts.items():
        st.subheader(key.replace("_", " ").title())
        new_val = st.text_area("Template", value=val, height=150, key=f"p_edit_v7_{key}")
        if st.button(f"Save {key}", key=f"p_btn_v7_{key}"):
            prompts[key] = new_val
            with open(path, "w", encoding="utf-8") as f:
                json.dump(prompts, f, indent=2, ensure_ascii=False)
            st.success(f"Updated {key}")

    st.write("---")
    if st.button("Reset ALL to Default"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PROMPTS, f, indent=2)
        st.warning("All prompts reset. Please refresh.")
        st.rerun()
