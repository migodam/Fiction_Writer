import React from 'react';
import { useUIStore } from '../store';
import { 
  Terminal, Users, Clock, Network, Globe, 
  PenTool, PlayCircle, CheckCircle, FileText, 
  BarChart2, Plus, Filter, SortAsc, Layout
} from 'lucide-react';

const XCircle = ({ size }: { size: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
);

interface SidebarConfig {
  [key: string]: {
    sections: { id: string; label: string; icon?: React.ReactNode }[];
    actions: { label: string; icon: React.ReactNode; testId: string }[];
  };
}

const sidebarConfig: SidebarConfig = {
  workbench: {
    sections: [
      { id: 'console', label: 'Agent Console' },
      { id: 'prompts', label: 'Prompt Library' },
      { id: 'history', label: 'AI History' },
      { id: 'logs', label: 'System Logs' },
    ],
    actions: [
      { label: 'Run Prompt', icon: <PlayCircle size={14} />, testId: 'sidebar-action-run' },
      { label: 'Clear', icon: <XCircle size={14} />, testId: 'sidebar-action-clear' },
    ],
  },
  characters: {
    sections: [
      { id: 'list', label: 'Character List' },
      { id: 'candidates', label: 'Candidate Queue' },
      { id: 'relationships', label: 'Relationships' },
      { id: 'tags', label: 'Tags' },
    ],
    actions: [
      { label: 'New Character', icon: <Plus size={14} />, testId: 'sidebar-action-new-character' },
      { label: 'Filter', icon: <Filter size={14} />, testId: 'sidebar-action-filter' },
    ],
  },
  timeline: {
    sections: [
      { id: 'events', label: 'Events' },
      { id: 'locations', label: 'Locations' },
      { id: 'chapters', label: 'Chapters' },
      { id: 'branches', label: 'Branches' },
    ],
    actions: [
      { label: 'Add Event', icon: <Plus size={14} />, testId: 'sidebar-action-add-event' },
      { label: 'Sort', icon: <SortAsc size={14} />, testId: 'sidebar-action-sort' },
    ],
  },
  writing: {
    sections: [
      { id: 'chapters', label: 'Chapters' },
      { id: 'scenes', label: 'Scenes' },
      { id: 'pov', label: 'POV Characters' },
      { id: 'beats', label: 'Story Beats' },
    ],
    actions: [
      { label: 'New Scene', icon: <Plus size={14} />, testId: 'sidebar-action-new-scene' },
    ],
  },
};

// Fallback for activities not yet fully configured
const getFallbackConfig = (id: string) => ({
  sections: [{ id: 'default', label: `${id.charAt(0).toUpperCase() + id.slice(1)} View` }],
  actions: [],
});

export const Sidebar = () => {
  const { currentActivity, sidebarSection, setSidebarSection } = useUIStore();
  const config = sidebarConfig[currentActivity] || getFallbackConfig(currentActivity);

  return (
    <aside className="w-[var(--sidebar-width)] bg-[#252526] border-r border-[#333333] flex flex-col" data-testid="sidebar">
      {/* Sidebar Header */}
      <div className="p-3 border-b border-[#333333] flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-widest text-[#888888]">{currentActivity}</span>
      </div>

      {/* Sections / View Modes */}
      <div className="flex-1 overflow-y-auto py-2">
        {config.sections.map(section => (
          <div
            key={section.id}
            data-testid={`sidebar-section-${currentActivity}-${section.id}`}
            className={`px-4 py-2 text-sm cursor-pointer flex items-center gap-2 transition-colors ${
              sidebarSection === section.id ? 'bg-[#37373d] text-white font-medium' : 'text-[#cccccc] hover:bg-[#2a2d2e]'
            }`}
            onClick={() => setSidebarSection(section.id)}
          >
            {section.label}
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      {config.actions.length > 0 && (
        <div className="p-2 border-t border-[#333333] grid grid-cols-1 gap-1">
          {config.actions.map(action => (
            <button
              key={action.testId}
              data-testid={action.testId}
              className="flex items-center gap-2 px-3 py-1.5 text-[11px] text-[#cccccc] hover:bg-[#37373d] hover:text-white rounded transition-colors"
            >
              {action.icon}
              {action.label}
            </button>
          ))}
        </div>
      )}
    </aside>
  );
};
