import React from 'react';
import { 
  Layout, Users, Clock, Network, Globe, 
  PlayCircle, CheckCircle, FileText, PenTool, 
  BarChart2, Terminal
} from 'lucide-react';

export interface RouteConfig {
  id: string;
  path: string;
  label: string;
  icon: React.ReactNode;
  testId: string;
  sidebarSections: { id: string; label: string }[];
  sidebarActions?: { label: string; icon: React.ReactNode; testId: string }[];
}

// Fallback empty actions
const noActions: any[] = [];

export const APP_ROUTES: RouteConfig[] = [
  {
    id: 'workbench',
    path: '/workbench',
    label: 'Workbench',
    icon: <Terminal size={20} />,
    testId: 'activity-btn-workbench',
    sidebarSections: [
      { id: 'console', label: 'Agent Console' },
      { id: 'prompts', label: 'Prompt Library' },
      { id: 'history', label: 'AI History' },
      { id: 'logs', label: 'System Logs' },
    ],
  },
  {
    id: 'writing',
    path: '/writing',
    label: 'Writing Studio',
    icon: <PenTool size={20} />,
    testId: 'activity-btn-writing',
    sidebarSections: [
      { id: 'chapters', label: 'Chapters' },
      { id: 'scenes', label: 'Scenes' },
      { id: 'pov', label: 'POV Characters' },
      { id: 'beats', label: 'Story Beats' },
    ],
  },
  {
    id: 'characters',
    path: '/characters',
    label: 'Characters',
    icon: <Users size={20} />,
    testId: 'activity-btn-characters',
    sidebarSections: [
      { id: 'list', label: 'Character List' },
      { id: 'candidates', label: 'Candidate Queue' },
      { id: 'relationships', label: 'Relationships' },
      { id: 'tags', label: 'Tags' },
    ],
  },
  {
    id: 'timeline',
    path: '/timeline',
    label: 'Timeline',
    icon: <Clock size={20} />,
    testId: 'activity-btn-timeline',
    sidebarSections: [
      { id: 'events', label: 'Events' },
      { id: 'locations', label: 'Locations' },
      { id: 'chapters', label: 'Chapters' },
      { id: 'branches', label: 'Branches' },
    ],
  },
  {
    id: 'graph',
    path: '/graph',
    label: 'Graph',
    icon: <Network size={20} />,
    testId: 'activity-btn-graph',
    sidebarSections: [
      { id: 'narrative', label: 'Narrative Graph' },
      { id: 'relationships', label: 'Relationship Graph' },
      { id: 'causality', label: 'Causality Graph' },
      { id: 'locations', label: 'Location Graph' },
    ],
  },
  {
    id: 'world',
    path: '/world',
    label: 'World Model',
    icon: <Globe size={20} />,
    testId: 'activity-btn-world',
    sidebarSections: [
      { id: 'notebooks', label: 'Notebooks' },
      { id: 'maps', label: 'Maps' },
      { id: 'organizations', label: 'Organizations' },
      { id: 'lore', label: 'Lore' },
    ],
  },
  {
    id: 'simulation',
    path: '/simulation',
    label: 'Simulation',
    icon: <PlayCircle size={20} />,
    testId: 'activity-btn-simulation',
    sidebarSections: [
      { id: 'runs', label: 'Runs' },
      { id: 'scenarios', label: 'Scenarios' },
      { id: 'comparisons', label: 'Comparisons' },
      { id: 'reports', label: 'Reports' },
    ],
  },
  {
    id: 'beta-reader',
    path: '/beta-reader',
    label: 'Beta Reader',
    icon: <FileText size={20} />,
    testId: 'activity-btn-beta',
    sidebarSections: [
      { id: 'feedback', label: 'Feedback' },
      { id: 'personas', label: 'Personas' },
    ],
  },
  {
    id: 'consistency',
    path: '/consistency',
    label: 'Consistency',
    icon: <CheckCircle size={20} />,
    testId: 'activity-btn-consistency',
    sidebarSections: [
      { id: 'categories', label: 'Categories' },
      { id: 'issues', label: 'Issues' },
      { id: 'ignored', label: 'Ignored' },
    ],
  },
  {
    id: 'publish',
    path: '/publish',
    label: 'Publish',
    icon: <Layout size={20} />,
    testId: 'activity-btn-publish',
    sidebarSections: [
      { id: 'formats', label: 'Formats' },
      { id: 'metadata', label: 'Metadata' },
      { id: 'preview', label: 'Preview' },
      { id: 'assets', label: 'Assets' },
    ],
  },
  {
    id: 'insights',
    path: '/insights',
    label: 'Insights',
    icon: <BarChart2 size={20} />,
    testId: 'activity-btn-insights',
    sidebarSections: [
      { id: 'project_stats', label: 'Project Stats' },
      { id: 'character_stats', label: 'Character Stats' },
      { id: 'pacing', label: 'Pacing' },
      { id: 'narrative', label: 'Narrative Insights' },
    ],
  }
];

export const getRouteConfig = (id: string): RouteConfig => {
  return APP_ROUTES.find(r => r.id === id) || APP_ROUTES[0];
};
