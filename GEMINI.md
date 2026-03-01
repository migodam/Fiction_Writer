# Fiction Writer Project Instructions

This project is a **Local-First** AI Fiction Writing Software.

## Architectural Principles

1.  **Privacy First**: All logic must prioritize local execution. Avoid external API calls (like OpenAI/Anthropic) unless specifically requested by the user. Prefer local LLM interfaces like **Ollama** or **llama-cpp-python**.
2.  **Long-Term Memory**: Implementation of RAG (Retrieval-Augmented Generation) or local state management to handle complex novel plot consistency.
3.  **UI/UX**: Target a clean, distraction-free writing environment. Streamlit or a desktop-focused web app is preferred for the initial prototype.
4.  **Extensibility**: The codebase should be modular, separating the LLM reasoning, content storage, and UI layers.

## Tech Stack

-   **Backend**: Python 3.10+, FastAPI or Flask (if needed).
-   **UI**: Streamlit (fast prototyping) or Electron/React (long-term).
-   **Local LLM Interface**: Ollama (preferred) or llama-cpp.
-   **Vector DB (Optional)**: ChromaDB or FAISS for plot consistency.

## Git Commit Style

-   Use clear, concise messages.
-   Prefix with `feat:`, `fix:`, `docs:`, or `chore:`.
