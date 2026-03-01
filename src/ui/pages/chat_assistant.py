import streamlit as st
import requests
from src.core.persistence import ProjectMemory

def render_chat_assistant(memory: ProjectMemory):
    st.header("Chat Assistant")
    st.caption("Brainstorm and explore your story universe with Llama 3.1.")

    # Display History
    chat_container = st.container(height=500)
    with chat_container:
        for msg in memory.data.get("chat_history", []):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # Chat Input
    if prompt := st.chat_input("Ask the AI about your story..."):
        # User message
        with chat_container:
            st.chat_message("user").markdown(prompt)
        memory.add_assistant_chat_msg("user", prompt)
        
        # AI Response
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Llama 3.1 is thinking..."):
                    try:
                        # Construct payload for Ollama REST API directly to handle timeouts better
                        newline = "\n"
                        context = newline.join([f"- {f['content']}" for f in memory.data.get("canon_facts", [])[:10]])
                        system_prompt = f"You are a narrative assistant. Known facts:{newline}{context}"
                        
                        payload = {
                            "model": "llama3.1:8b",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            "stream": False
                        }
                        
                        response = requests.post("http://localhost:11434/api/chat", json=payload, timeout=60)
                        
                        if response.status_code == 200:
                            ai_reply = response.json()["message"]["content"]
                            st.markdown(ai_reply)
                            memory.add_assistant_chat_msg("assistant", ai_reply, provenance="llama3.1:8b")
                        else:
                            st.error(f"Ollama Error: {response.text}")
                    except requests.exceptions.ConnectionError:
                        st.error("Connection Error: Is Ollama running on localhost:11434?")
                    except requests.exceptions.Timeout:
                        st.error("Timeout: The model took too long to respond.")
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")

    if st.button("Clear Chat History"):
        memory.clear_chat_history()
        st.rerun()
