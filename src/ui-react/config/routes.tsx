import React from 'react';
import {
  Layout,
  Library,
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
  Bot,
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

export const APP_ROUTES: RouteConfig[] = [
  {
    id: 'workbench',
    path: '/workbench',
    label: 'Workbench',
    icon: <Terminal size={20} />,
    testId: 'activity-btn-workbench',
    sidebarSections: [
      { id: 'inbox', label: 'Inbox' },
      { id: 'history', label: 'History' },
      { id: 'issues', label: 'Issues' },
      { id: 'imports', label: 'Imports' },
      { id: 'runs', label: 'Runs' },
      { id: 'prompts', label: 'Prompts' },
    ],
  },
  {
    id: 'writing',
    path: '/writing',
    label: 'Writing Studio',
    icon: <PenTool size={20} />,
    testId: 'activity-btn-writing',
    sidebarSections: [
      { id: 'scenes', label: 'Scenes' },
      { id: 'chapters', label: 'Chapters' },
      { id: 'manuscript', label: 'Manuscript' },
      { id: 'scripts', label: 'Scripts' },
      { id: 'storyboards', label: 'Storyboards' },
    ],
  },
  {
    id: 'characters',
    path: '/characters',
    label: 'Characters',
    icon: <Users size={20} />,
    testId: 'activity-btn-characters',
    sidebarSections: [
      { id: 'overview', label: 'Overview' },
      { id: 'candidates', label: 'Candidate Queue' },
      { id: 'relationship-graph', label: 'Relationship Graph' },
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
      { id: 'timeline', label: 'Timeline' },
    ],
  },
  {
    id: 'graph',
    path: '/graph',
    label: 'Graph',
    icon: <Network size={20} />,
    testId: 'activity-btn-graph',
    sidebarSections: [
      { id: 'boards', label: 'Boards' },
    ],
  },
  {
    id: 'world',
    path: '/world',
    label: 'World Model',
    icon: <Globe size={20} />,
    testId: 'activity-btn-world',
    sidebarSections: [
      { id: 'entries', label: 'Entries' },
      { id: 'map', label: 'Map' },
      { id: 'settings', label: 'Settings' },
    ],
  },
  {
    id: 'simulation',
    path: '/simulation',
    label: 'Simulation',
    icon: <PlayCircle size={20} />,
    testId: 'activity-btn-simulation',
    sidebarSections: [
      { id: 'labs', label: 'Labs' },
      { id: 'reviewers', label: 'Reviewers' },
    ],
  },
  {
    id: 'beta-reader',
    path: '/beta-reader',
    label: 'Beta Reader',
    icon: <FileText size={20} />,
    testId: 'activity-btn-beta',
    sidebarSections: [
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
      { id: 'overview', label: 'Overview' },
    ],
  },
  {
    id: 'agents',
    path: '/agents',
    label: 'Agents',
    icon: <Bot size={20} />,
    testId: 'activity-btn-agents',
    sidebarSections: [
      { id: 'console', label: 'Console' },
    ],
  },
  {
    id: 'publish',
    path: '/publish',
    label: 'Publish',
    icon: <Layout size={20} />,
    testId: 'activity-btn-publish',
    sidebarSections: [
      { id: 'exports', label: 'Exports' },
      { id: 'video', label: 'Video' },
    ],
  },
  {
    id: 'insights',
    path: '/insights',
    label: 'Insights',
    icon: <BarChart2 size={20} />,
    testId: 'activity-btn-insights',
    sidebarSections: [
      { id: 'overview', label: 'Overview' },
    ],
  },
  {
    id: 'metadata',
    path: '/metadata',
    label: 'Reference Library',
    icon: <Library size={20} />,
    testId: 'activity-btn-metadata',
    sidebarSections: [
      { id: 'files', label: 'Files' },
      { id: 'chunks', label: 'Chunks Preview' },
    ],
  },
];

export const getRouteConfig = (id: string): RouteConfig => {
  return APP_ROUTES.find(r => r.id === id) || APP_ROUTES[0];
};

export const getDefaultSection = (activityId: string): string => {
  const config = getRouteConfig(activityId);
  return config.sidebarSections[0]?.id || '';
};

export const getSectionRoute = (activityId: string, sectionId?: string): string => {
  const config = getRouteConfig(activityId);
  const resolvedSection = sectionId || getDefaultSection(activityId);
  return resolvedSection ? `${config.path}/${resolvedSection}` : config.path;
};

export const getActivityEntryPath = (activityId: string): string => {
  return getSectionRoute(activityId, getDefaultSection(activityId));
};

export const getSidebarSectionFromPath = (pathname: string, activityId: string): string => {
  const config = getRouteConfig(activityId);
  const segments = pathname.split('/').filter(Boolean);
  const activitySegment = config.path.replace('/', '');
  const currentIndex = segments.indexOf(activitySegment);
  const nextSegment = currentIndex >= 0 ? segments[currentIndex + 1] : undefined;
  const knownSections = new Set(config.sidebarSections.map((section) => section.id));

  if (!nextSegment) {
    return getDefaultSection(activityId);
  }

  if (knownSections.has(nextSegment)) {
    return nextSegment;
  }

  // Entity detail routes keep the primary list section highlighted.
  return getDefaultSection(activityId);
};
