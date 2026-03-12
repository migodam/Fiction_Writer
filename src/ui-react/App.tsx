import React, { useEffect, useRef, useState } from 'react';
import { BrowserRouter as Router, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  Bot,
  CheckCircle,
  ChevronRight,
  Download,
  FilePlus,
  FolderOpen,
  Gauge,
  Keyboard,
  LayoutPanelTop,
  PanelLeft,
  Redo,
  Save,
  Search,
  Settings,
  Undo,
  X,
} from 'lucide-react';
import { useProjectStore, useUIStore } from './store';
import { APP_ROUTES, getActivityEntryPath, getSidebarSectionFromPath } from './config/routes';
import { Sidebar } from './components/Sidebar';
import { CharactersWorkspace } from './components/CharactersWorkspace';
import { TimelineWorkspace } from './components/TimelineWorkspace';
import { WritingWorkspace } from './components/WritingWorkspace';
import { GraphWorkspace } from './components/GraphWorkspace';
import { WorldWorkspace } from './components/WorldWorkspace';
import { SimulationWorkspace } from './components/SimulationWorkspace';
import { ConsistencyWorkspace } from './components/ConsistencyWorkspace';
import { BetaReaderWorkspace } from './components/BetaReaderWorkspace';
import { WorkbenchWorkspace } from './components/WorkbenchWorkspace';
import { EventInspector } from './components/EventInspector';
import { AgentDock } from './components/AgentDock';
import { PublishWorkspace } from './components/PublishWorkspace';
import { InsightsWorkspace } from './components/InsightsWorkspace';
import { electronApi } from './services/electronApi';
import { useI18n } from './i18n';
import type { CreateProjectInput } from './models/project';
import { cn } from './utils';
import { PaneResizeHandle } from './components/PaneResizeHandle';
import { ContextMenu } from './components/ContextMenu';

type CommandOption = {
  label: string;
  path: string;
  type: string;
  id?: string;
  description?: string;
};

type ProjectDialogState = {
  mode: 'create' | 'open';
  name: string;
  folder: string;
  template: CreateProjectInput['template'];
};

const CommandPalette = () => {
  const { isCommandPaletteOpen, toggleCommandPalette } = useUIStore();
  const { searchEntities, setSelectedEntity } = useProjectStore();
  const { t } = useI18n();
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const activityOptions: CommandOption[] = APP_ROUTES.map((route) => ({
    label: t(`routes.${route.id}.label`, route.label),
    path: getActivityEntryPath(route.id),
    type: 'activity',
  }));

  const entityResults: CommandOption[] = searchEntities(search).map((entry) => ({
    label: entry.label,
    description: entry.description,
    path:
      entry.type === 'character'
        ? `/characters/profile/${entry.id}`
        : entry.type === 'candidate'
        ? '/characters/candidates'
        : entry.type === 'timeline_event'
        ? `/timeline/events?event=${entry.id}`
        : entry.type === 'world_item'
        ? '/world/lore'
        : entry.type === 'scene'
        ? '/writing/scenes'
        : '/workbench/inbox',
    type: entry.type,
    id: entry.id,
  }));

  const allResults = [
    ...activityOptions.filter((item) => item.label.toLowerCase().includes(search.toLowerCase())),
    ...entityResults,
  ];

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'p') {
        event.preventDefault();
        toggleCommandPalette();
      }
      if (event.key === 'Escape') {
        toggleCommandPalette(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleCommandPalette]);

  if (!isCommandPaletteOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-20" data-testid="command-palette">
      <div className="w-full max-w-lg overflow-hidden rounded-lg border border-border bg-bg-elev-1 shadow-2">
        <div className="flex items-center border-b border-border px-4">
          <Search size={18} className="text-text-2" />
          <input
            autoFocus
            className="w-full bg-transparent p-4 text-text outline-none"
            placeholder={t('command.searchPlaceholder')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="max-h-80 overflow-y-auto py-2">
          {allResults.length > 0 ? (
            allResults.map((item, index) => (
              <button
                type="button"
                key={`${item.label}-${index}`}
                className="flex w-full items-center justify-between px-4 py-2 text-left transition-colors hover:bg-brand hover:text-white"
                onClick={() => {
                  if (item.type !== 'activity' && item.id) {
                    setSelectedEntity(item.type as any, item.id);
                  }
                  navigate(item.path);
                  toggleCommandPalette(false);
                  setSearch('');
                }}
              >
                <span className="flex flex-col">
                  <span className="text-sm font-medium">{item.label}</span>
                  {item.description && <span className="text-[10px] uppercase tracking-[0.2em] opacity-60">{item.description}</span>}
                </span>
                <ChevronRight size={14} className="opacity-50" />
              </button>
            ))
          ) : (
            <div className="px-4 py-8 text-center text-xs font-bold uppercase tracking-[0.3em] text-text-3">{t('command.noResults')}</div>
          )}
        </div>
      </div>
    </div>
  );
};

