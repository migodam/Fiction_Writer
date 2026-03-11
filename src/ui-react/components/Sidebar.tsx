import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useUIStore } from '../store';
import { getRouteConfig, getSectionRoute } from '../config/routes';

export const Sidebar = () => {
  const { currentActivity, sidebarSection, setSidebarSection } = useUIStore();
  const navigate = useNavigate();
  const config = getRouteConfig(currentActivity);

  return (
    <aside className="w-sidebar bg-bg-elev-1 border-r border-border flex flex-col" data-testid="sidebar">
      {/* Sidebar Header */}
      <div className="p-3 border-b border-border flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-widest text-text-3">{config.label}</span>
      </div>

      {/* Sections / View Modes */}
      <div className="flex-1 overflow-y-auto py-2">
        {config.sidebarSections.map(section => (
          <div
            key={section.id}
            data-testid={`sidebar-section-${currentActivity}-${section.id}`}
            className={`px-4 py-2 text-sm cursor-pointer flex items-center gap-2 transition-colors ${
              sidebarSection === section.id ? 'bg-active text-text font-medium border-l-2 border-brand' : 'text-text-2 hover:bg-hover border-l-2 border-transparent'
            }`}
            onClick={() => {
              setSidebarSection(section.id);
              navigate(getSectionRoute(currentActivity, section.id));
            }}
          >
            {section.label}
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      {config.sidebarActions && config.sidebarActions.length > 0 && (
        <div className="p-2 border-t border-border grid grid-cols-1 gap-1">
          {config.sidebarActions.map(action => (
            <button
              key={action.testId}
              data-testid={action.testId}
              className="flex items-center gap-2 px-3 py-1.5 text-[11px] text-text-2 hover:bg-hover hover:text-text rounded transition-colors"
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
