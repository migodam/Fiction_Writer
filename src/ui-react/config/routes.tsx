import React from 'react';
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
      { id: 'bulk', label: 'Bulk Actions' },
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
      { id: 'location', label: 'Location Graph' },
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
      { id: 'project', label: 'Project Stats' },
      { id: 'characters', label: 'Character Stats' },
      { id: 'pacing', label: 'Pacing' },
      { id: 'narrative', label: 'Narrative Insights' },
    ],
  }
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