const ToolbarButton = ({
  icon,
  title,
  onClick,
  testId,
}: {
  icon: React.ReactNode;
  title: string;
  onClick?: () => void;
  testId?: string;
}) => (
  <button
    type="button"
    className="rounded p-1.5 text-text-2 transition-colors hover:bg-hover hover:text-text"
    title={title}
    onClick={onClick}
    data-testid={testId}
  >
    {icon}
  </button>
);

const TopToolbar = ({
  onCreateProject,
  onOpenProject,
}: {
  onCreateProject: () => void;
  onOpenProject: () => void;
}) => {
  const { toggleCommandPalette, toggleAgentDock, toggleSidebar, toggleSettings, isSidebarCollapsed } = useUIStore();
  const { saveProject, saveStatus, projectName } = useProjectStore();
  const { t } = useI18n();

  return (
    <header className="h-top-toolbar border-b border-border bg-bg-elev-1 px-2" data-testid="top-toolbar">
      <div className="flex h-full items-center justify-between gap-4">
        <div className="flex items-center gap-1">
          <div className="mr-2 flex items-center gap-2 border-r border-border px-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-brand text-xs font-bold text-white">F</div>
            <div className="flex flex-col">
              <span className="text-[11px] font-bold tracking-tight text-text">{t('app.title')}</span>
              <span className="text-[9px] uppercase tracking-[0.25em] text-text-3">{projectName}</span>
            </div>
          </div>
          <ToolbarButton icon={<PanelLeft size={14} />} title={t('toolbar.toggleSidebar')} onClick={() => toggleSidebar(!isSidebarCollapsed)} testId="toolbar-toggle-sidebar" />
          <ToolbarButton icon={<FilePlus size={14} />} title={t('toolbar.newProject')} onClick={onCreateProject} testId="toolbar-new-project" />
          <ToolbarButton icon={<FolderOpen size={14} />} title={t('toolbar.openProject')} onClick={onOpenProject} testId="toolbar-open-project" />
          <ToolbarButton
            icon={<Save size={14} className={saveStatus === 'Unsaved changes' ? 'text-brand' : ''} />}
            title={t('toolbar.saveProject')}
            onClick={() => saveProject()}
            testId="toolbar-save"
          />
          <div className="mx-1 h-4 w-px bg-border"></div>
          <ToolbarButton icon={<Undo size={14} />} title={t('toolbar.undo')} />
          <ToolbarButton icon={<Redo size={14} />} title={t('toolbar.redo')} />
          <div className="mx-1 h-4 w-px bg-border"></div>
          <ToolbarButton icon={<Activity size={14} />} title={t('toolbar.runSimulation')} />
          <ToolbarButton icon={<CheckCircle size={14} />} title={t('toolbar.checkConsistency')} />
          <ToolbarButton icon={<Download size={14} />} title={t('toolbar.exportBook')} />
        </div>

        <button
          type="button"
          className="flex flex-1 items-center gap-2 rounded border border-border bg-bg px-3 py-1 text-left text-text-2 transition-colors hover:border-border-2"
          onClick={() => toggleCommandPalette()}
          data-testid="global-search"
        >
          <Search size={12} />
          <span className="text-[11px]">{t('toolbar.searchPlaceholder')}</span>
        </button>

        <div className="flex items-center gap-1">
          <ToolbarButton icon={<Bot size={14} />} title={t('toolbar.toggleAgentDock')} onClick={() => toggleAgentDock()} testId="ai-assistant" />
          <ToolbarButton icon={<Settings size={14} />} title={t('toolbar.settings')} onClick={() => toggleSettings(true)} testId="toolbar-settings" />
        </div>
      </div>
    </header>
  );
};

