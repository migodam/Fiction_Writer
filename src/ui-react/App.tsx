import React from 'react';
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
  Terminal 
} from 'lucide-react';

// SKELETON PAGES
const PlaceholderPage = ({ title, testId }: { title: string, testId: string }) => (
  <div style={{ padding: '20px' }} data-testid={testId}>
    <h1>{title}</h1>
    <p>This is a skeleton for the {title} activity.</p>
  </div>
);

const AppContent = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const activities = [
    { id: 'workbench', path: '/workbench', label: 'Workbench', icon: <Terminal />, testId: 'activity-btn-workbench' },
    { id: 'writing', path: '/writing', label: 'Writing Studio', icon: <PenTool />, testId: 'activity-btn-writing' },
    { id: 'characters', path: '/characters', label: 'Characters', icon: <Users />, testId: 'activity-btn-characters' },
    { id: 'timeline', path: '/timeline', label: 'Timeline', icon: <Clock />, testId: 'activity-btn-timeline' },
    { id: 'graph', path: '/graph', label: 'Graph', icon: <Network />, testId: 'activity-btn-graph' },
    { id: 'world', path: '/world', label: 'World Model', icon: <Globe />, testId: 'activity-btn-world' },
    { id: 'simulation', path: '/simulation', label: 'Simulation', icon: <PlayCircle />, testId: 'activity-btn-simulation' },
    { id: 'beta', path: '/beta-reader', label: 'Beta Reader', icon: <FileText />, testId: 'activity-btn-beta' },
    { id: 'consistency', path: '/consistency', label: 'Consistency', icon: <CheckCircle />, testId: 'activity-btn-consistency' },
    { id: 'publish', path: '/publish', label: 'Publish', icon: <Layout />, testId: 'activity-btn-publish' },
    { id: 'insights', path: '/insights', label: 'Insights', icon: <BarChart2 />, testId: 'activity-btn-insights' },
  ];

  const currentActivityId = activities.find(a => location.pathname.startsWith(a.path))?.id || 'workbench';

  return (
    <div className="app-container">
      <header className="top-toolbar" data-testid="top-toolbar">
        <div style={{ fontWeight: 'bold' }}>Fiction Writer IDE</div>
      </header>

      <div className="main-layout">
        <nav className="activity-bar" data-testid="activity-bar">
          {activities.map((activity) => (
            <div
              key={activity.id}
              className={`activity-btn ${currentActivityId === activity.id ? 'active' : ''}`}
              onClick={() => navigate(activity.path)}
              title={activity.label}
              data-testid={activity.testId}
            >
              {activity.icon}
            </div>
          ))}
        </nav>

        <aside className="sidebar" data-testid="sidebar">
          <div style={{ padding: '10px', borderBottom: '1px solid var(--border-color)' }}>
            <strong>{activities.find(a => a.id === currentActivityId)?.label}</strong>
          </div>
          {/* Sidebar sections will be added here in later iterations */}
          <div data-testid={`sidebar-section-${currentActivityId}-list`} style={{ padding: '10px' }}>
             Sidebar Content
          </div>
        </aside>

        <main className="workspace" data-testid="workspace">
          <Routes>
            <Route path="/" element={<PlaceholderPage title="Workbench" testId="agent-console" />} />
            <Route path="/workbench/*" element={<PlaceholderPage title="Workbench" testId="agent-console" />} />
            <Route path="/writing/*" element={<PlaceholderPage title="Writing Studio" testId="writing-editor" />} />
            <Route path="/characters/*" element={<PlaceholderPage title="Characters" testId="character-list" />} />
            <Route path="/timeline/*" element={<PlaceholderPage title="Timeline" testId="timeline-canvas" />} />
            <Route path="/graph/*" element={<PlaceholderPage title="Graph" testId="graph-canvas" />} />
            <Route path="/world/*" element={<PlaceholderPage title="World Model" testId="world-container-list" />} />
            <Route path="/simulation/*" element={<PlaceholderPage title="Simulation" testId="simulation-runs" />} />
            <Route path="/beta-reader/*" element={<PlaceholderPage title="Beta Reader" testId="beta-reader-preview" />} />
            <Route path="/consistency/*" element={<PlaceholderPage title="Consistency" testId="consistency-issue-list" />} />
            <Route path="/publish/*" element={<PlaceholderPage title="Publish" testId="publish-preview" />} />
            <Route path="/insights/*" element={<PlaceholderPage title="Insights" testId="insight-wordcount" />} />
          </Routes>
        </main>

        <aside className="inspector" data-testid="inspector">
          <div style={{ padding: '10px' }}>Global Inspector</div>
        </aside>
      </div>

      <footer className="status-bar" data-testid="status-bar">
        Ready
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
