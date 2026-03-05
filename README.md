# Narrative IDE — Desktop Narrative IDE (Windows Demo)

This is a commercial-grade **Local-First AI Narrative IDE** built for professional fiction writers. It provides a VS Code / Premiere-style interface for managing complex story structures, characters, timelines, and world-building.

## Key Features (P0/P1 Implemented)

- **IDE Shell**: Full-featured layout with Activity Bar, Sidebar, Workspace, and Global Inspector.
- **Command Palette (Ctrl+P)**: Fast, fuzzy-search navigation between all modules.
- **Writing Studio**: 
  - Serif-based distraction-free editor.
  - **Debounced Autosave**: Automatic background saving with UI status feedback.
  - **Context Panel**: Real-time reference to characters and timeline events while writing.
- **Characters Module**:
  - Candidate confirmation workflow (AI-generated candidates to confirmed roster).
  - Detailed character profile management with explicit save.
- **Timeline Module**:
  - Multi-branch track system.
  - Interactive event nodes with deep integration into the Global Inspector.
- **Global Selection Model**: Unified selection state across the entire IDE.

## Tech Stack

- **Shell**: [Electron](https://www.electronjs.org/)
- **Frontend**: [React 18](https://react.dev/) + [Vite](https://vitejs.dev/)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) + [Lucide Icons](https://lucide.dev/)
- **State Management**: [Zustand](https://docs.pmnd.rs/zustand/getting-started/introduction)
- **Testing**: [Playwright](https://playwright.dev/) (E2E)
- **Language**: TypeScript

## Getting Started

### Prerequisites
- Node.js v20 or higher
- Windows OS (for targeted UI optimizations)

### Installation
```powershell
npm install
```

### Running the Application
To start the IDE in development mode (Vite + Electron):
```powershell
npm run electron:dev
```

To run the web version only (Vite):
```powershell
npm run ui:dev
```

### Testing
Run all P0 and smoke tests:
```powershell
npm run test:e2e
```

## Project Structure
- `src/ui-react/`: React frontend application.
- `src/electron/`: Electron main process and IPC logic.
- `src/ui/`: Legacy Streamlit UI (Reference only).
- `dev_agent_logs/`: Comprehensive engineering logs, metrics, and architecture notes.
- `dev_docs/`: Governing specifications and logic definitions.

## License
MIT