const Inspector = () => {
  const { selectedEntity, characters, timelineEvents, proposals, issues } = useProjectStore();
  const { t } = useI18n();

  const renderContent = () => {
    if (selectedEntity.type === 'timeline_event') {
      return <EventInspector />;
    }

    if (selectedEntity.type === 'character') {
      const character = characters.find((entry) => entry.id === selectedEntity.id);
      return (
        <div className="p-4">
          <div className="mb-1 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('inspector.characterProfile')}</div>
          <div className="text-lg font-semibold text-brand-2">{character?.name || 'Character'}</div>
          <div className="mt-4 border-t border-border pt-4 text-xs leading-relaxed text-text-2">{character?.background}</div>
        </div>
      );
    }

    if (selectedEntity.type === 'proposal') {
      const proposal = proposals.find((entry) => entry.id === selectedEntity.id);
      return (
        <div className="p-4">
          <div className="mb-1 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('inspector.workbenchProposal')}</div>
          <div className="text-lg font-semibold text-brand-2">{proposal?.title || 'Proposal'}</div>
          <div className="mt-4 rounded-xl border border-border bg-bg p-4 text-xs leading-relaxed text-text-2">{proposal?.preview}</div>
        </div>
      );
    }

    if (selectedEntity.type === 'issue') {
      const issue = issues.find((entry) => entry.id === selectedEntity.id);
      return (
        <div className="p-4">
          <div className="mb-1 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('inspector.issue')}</div>
          <div className="text-lg font-semibold text-brand-2">{issue?.title || 'Issue'}</div>
          <div className="mt-4 rounded-xl border border-border bg-bg p-4 text-xs leading-relaxed text-text-2">{issue?.description}</div>
        </div>
      );
    }

    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-text-3">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full border-2 border-dashed border-border">
          <Search size={20} />
        </div>
        <div className="text-xs font-black uppercase tracking-[0.25em] text-text-3">{t('inspector.noSelection')}</div>
        <p className="mt-2 text-[10px] leading-relaxed text-text-2">{t('inspector.noSelectionBody')}</p>
      </div>
    );
  };

  return (
    <aside className="h-full border-l border-border bg-bg-elev-1 overflow-hidden" data-testid="inspector">
      {renderContent()}
    </aside>
  );
};

const Toast = () => {
  const { lastActionStatus } = useUIStore();
  if (!lastActionStatus) {
    return null;
  }

  return (
    <div className="fixed bottom-12 right-12 z-[100] rounded bg-brand px-6 py-2 text-xs font-black uppercase tracking-[0.25em] text-white shadow-2">
      {lastActionStatus}
    </div>
  );
};

const ProjectDialog = ({
  state,
  onChange,
  onChooseFolder,
  onSubmit,
  onClose,
  validationError,
}: {
  state: ProjectDialogState;
  onChange: (next: Partial<ProjectDialogState>) => void;
  onChooseFolder: () => void;
  onSubmit: () => void;
  onClose: () => void;
  validationError: string | null;
}) => {
  const { t } = useI18n();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" data-testid="project-dialog">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-bg-elev-1 shadow-2">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
              {state.mode === 'create' ? t('projectDialog.createTitle') : t('projectDialog.openTitle')}
            </div>
            <div className="mt-1 text-lg font-black text-text">{state.mode === 'create' ? t('toolbar.newProject') : t('toolbar.openProject')}</div>
          </div>
          <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="space-y-5 px-6 py-6">
          {state.mode === 'create' && (
            <label className="block">
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('projectDialog.projectName')}</div>
              <input
                className="w-full rounded-xl border border-border bg-bg px-4 py-3 text-text outline-none"
                value={state.name}
                onChange={(event) => onChange({ name: event.target.value })}
                data-testid="project-name-input"
              />
            </label>
          )}
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('projectDialog.projectFolder')}</div>
            <div className="flex gap-3">
              <input className="flex-1 rounded-xl border border-border bg-bg px-4 py-3 text-text outline-none" value={state.folder} readOnly data-testid="project-folder-input" />
              <button type="button" className="rounded-xl border border-border px-4 py-3 text-sm text-text transition-colors hover:border-brand" onClick={onChooseFolder} data-testid="project-folder-pick">
                {t('projectDialog.chooseFolder')}
              </button>
            </div>
          </label>
          {state.mode === 'create' && (
            <label className="block">
              <div className="mb-2 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('projectDialog.template')}</div>
              <select
                className="w-full rounded-xl border border-border bg-bg px-4 py-3 text-text outline-none"
                value={state.template}
                onChange={(event) => onChange({ template: event.target.value as CreateProjectInput['template'] })}
                data-testid="project-template-select"
              >
                <option value="starter-demo">{t('settings.starter')}</option>
                <option value="blank">{t('settings.blank')}</option>
              </select>
            </label>
          )}
          {validationError && <div className="rounded-xl border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">{validationError}</div>}
        </div>
        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <button type="button" className="rounded-xl border border-border px-4 py-2 text-sm text-text-2" onClick={onClose}>
            {t('projectDialog.cancel')}
          </button>
          <button type="button" className="rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white" onClick={onSubmit} data-testid="project-dialog-submit">
            {state.mode === 'create' ? t('projectDialog.create') : t('projectDialog.open')}
          </button>
        </div>
      </div>
    </div>
  );
};

