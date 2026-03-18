import React from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import { getRouteConfig, getSectionRoute } from '../config/routes';
import { useI18n } from '../i18n';

export const Sidebar = () => {
  const { currentActivity, sidebarSection, setSidebarSection, isSidebarCollapsed, toggleSidebar } = useUIStore();
  const {
    proposals,
    proposalHistory,
    issues,
    importJobs,
    taskRuns,
    promptTemplates,
    scripts,
    storyboards,
    videoPackages,
    timelineBranches,
    unreadUpdates,
  } = useProjectStore();
  const navigate = useNavigate();
  const config = getRouteConfig(currentActivity);
  const { t } = useI18n();

  const getSectionBadge = (sectionId: string) => {
    if (currentActivity === 'workbench') {
      if (sectionId === 'inbox') return proposals.length;
      if (sectionId === 'history') return proposalHistory.length;
      if (sectionId === 'issues') return issues.length;
      if (sectionId === 'imports') return importJobs.length;
      if (sectionId === 'runs') return taskRuns.filter((run) => run.status === 'running' || run.status === 'queued' || run.status === 'awaiting_user_input').length;
      if (sectionId === 'prompts') return promptTemplates.length;
    }

    if (currentActivity === 'writing') {
      if (sectionId === 'scripts') return scripts.length;
      if (sectionId === 'storyboards') return storyboards.length;
    }

    if (currentActivity === 'publish' && sectionId === 'video') {
      return videoPackages.length;
    }

    if (currentActivity === 'timeline' && sectionId === 'branches') {
      return timelineBranches.length;
    }

    return 0;
  };

  return (
    <aside className="h-full bg-bg-elev-1 border-r border-border flex flex-col overflow-hidden" data-testid="sidebar">
      <div className="p-3 border-b border-border flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-widest text-text-3 truncate">
          {t(`routes.${config.id}.label`, config.label)}
        </span>
        <button
          type="button"
          className="rounded p-1 text-text-3 transition-colors hover:bg-hover hover:text-text"
          onClick={() => toggleSidebar(!isSidebarCollapsed)}
          title={isSidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')}
          data-testid="sidebar-toggle"
        >
          {isSidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>
      </div>

      {!isSidebarCollapsed && (
        <div className="flex-1 overflow-y-auto py-2">
          {config.sidebarSections.map((section) => (
            <div
              key={section.id}
              data-testid={`sidebar-section-${currentActivity}-${section.id}`}
              className={`px-4 py-2 text-sm cursor-pointer flex items-center gap-2 transition-colors ${
                sidebarSection === section.id
                  ? 'bg-active text-text font-medium border-l-2 border-brand'
                  : 'text-text-2 hover:bg-hover border-l-2 border-transparent'
              }`}
              onClick={() => {
                setSidebarSection(section.id);
                navigate(getSectionRoute(currentActivity, section.id));
              }}
            >
              <span className="truncate">{t(`routes.${config.id}.sections.${section.id}`, section.label)}</span>
              {getSectionBadge(section.id) > 0 && (
                <span className="ml-auto rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-black text-text-3">
                  {getSectionBadge(section.id)}
                </span>
              )}
              {unreadUpdates.sections[`${currentActivity}.${section.id}`] && (
                <span className="h-2 w-2 rounded-full bg-brand" aria-hidden="true" />
              )}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
};
