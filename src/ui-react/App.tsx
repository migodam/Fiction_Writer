import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { 
  Layout, Users, Clock, Network, Globe, 
  PlayCircle, CheckCircle, FileText, PenTool, 
  BarChart2, Terminal, Search, Settings,
  Save, Undo, Redo, FilePlus, FolderOpen, Download,
  Cpu, Activity, ChevronRight
} from 'lucide-react';
import { useUIStore, useProjectStore } from './store';
import { CharactersWorkspace } from './components/CharactersWorkspace';
import { TimelineWorkspace } from './components/TimelineWorkspace';
import { EventInspector } from './components/EventInspector';
import { WritingWorkspace } from './components/WritingWorkspace';
import { GraphWorkspace } from './components/GraphWorkspace';
import { WorldWorkspace } from './components/WorldWorkspace';
import { SimulationWorkspace } from './components/SimulationWorkspace';
import { ConsistencyWorkspace } from './components/ConsistencyWorkspace';
import { BetaReaderWorkspace } from './components/BetaReaderWorkspace';
import { Sidebar } from './components/Sidebar';

// UTILS
const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');

interface CommandOption {
    label: string;
    path: string;
    type: string;
    id?: string;
    description?: string;
}

// COMMAND PALETTE
const CommandPalette = () => {
  const { isCommandPaletteOpen, toggleCommandPalette } = useUIStore();
  const { searchEntities, setSelectedEntity } = useProjectStore();
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const activityOptions: CommandOption[] = [
    { label: 'Go to Workbench', path: '/workbench', type: 'activity' },
    { label: 'Go to Writing Studio', path: '/writing', type: 'activity' },
    { label: 'Go to Characters', path: '/characters', type: 'activity' },
    { label: 'Go to Timeline', path: '/timeline', type: 'activity' },
    { label: 'Go to Graph', path: '/graph', type: 'activity' },
    { label: 'Go to World Model', path: '/world', type: 'activity' },
    { label: 'Go to Simulation', path: '/simulation', type: 'activity' },
    { label: 'Go to Beta Reader', path: '/beta-reader', type: 'activity' },
    { label: 'Go to Consistency', path: '/consistency', type: 'activity' },
    { label: 'Go to Publish', path: '/publish', type: 'activity' },
    { label: 'Go to Insights', path: '/insights', type: 'activity' },
  ];

  const entityResults: CommandOption[] = searchEntities(search).map(e => ({
      label: e.label,
      description: e.description,
      path: e.type === 'character' ? '/characters' : '/timeline',
      type: e.type || 'unknown',
      id: e.id
  }));

  const filteredActivities = activityOptions.filter(o => o.label.toLowerCase().includes(search.toLowerCase()));
  const allResults = [...filteredActivities, ...entityResults];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        toggleCommandPalette();
      }
      if (e.key === 'Escape') {
        toggleCommandPalette(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  if (!isCommandPaletteOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black bg-opacity-50" data-testid="command-palette">
      <div className="w-full max-w-lg bg-bg-elev-1 border border-border shadow-2xl rounded-lg overflow-hidden flex flex-col">
        <div className="flex items-center px-4 border-b border-border">
          <Search size={18} className="text-text-2" />
          <input 
            autoFocus
            className="w-full p-4 bg-transparent outline-none text-text"
            placeholder="Search activities or entities..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="max-h-80 overflow-y-auto py-2">
          {allResults.length > 0 ? allResults.map((opt, idx) => (
            <div 
              key={idx}
              className="px-4 py-2 hover:bg-brand hover:text-white cursor-pointer transition-colors flex items-center justify-between group"
              onClick={() => {
                if (opt.type !== 'activity' && opt.id) {
                    setSelectedEntity(opt.type as any, opt.id);
                }
                navigate(opt.path);
                toggleCommandPalette(false);
                setSearch('');
              }}
            >
              <div className="flex flex-col">
                <span className="text-sm font-medium">{opt.label}</span>
                {opt.description && <span className="text-[10px] opacity-60 uppercase font-bold tracking-tighter">{opt.description}</span>}
              </div>
              <ChevronRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          )) : (
              <div className="px-4 py-8 text-center text-text-3 text-xs uppercase tracking-widest font-bold italic">No results found</div>
          )}
        </div>
        <div className="p-2 bg-bg border-t border-border flex justify-between text-[9px] text-text-3 font-bold uppercase tracking-widest px-4">
            <span>↑↓ to navigate</span>
            <span>↵ to select</span>
            <span>esc to close</span>
        </div>
      </div>
    </div>
  );
};

// TOP TOOLBAR
const TopToolbar = () => {
    const { toggleCommandPalette } = useUIStore();
    const { saveProject, saveStatus } = useProjectStore();

    return (
      <header className="h-top-toolbar bg-bg-elev-1 border-b border-border flex items-center justify-between px-2 z-10" data-testid="top-toolbar">
        <div className="flex items-center gap-1">
          <div className="flex items-center gap-2 px-2 mr-2 border-r border-border">
            <div className="w-6 h-6 bg-brand rounded flex items-center justify-center text-white font-bold text-xs">F</div>
            <span className="font-bold text-[11px] text-text tracking-tighter">NARRATIVE IDE</span>
          </div>
          
          <div className="flex items-center gap-0.5">
            <ToolbarButton icon={<FilePlus size={14} />} title="New Project" />
            <ToolbarButton icon={<FolderOpen size={14} />} title="Open Project" />
            <ToolbarButton 
                icon={<Save size={14} className={saveStatus === 'Unsaved changes' ? 'text-brand' : ''} />} 
                title="Save Project" 
                onClick={saveProject}
                testId="toolbar-save"
            />
            <div className="w-px h-4 bg-border mx-1"></div>
            <ToolbarButton icon={<Undo size={14} />} title="Undo" />
            <ToolbarButton icon={<Redo size={14} />} title="Redo" />
            <div className="w-px h-4 bg-border mx-1"></div>
            <ToolbarButton icon={<Cpu size={14} />} title="Run AI" />
            <ToolbarButton icon={<Activity size={14} />} title="Run Simulation" />
            <ToolbarButton icon={<CheckCircle size={14} />} title="Check Consistency" />
            <ToolbarButton icon={<Download size={14} />} title="Export Book" />
          </div>
        </div>

        <div className="flex-1 max-w-md px-4">
            <div 
                className="flex items-center gap-2 bg-bg border border-border rounded px-3 py-1 text-text-2 cursor-pointer hover:border-border-2 transition-colors"
                onClick={() => toggleCommandPalette()}
                data-testid="global-search"
            >
                <Search size={12} />
                <span className="text-[11px]">Search entities, chapters, settings... (Ctrl+P)</span>
            </div>
        </div>

        <div className="flex items-center gap-1">
          <ToolbarButton icon={<Settings size={14} />} title="Settings" />
          <div className="w-8 h-8 rounded-full bg-bg-elev-2 ml-2 flex items-center justify-center text-[10px] font-bold border border-border">JD</div>
        </div>
      </header>
    );
};

const ToolbarButton = ({ icon, title, onClick, testId }: { icon: React.ReactNode, title: string, onClick?: () => void, testId?: string }) => (
    <button 
        className="p-1.5 hover:bg-hover rounded text-text-2 hover:text-text transition-colors" 
        title={title}
        onClick={onClick}
        data-testid={testId}
    >
        {icon}
    </button>
);

// SKELETON COMPONENTS
const Inspector = () => {
  const { selectedEntity, characters, timelineEvents } = useProjectStore();
  
  const renderContent = () => {
    if (selectedEntity.type === 'timeline_event') {
        return <EventInspector />;
    }

    if (selectedEntity.type === 'character') {
        const char = characters.find(c => c.id === selectedEntity.id);
        return (
            <div className="p-4">
                <div className="text-sm text-[#888888] uppercase mb-1 font-bold tracking-widest text-[10px]">Character Profile</div>
                <div className="text-lg font-semibold truncate text-[#007acc]">{char?.name || 'New Character'}</div>
                <div className="mt-4 text-xs text-[#999999] leading-relaxed border-t border-[#333333] pt-4">{char?.background}</div>
            </div>
        );
    }

    return (
        <div className="p-8 h-full flex flex-col items-center justify-center text-center text-[#cccccc]">
            <div className="w-12 h-12 rounded-full border-2 border-dashed border-[#333333] flex items-center justify-center mb-4 text-[#333333]">
                <Search size={20} />
            </div>
            <div className="text-[#666666] italic text-xs uppercase font-bold tracking-widest">No Selection</div>
            <p className="text-[10px] text-[#444444] mt-2 leading-relaxed">Select an item in the workspace or search (Ctrl+P) to view details</p>
        </div>
    );
  };

  return (
    <aside className="w-[var(--inspector-width)] bg-[#252526] border-l border-[#333333] flex flex-col overflow-hidden" data-testid="inspector">
       {renderContent()}
    </aside>
  );
};

const PlaceholderPage = ({ title, testId }: { title: string, testId: string }) => {
  return (
    <div className="p-12 h-full flex flex-col" data-testid={testId}>
      <h1 className="text-4xl font-bold mb-4 text-[#cccccc]">{title}</h1>
      <p className="text-[#666666] mb-8 uppercase tracking-[0.2em] text-xs">Module Placeholder</p>
      <div className="flex-1 border-2 border-dashed border-[#222222] rounded-xl flex items-center justify-center bg-[#181818]">
         <div className="text-center opacity-20">
            <Layout size={64} className="mx-auto mb-4" />
            <p className="text-sm uppercase font-bold text-[#cccccc]">Workspace Ready</p>
         </div>
      </div>
    </div>
  );
};

const Toast = () => {
    const { lastActionStatus } = useUIStore();
    if (!lastActionStatus) return null;
    return (
        <div className="fixed bottom-12 right-12 z-[100] bg-[#007acc] text-white px-6 py-2 rounded shadow-2xl font-bold text-xs uppercase tracking-widest">
            {lastActionStatus}
        </div>
    );
};

// LAYOUT
import { APP_ROUTES } from './config/routes';
import charMock from './mock/characters.json';
import timelineMock from './mock/timeline.json';
import relMock from './mock/relationships.json';
import worldMock from './mock/world_items.json';

const AppContent = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedEntity, characters, timelineEvents, projectName, saveStatus, loadProject } = useProjectStore();
  const { setActivity } = useUIStore();

  const currentActivityId = APP_ROUTES.find(a => location.pathname.startsWith(a.path))?.id || 'workbench';
  
  useEffect(() => {
    setActivity(currentActivityId);
  }, [currentActivityId]);

  useEffect(() => {
    // Initial data load
    loadProject({ 
        characters: charMock,
        timeline: { events: timelineMock, branches: [{ id: 'branch_main', name: 'Main' }] },
        relationships: relMock,
        world: { 
            containers: [
                { id: 'cont_notebooks', name: 'Notebooks', type: 'notebook', isDefault: true },
                { id: 'cont_maps', name: 'Maps', type: 'map', isDefault: true },
                { id: 'cont_orgs', name: 'Organizations', type: 'graph', isDefault: true },
                { id: 'cont_lore', name: 'Lore', type: 'notebook', isDefault: true },
            ],
            items: worldMock.map((item: any) => ({
                id: item.id,
                containerId: 'cont_lore', // default to lore for mock
                name: item.name,
                description: item.description,
                attributes: Object.entries(item.fields || {}).map(([key, value]) => ({ key, value: String(value) }))
            }))
        },
        chapters: [
            { id: 'chap_1', title: 'Chapter 1', orderIndex: 0 }
        ],
        scenes: [
            { id: 'scene_1', chapterId: 'chap_1', title: 'The Beginning', content: 'Once upon a time...', orderIndex: 0 }
        ]
    });
  }, []);

  const selectedLabel = selectedEntity.type === 'character' 
    ? characters.find(c => c.id === selectedEntity.id)?.name || 'New Character'
    : selectedEntity.type === 'timeline_event'
    ? timelineEvents.find(e => e.id === selectedEntity.id)?.title || 'New Event'
    : selectedEntity.id || 'No Selection';

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg text-text">
      <CommandPalette />
      <Toast />
      <TopToolbar />

      <div className="flex flex-1 overflow-hidden">
        {/* Activity Bar */}
        <nav className="w-activity-bar bg-bg-elev-2 border-r border-border flex flex-col items-center pt-2 gap-1" data-testid="activity-bar">
          {APP_ROUTES.map((activity) => {
            const isActive = currentActivityId === activity.id;
            return (
                <div
                key={activity.id}
                className={cnLocal(
                    "w-12 h-12 flex items-center justify-center cursor-pointer transition-all relative group",
                    isActive ? "text-brand" : "text-text-2 hover:text-text"
                )}
                onClick={() => navigate(activity.path)}
                title={activity.label}
                data-testid={activity.testId}
                >
                {isActive && <div className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-brand"></div>}
                {activity.icon}
                </div>
            );
          })}
        </nav>

        <Sidebar />

        {/* Workspace */}
        <main className="flex-1 bg-bg overflow-auto relative" data-testid="workspace">
          <Routes>
            <Route path="/" element={<PlaceholderPage title="Workbench" testId="agent-console" />} />
            <Route path="/workbench/*" element={<PlaceholderPage title="Workbench" testId="agent-console" />} />
            <Route path="/writing/*" element={<WritingWorkspace />} />
            <Route path="/characters/*" element={<CharactersWorkspace />} />
            <Route path="/timeline/*" element={<TimelineWorkspace />} />
            <Route path="/graph/*" element={<GraphWorkspace />} />
            <Route path="/world/*" element={<WorldWorkspace />} />
            <Route path="/simulation/*" element={<SimulationWorkspace />} />
            <Route path="/beta-reader/*" element={<BetaReaderWorkspace />} />
            <Route path="/consistency/*" element={<ConsistencyWorkspace />} />
            <Route path="/publish/*" element={<PlaceholderPage title="Publish" testId="publish-preview" />} />
            <Route path="/insights/*" element={<PlaceholderPage title="Insights" testId="insight-wordcount" />} />
          </Routes>
        </main>

        <Inspector />
      </div>

      {/* Status Bar */}
      <footer className="h-status-bar bg-brand text-white flex items-center justify-between px-3 text-[10px] font-bold uppercase tracking-wider" data-testid="status-bar">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="opacity-60">Project:</span>
            <span>{projectName}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="opacity-60">Status:</span>
            <span className={saveStatus === 'Error' ? 'text-red-300' : ''}>{saveStatus}</span>
          </div>
        </div>
        
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="opacity-60">Selection:</span>
            <span className="text-[#e0e0e0]">{selectedLabel}</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span>
                <span>Ollama: Ready</span>
            </div>
            <span>UTF-8</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

const App = () => {
  return (
    <Router>
      <AppContent />
    </Router>
  );
};

export default App;