const SettingsModal = () => {
  const {
    isSettingsOpen,
    toggleSettings,
    locale,
    setLocale,
    resetLayout,
    density,
    setDensity,
    editorWidth,
    setEditorWidth,
    motionLevel,
    setMotionLevel,
  } = useUIStore();
  const { createProject } = useProjectStore();
  const { t } = useI18n();

  if (!isSettingsOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" data-testid="settings-modal">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-bg-elev-1 shadow-2">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('settings.title')}</div>
          </div>
          <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={() => toggleSettings(false)}>
            <X size={16} />
          </button>
        </div>
        <div className="space-y-6 px-6 py-6">
          <section>
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('settings.language')}</div>
            <div className="grid grid-cols-2 gap-3" data-testid="language-switcher">
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', locale === 'en' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setLocale('en')} data-testid="locale-en">{t('settings.english')}</button>
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', locale === 'zh-CN' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setLocale('zh-CN')} data-testid="locale-zh">{t('settings.chinese')}</button>
            </div>
          </section>

          <section>
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('settings.layout')}</div>
            <div className="grid gap-3 md:grid-cols-3">
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', density === 'comfortable' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setDensity('comfortable')}>
                <div className="flex items-center gap-2"><Gauge size={14} /> Comfortable</div>
              </button>
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', density === 'compact' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setDensity('compact')}>
                <div className="flex items-center gap-2"><Gauge size={14} /> Compact</div>
              </button>
              <button type="button" className="rounded-xl border border-border px-4 py-3 text-sm text-text transition-colors hover:border-brand" onClick={resetLayout} data-testid="reset-layout-btn">
                {t('settings.resetLayout')}
              </button>
            </div>
          </section>

          <section>
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Editor Width</div>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', editorWidth === 'focused' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setEditorWidth('focused')}>Focused</button>
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', editorWidth === 'wide' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setEditorWidth('wide')}>Wide</button>
            </div>
          </section>

          <section>
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Motion</div>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', motionLevel === 'full' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setMotionLevel('full')}>
                Full Motion
              </button>
              <button type="button" className={cn('rounded-xl border px-4 py-3 text-sm', motionLevel === 'reduced' ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={() => setMotionLevel('reduced')}>
                Reduced
              </button>
            </div>
          </section>

          <section>
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Shortcuts</div>
            <div className="rounded-2xl border border-border bg-bg px-4 py-4 text-sm text-text-2">
              <div className="flex items-center gap-3"><Keyboard size={14} /> `Ctrl+P` opens the command palette. Right-click now exposes contextual actions across authoring surfaces.</div>
            </div>
          </section>

          <section>
            <div className="mb-3 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{t('settings.projectActions')}</div>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className="rounded-xl border border-border px-4 py-3 text-sm text-text transition-colors hover:border-brand" onClick={() => createProject({ name: 'Starter Demo Project', template: 'starter-demo', locale })} data-testid="quick-starter-project">
                {t('settings.starter')}
              </button>
              <button type="button" className="rounded-xl border border-border px-4 py-3 text-sm text-text transition-colors hover:border-brand" onClick={() => createProject({ name: 'Blank Narrative Project', template: 'blank', locale })} data-testid="quick-blank-project">
                {t('settings.blank')}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

const AppContent = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const initializedRef = useRef(false);
  const { t } = useI18n();
  const [projectDialog, setProjectDialog] = useState<ProjectDialogState | null>(null);
  const [projectDialogError, setProjectDialogError] = useState<string | null>(null);
  const {
    selectedEntity,
    characters,
    timelineEvents,
    projectName,
    projectRoot,
    proposals,
    issues,
    saveStatus,
    openProject,
    createProject,
    setSelectedEntity,
    clearUnreadActivity,
    setProjectLocale,
    syncProjectUiState,
  } = useProjectStore();
  const {
    setActivity,
    setSidebarSection,
    sidebarWidth,
    inspectorWidth,
    agentDockWidth,
    isSidebarCollapsed,
    isAgentDockOpen,
    locale,
    density,
    editorWidth,
    motionLevel,
  } = useUIStore();

  const currentActivityId = APP_ROUTES.find((route) => location.pathname.startsWith(route.path))?.id || 'workbench';

  useEffect(() => {
    setActivity(currentActivityId);
    setSidebarSection(getSidebarSectionFromPath(location.pathname, currentActivityId));
    clearUnreadActivity(currentActivityId);
  }, [clearUnreadActivity, currentActivityId, location.pathname, setActivity, setSidebarSection]);

  useEffect(() => {
    if (initializedRef.current) {
      return;
    }
    initializedRef.current = true;
    void openProject();
  }, [openProject]);

  useEffect(() => {
    setProjectLocale(locale);
  }, [locale, setProjectLocale]);

  useEffect(() => {
    syncProjectUiState();
  }, [sidebarWidth, inspectorWidth, agentDockWidth, isSidebarCollapsed, isAgentDockOpen, density, editorWidth, motionLevel, syncProjectUiState]);

  const selectedLabel =
    selectedEntity.type === 'character'
      ? characters.find((entry) => entry.id === selectedEntity.id)?.name || t('shell.noSelection')
      : selectedEntity.type === 'timeline_event'
      ? timelineEvents.find((entry) => entry.id === selectedEntity.id)?.title || t('shell.noSelection')
      : selectedEntity.type === 'proposal'
      ? proposals.find((entry) => entry.id === selectedEntity.id)?.title || t('inspector.workbenchProposal')
      : selectedEntity.type === 'issue'
      ? issues.find((entry) => entry.id === selectedEntity.id)?.title || t('inspector.issue')
      : t('shell.noSelection');

  const handleChooseDirectory = async () => {
    if (!projectDialog) {
      return;
    }
    const result = await electronApi.pickDirectory(projectDialog.mode === 'create' ? 'create' : 'open');
    if (!result.canceled && result.path) {
      setProjectDialog({ ...projectDialog, folder: result.path });
    }
  };

  const handleCreateProject = () => {
    setProjectDialog({
      mode: 'create',
      name: 'Starter Demo Project',
      folder: '',
      template: 'starter-demo',
    });
    setProjectDialogError(null);
  };

  const handleOpenProject = () => {
    setProjectDialog({
      mode: 'open',
      name: '',
      folder: '',
      template: 'starter-demo',
    });
    setProjectDialogError(null);
  };

  const submitProjectDialog = async () => {
    if (!projectDialog) {
      return;
    }

    const requiresFolder = electronApi.isAvailable();
    if ((requiresFolder && !projectDialog.folder) || (projectDialog.mode === 'create' && !projectDialog.name.trim())) {
      setProjectDialogError(t(requiresFolder ? 'projectDialog.validation' : 'projectDialog.validationBrowser'));
      return;
    }

    if (projectDialog.mode === 'create') {
      const rootPath = electronApi.isAvailable() ? `${projectDialog.folder}/${projectDialog.name}`.replace(/\\/g, '/') : undefined;
      await createProject({
        name: projectDialog.name.trim(),
        rootPath,
        template: projectDialog.template,
        locale,
      });
    } else {
      await openProject(projectDialog.folder || undefined);
    }

    setProjectDialog(null);
    setProjectDialogError(null);
  };

  return (
    <div
      className={cn('flex h-screen flex-col overflow-hidden bg-bg text-text', density === 'compact' && 'text-[13px]')}
      style={{
        ['--sidebar-width' as any]: `${sidebarWidth}px`,
        ['--inspector-width' as any]: `${inspectorWidth}px`,
        ['--agent-dock-width' as any]: `${agentDockWidth}px`,
      }}
    >
      <CommandPalette />
      <SettingsModal />
      <ContextMenu />
      {projectDialog && (
        <ProjectDialog
          state={projectDialog}
          onChange={(next) => setProjectDialog({ ...projectDialog, ...next })}
          onChooseFolder={handleChooseDirectory}
          onSubmit={submitProjectDialog}
          onClose={() => setProjectDialog(null)}
          validationError={projectDialogError}
        />
      )}
      <Toast />
      <TopToolbar onCreateProject={handleCreateProject} onOpenProject={handleOpenProject} />

      <div className="flex flex-1 overflow-hidden">
        <nav className="w-activity-bar border-r border-border bg-bg-elev-2 pt-2" data-testid="activity-bar">
          <div className="flex flex-col items-center gap-1">
            {APP_ROUTES.map((activity) => {
              const isActive = currentActivityId === activity.id;
              return (
                <button
                  type="button"
                  key={activity.id}
                  className={cn('relative flex h-12 w-12 items-center justify-center rounded text-text-2 transition-all hover:text-text', isActive && 'text-brand')}
                  onClick={() => navigate(getActivityEntryPath(activity.id))}
                  title={t(`routes.${activity.id}.label`, activity.label)}
                  data-testid={activity.testId}
                >
                  {isActive && <div className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-brand"></div>}
                  {activity.icon}
                </button>
              );
            })}
          </div>
        </nav>

        <div style={{ width: isSidebarCollapsed ? 0 : sidebarWidth }} className="transition-[width] duration-200 overflow-hidden">
          <Sidebar />
        </div>
        {!isSidebarCollapsed && <PaneResizeHandle panel="sidebar" direction="right" testId="sidebar-resizer" />}

        <main className="flex-1 overflow-hidden bg-bg" data-testid="workspace">
          <Routes>
            <Route path="/" element={<Navigate to="/workbench/inbox" replace />} />
            <Route path="/workbench" element={<Navigate to="/workbench/inbox" replace />} />
            <Route path="/workbench/inbox" element={<WorkbenchWorkspace />} />
            <Route path="/workbench/history" element={<WorkbenchWorkspace />} />
            <Route path="/workbench/issues" element={<WorkbenchWorkspace />} />
            <Route path="/workbench/bulk" element={<WorkbenchWorkspace />} />
            <Route path="/workbench/*" element={<Navigate to="/workbench/inbox" replace />} />
            <Route path="/writing/*" element={<WritingWorkspace />} />
            <Route path="/characters" element={<Navigate to="/characters/list" replace />} />
            <Route path="/characters/list" element={<CharactersWorkspace />} />
            <Route path="/characters/candidates" element={<CharactersWorkspace />} />
            <Route path="/characters/relationships" element={<CharactersWorkspace />} />
            <Route path="/characters/tags" element={<CharactersWorkspace />} />
            <Route path="/characters/profile/:characterId" element={<CharactersWorkspace />} />
            <Route path="/characters/*" element={<Navigate to="/characters/list" replace />} />
            <Route path="/timeline/*" element={<TimelineWorkspace />} />
            <Route path="/graph/*" element={<GraphWorkspace />} />
            <Route path="/world/*" element={<WorldWorkspace />} />
            <Route path="/simulation/*" element={<SimulationWorkspace />} />
            <Route path="/beta-reader/*" element={<BetaReaderWorkspace />} />
            <Route path="/consistency/*" element={<ConsistencyWorkspace />} />
            <Route path="/publish/*" element={<PublishWorkspace />} />
            <Route path="/insights/*" element={<InsightsWorkspace />} />
          </Routes>
        </main>

        <PaneResizeHandle panel="inspector" direction="left" testId="inspector-resizer" />
        <div style={{ width: inspectorWidth }} className="overflow-hidden">
          <Inspector />
        </div>
        {isAgentDockOpen && <PaneResizeHandle panel="agentDock" direction="left" testId="agentDock-resizer" />}
        <div style={{ width: isAgentDockOpen ? agentDockWidth : 56 }} className="overflow-hidden transition-[width] duration-200">
          <AgentDock />
        </div>
      </div>

      <footer className={cn('h-status-bar border-t border-amber-300/20 text-white', editorWidth === 'wide' ? 'bg-slate-900' : 'bg-brand')} data-testid="status-bar">
        <div className="flex h-full items-center justify-between px-3 text-[10px] font-black uppercase tracking-[0.18em]">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2"><span className="opacity-60">{t('shell.project')}</span><span>{projectName}</span></div>
            <div className="flex items-center gap-2"><span className="opacity-60">{t('shell.path')}</span><span className="max-w-[320px] truncate">{projectRoot}</span></div>
            <div className="flex items-center gap-2"><span className="opacity-60">{t('shell.status')}</span><span>{saveStatus}</span></div>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2"><span className="opacity-60">{t('shell.selection')}</span><span>{selectedLabel}</span></div>
            <div className="flex items-center gap-2"><span className="opacity-60">{t('shell.workbench')}</span><span>{proposals.length} pending / {issues.length} issues</span></div>
          </div>
        </div>
      </footer>
    </div>
  );
};

const App = () => (
  <Router>
    <AppContent />
  </Router>
);

export default App;
