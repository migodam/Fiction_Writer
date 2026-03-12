import React from 'react';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useUIStore } from '../store';
import { getRouteConfig, getSectionRoute } from '../config/routes';
import { useI18n } from '../i18n';

export const Sidebar = () => {
  const { currentActivity, sidebarSection, setSidebarSection, isSidebarCollapsed, toggleSidebar } = useUIStore();
  const navigate = useNavigate();
  const config = getRouteConfig(currentActivity);
  const { t } = useI18n();

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
              {t(`routes.${config.id}.sections.${section.id}`, section.label)}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
};
