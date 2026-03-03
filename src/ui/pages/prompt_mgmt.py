import streamlit as st

# We keep the prompts visible for the user to understand the system logic
SYSTEM_PROMPTS = {
    "Narrative Architect (Clarifier)": """
    Role: Narrative Architect
    Task: Generate probing, deep questions to clarify the story. 
    Focus: logic gaps, character secrets, and world consequences.
    Output: JSON list of strings.
    """,
    "World Architect (Core Agent)": """
    Role: Narrative World Architect and Story Planner
    Task: Generate 5-8 characters (candidate), 15-30 timeline events, structured relationships, and OneNote settings.
    Output: Dual-part JSON (user_output + project_updates).
    """,
    "Packager (Requirements Analyst)": """
    Task: Convert raw input and interview history into a structured GenerationRequest JSON.
    Output: JSON spec.
    """
}

def render(memory):
    st.header("Prompt Management")
    st.caption("Review and understand the internal instructions driving the AI.")

    st.info("Currently, system prompts are hard-coded in 'src/ai/workflow.py' for stability. Below are the active versions.")

    for role, content in SYSTEM_PROMPTS.items():
        with st.expander(f"System Role: {role}"):
            st.code(content.strip(), language="markdown")
            st.button(f"Copy {role} Prompt", key=f"cp_{role}")

    st.write("---")
    st.subheader("Model Configuration")
    st.write(f"**Primary Model:** {st.session_state.get('openai_model', 'gpt-4o-mini')}")
    st.write(f"**Generation Language:** {st.session_state.get('creative_language', 'English')}")
