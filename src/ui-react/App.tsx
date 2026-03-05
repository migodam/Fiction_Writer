import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { 
  Layout, 
  Users, 
  Clock, 
  Network, 
  Globe, 
  PlayCircle, 
  CheckCircle, 
  FileText, 
  PenTool, 
  BarChart2, 
  Terminal,
  Search,
  Settings
} from 'lucide-react';
import { useUIStore, useProjectStore } from './store';
import { CharactersWorkspace } from './components/CharactersWorkspace';
import { TimelineWorkspace } from './components/TimelineWorkspace';
import { EventInspector } from './components/EventInspector';
import { WritingWorkspace } from './components/WritingWorkspace';

// UTILS
const cnLocal = (...inputs: any[]) => inputs.filter(Boolean).join(' ');

// COMMAND PALETTE
const CommandPalette = () => {
  const { isCommandPaletteOpen, toggleCommandPalette } = useUIStore();
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const options = [
    { label: 'Go to Workbench', path: '/workbench' },
    { label: 'Go to Writing Studio', path: '/writing' },
    { label: 'Go to Characters', path: '/characters' },
    { label: 'Go to Timeline', path: '/timeline' },
    { label: 'Go to Graph', path: '/graph' },
    { label: 'Go to World Model', path: '/world' },
    { label: 'Go to Simulation', path: '/simulation' },
    { label: 'Go to Beta Reader', path: '/beta-reader' },
    { label: 'Go to Consistency', path: '/consistency' },
    { label: 'Go to Publish', path: '/publish' },
    { label: 'Go to Insights', path: '/insights' },
  ];

  const filtered = options.filter(o => o.label.toLowerCase().includes(search.toLowerCase()));

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
      <div className="w-full max-w-lg bg-[#252526] border border-[#333333] shadow-2xl rounded-lg overflow-hidden">
        <div className="flex items-center px-4 border-b border-[#333333]">
          <Search size={18} className="text-[#888888]" />
          <input 
            autoFocus
            className="w-full p-4 bg-transparent outline-none text-[#cccccc]"
            placeholder="Search activities..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="max-h-80 overflow-y-auto">
          {filtered.map(opt => (
            <div 
              key={opt.path}
              className="px-4 py-3 hover:bg-[#007acc] hover:text-white cursor-pointer transition-colors"
              onClick={() => {
                navigate(opt.path);
                toggleCommandPalette(false);
              }}
            >
              {opt.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

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
                <div className="text-sm text-[#888888] uppercase mb-1">Character</div>
                <div className="text-lg font-semibold truncate">{char?.name || 'New Character'}</div>
                <div className="mt-4 text-xs text-[#666666] leading-relaxed">{char?.background}</div>
            </div>
        );
    }

    return (
        <div className="p-4 text-[#888888] italic text-sm">Select an item to inspect</div>
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
    <div className="p-8" data-testid={testId}>
      <h1 className="text-3xl font-bold mb-4">{title}</h1>
      <p className="text-[#888888] mb-8">This is a skeleton for the {title} activity.</p>
    </div>
  );
};

const Toast = () => {
    const { lastActionStatus } = useUIStore();
    if (!lastActionStatus) return null;
    return (
        <div className="fixed bottom-10 right-10 z-[100] bg-[#2e7d32] text-white px-6 py-3 rounded-lg shadow-2xl font-bold">
            {lastActionStatus}
        </div>
    );
};

// LAYOUT
const AppContent = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedEntity, characters, timelineEvents } = useProjectStore();
  const { toggleCommandPalette } = useUIStore();

  const activities = [
    { id: 'workbench', path: '/workbench', label: 'Workbench', icon: <Terminal size={24} />, testId: 'activity-btn-workbench' },
    { id: 'writing', path: '/writing', label: 'Writing Studio', icon: <PenTool size={24} />, testId: 'activity-btn-writing' },
    { id: 'characters', path: '/characters', label: 'Characters', icon: <Users size={24} />, testId: 'activity-btn-characters' },
    { id: 'timeline', path: '/timeline', label: 'Timeline', icon: <Clock size={24} />, testId: 'activity-btn-timeline' },
    { id: 'graph', path: '/graph', label: 'Graph', icon: <Network size={24} />, testId: 'activity-btn-graph' },
    { id: 'world', path: '/world', label: 'World Model', icon: <Globe size={24} />, testId: 'activity-btn-world' },
    { id: 'simulation', path: '/simulation', label: 'Simulation', icon: <PlayCircle size={24} />, testId: 'activity-btn-simulation' },
    { id: 'beta', path: '/beta-reader', label: 'Beta Reader', icon: <FileText size={24} />, testId: 'activity-btn-beta' },
    { id: 'consistency', path: '/consistency', label: 'Consistency', icon: <CheckCircle size={24} />, testId: 'activity-btn-consistency' },
    { id: 'publish', path: '/publish', label: 'Publish', icon: <Layout size={24} />, testId: 'activity-btn-publish' },
    { id: 'insights', path: '/insights', label: 'Insights', icon: <BarChart2 size={24} />, testId: 'activity-btn-insights' },
  ];

  const currentActivityId = activities.find(a => location.pathname.startsWith(a.path))?.id || 'workbench';
  
  const selectedLabel = selectedEntity.type === 'character' 
    ? characters.find(c => c.id === selectedEntity.id)?.name || 'New Character'
    : selectedEntity.type === 'timeline_event'
    ? timelineEvents.find(e => e.id === selectedEntity.id)?.title || 'New Event'
    : selectedEntity.id || 'None';

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <CommandPalette />
      <Toast />
      
      {/* Top Toolbar */}
      <header className="h-[var(--top-toolbar-height)] bg-[#252526] border-b border-[#333333] flex items-center justify-between px-4 z-10" data-testid="top-toolbar">
        <div className="flex items-center gap-4">
          <div className="font-bold text-white tracking-tight">NARRATIVE IDE</div>
          <div className="text-xs px-2 py-1 bg-[#333333] rounded text-[#888888]">Windows Demo</div>
        </div>
        <div className="flex items-center gap-2">
          <button 
            data-testid="toggle-command-palette"
            className="p-1.5 hover:bg-[#333333] rounded"
            onClick={() => toggleCommandPalette()}
          >
            <Search size={16} />
          </button>
          <button className="p-1.5 hover:bg-[#333333] rounded"><Settings size={16} /></button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Activity Bar */}
        <nav className="w-[var(--activity-bar-width)] bg-[#252526] border-r border-[#333333] flex flex-col items-center pt-4" data-testid="activity-bar">
          {activities.map((activity) => (
            <div
              key={activity.id}
              className={cnLocal(
                "activity-btn",
                currentActivityId === activity.id && "active bg-[#333333]"
              )}
              onClick={() => navigate(activity.path)}
              title={activity.label}
              data-testid={activity.testId}
            >
              {React.cloneElement(activity.icon as React.ReactElement, { 
                className: currentActivityId === activity.id ? "text-white" : "text-[#888888]" 
              })}
            </div>
          ))}
        </nav>

        {/* Sidebar */}
        <aside className="w-[var(--sidebar-width)] bg-[#252526] border-r border-[#333333] flex flex-col" data-testid="sidebar">
          <div className="p-3 border-b border-[#333333] flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#888888]">{currentActivityId}</span>
          </div>
          <div className="flex-1 overflow-y-auto" data-testid={`sidebar-section-${currentActivityId}-list`}>
            <div className="p-4 text-sm text-[#666666] italic">View modes...</div>
          </div>
        </aside>

        {/* Workspace */}
        <main className="flex-1 bg-[#121212] overflow-auto relative" data-testid="workspace">
          <Routes>
            <Route path="/" element={<PlaceholderPage title="Workbench" testId="agent-console" />} />
            <Route path="/workbench/*" element={<PlaceholderPage title="Workbench" testId="agent-console" />} />
            <Route path="/writing/*" element={<WritingWorkspace />} />
            <Route path="/characters/*" element={<CharactersWorkspace />} />
            <Route path="/timeline/*" element={<TimelineWorkspace />} />
            <Route path="/graph/*" element={<PlaceholderPage title="Graph" testId="graph-canvas" />} />
            <Route path="/world/*" element={<PlaceholderPage title="World Model" testId="world-container-list" />} />
            <Route path="/simulation/*" element={<PlaceholderPage title="Simulation" testId="simulation-runs" />} />
            <Route path="/beta-reader/*" element={<PlaceholderPage title="Beta Reader" testId="beta-reader-preview" />} />
            <Route path="/consistency/*" element={<PlaceholderPage title="Consistency" testId="consistency-issue-list" />} />
            <Route path="/publish/*" element={<PlaceholderPage title="Publish" testId="publish-preview" />} />
            <Route path="/insights/*" element={<PlaceholderPage title="Insights" testId="insight-wordcount" />} />
          </Routes>
        </main>

        <Inspector />
      </div>

      {/* Status Bar */}
      <footer className="h-[var(--status-bar-height)] bg-[#007acc] text-white flex items-center justify-between px-3 text-[11px] font-medium" data-testid="status-bar">
        <div className="flex items-center gap-4">
          <span>PROJECT: Seed Project</span>
          <span className="uppercase">Selection: {selectedLabel}</span>
        </div>
        <div className="flex items-center gap-3">
          <span>UTF-8</span>
          <span>READY</span>
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
