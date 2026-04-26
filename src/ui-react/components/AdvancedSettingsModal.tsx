import React, { useMemo, useState, useEffect } from 'react';
import { CheckCircle2, Plus, Save, Settings, Star, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { electronApi } from '../services/electronApi';
import { useI18n } from '../i18n';
import type { PromptTemplate } from '../models/project';

const TABS = ['workspace', 'writing', 'ai', 'import-export', 'appearance', 'prompts', 'advanced'] as const;

export const AdvancedSettingsModal = () => {
  const ui = useUIStore();
  const project = useProjectStore();
  const { t } = useI18n();
  const locale = ui.locale;
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('workspace');
  const [activeProviderId, setActiveProviderId] = useState(
    ui.appSettings.selectedProviderProfileId || ui.appSettings.providerProfiles[0]?.id || ''
  );
  const [activeModelId, setActiveModelId] = useState(
    ui.appSettings.selectedModelProfileId || ui.appSettings.modelProfiles[0]?.id || ''
  );
  const [providerStatus, setProviderStatus] = useState<string | null>(null);

  const selectedProviderProfileId = ui.appSettings.selectedProviderProfileId || ui.appSettings.providerProfiles[0]?.id;
  const selectedModelProfileId = ui.appSettings.selectedModelProfileId || ui.appSettings.modelProfiles[0]?.id;

  const provider = ui.appSettings.providerProfiles.find((entry) => entry.id === activeProviderId) || ui.appSettings.providerProfiles[0];
  const model = ui.appSettings.modelProfiles.find((entry) => entry.id === activeModelId) || ui.appSettings.modelProfiles[0];
  const saveSettings = (partial: Partial<typeof ui.appSettings>) => ui.saveAppSettings(partial);

  const updateProvider = (partial: Partial<typeof provider>) => {
    if (!provider) return;
    saveSettings({ providerProfiles: ui.appSettings.providerProfiles.map((entry) => entry.id === provider.id ? { ...entry, ...partial } : entry) });
  };

  const updateModel = (partial: Partial<typeof model>) => {
    if (!model) return;
    saveSettings({ modelProfiles: ui.appSettings.modelProfiles.map((entry) => entry.id === model.id ? { ...entry, ...partial } : entry) });
  };

  // Prompts tab state
  const promptTemplates = useProjectStore((s) => s.promptTemplates);
  const updatePromptTemplate = useProjectStore((s) => s.updatePromptTemplate);
  const projectRoot = useProjectStore((s) => s.projectRoot);
  const [sidecarPrompts, setSidecarPrompts] = useState<Record<string, { name: string; text: string }[]>>({});
  const [selectedFlowId, setSelectedFlowId] = useState('W1');
  const [selectedPromptName, setSelectedPromptName] = useState('W1_EXTRACT_CHARACTERS_DEEP');
  const [userSlot, setUserSlot] = useState('');
  const [promptSaved, setPromptSaved] = useState(false);

  const FLOW_LABELS: Record<string, string> = {
    W0: t('settings.prompts.w0', 'W0 Orchestrator'),
    W1: t('settings.prompts.w1', 'W1 Import'),
    W2: t('settings.prompts.w2', 'W2 Manuscript Sync'),
    W3: t('settings.prompts.w3', 'W3 Writing'),
    W4: t('settings.prompts.w4', 'W4 Consistency'),
    W5: t('settings.prompts.w5', 'W5 Simulation'),
    W6: t('settings.prompts.w6', 'W6 Beta Reader'),
    W7: t('settings.prompts.w7', 'W7 Metadata'),
  };

  useEffect(() => {
    if (activeTab === 'prompts' && projectRoot && Object.keys(sidecarPrompts).length === 0) {
      electronApi.fetchPrompts(projectRoot).then(setSidecarPrompts).catch(() => {});
    }
  }, [activeTab, projectRoot]);

  useEffect(() => {
    // When prompt selection changes, load the existing user slot from project
    const existing = promptTemplates.find(t => t.id === selectedPromptName);
    setUserSlot(existing?.userCustomPromptSlot ?? '');
    setPromptSaved(false);
  }, [selectedPromptName, promptTemplates]);

  const handleSaveUserSlot = () => {
    const flowPrompts = sidecarPrompts[selectedFlowId] ?? [];
    const basePrompt = flowPrompts.find(p => p.name === selectedPromptName);
    const existing = promptTemplates.find(t => t.id === selectedPromptName);
    const template: PromptTemplate = existing ?? {
      id: selectedPromptName,
      name: selectedPromptName,
      agentType: ('w' + selectedFlowId.toLowerCase().slice(1) + '-agent') as any,
      purpose: basePrompt?.name ?? selectedPromptName,
      inputContract: [],
      outputContract: [],
      reviewPolicy: 'manual_workbench' as const,
      promptTemplate: basePrompt?.text ?? '',
      userCustomPromptSlot: userSlot,
      modelHints: [],
      version: 1,
      promptTemplateSlots: [],
      forbiddenActions: [],
      writeTargets: [],
      requiresWorkbenchReview: false,
    };
    updatePromptTemplate({ ...template, userCustomPromptSlot: userSlot, promptTemplate: basePrompt?.text ?? template.promptTemplate });
    setPromptSaved(true);
    setTimeout(() => setPromptSaved(false), 2000);
  };

  const selectedBaseText = (sidecarPrompts[selectedFlowId] ?? []).find(p => p.name === selectedPromptName)?.text ?? '';

  const labels = useMemo(() => ({
    workspace: t('settings.workspace', 'Workspace'),
    writing: t('settings.writing', 'Writing'),
    ai: t('settings.aiProviders', 'AI Providers & Models'),
    'import-export': t('settings.importExport', 'Import / Export'),
    appearance: t('settings.appearance', 'Appearance'),
    prompts: t('settings.prompts', 'Prompts'),
    advanced: t('settings.advanced', 'Advanced'),
  }), [t]);

  if (!ui.isSettingsOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6" data-testid="settings-modal">
      <div className="flex h-[88vh] w-full max-w-6xl overflow-hidden rounded-[32px] border border-border bg-bg-elev-1 shadow-2">
        <aside className="w-64 border-r border-border bg-bg-elev-2 p-5">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-brand/30 bg-brand/10 text-brand">
              <Settings size={18} />
            </div>
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('settings.settingsCenter', 'Settings Center')}</div>
              <div className="text-sm font-black text-text">{project.projectName}</div>
            </div>
          </div>
          <div className="space-y-2">
            {TABS.map((tab) => (
              <button key={tab} type="button" className={cn('w-full rounded-2xl px-4 py-3 text-left text-sm font-bold', activeTab === tab ? 'bg-active text-text border border-brand/30' : 'text-text-2 hover:bg-hover')} onClick={() => setActiveTab(tab)}>
                {labels[tab]}
              </button>
            ))}
          </div>
        </aside>

        <div className="flex flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{labels[activeTab]}</div>
            </div>
            <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={() => ui.toggleSettings(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
            {activeTab === 'workspace' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={t('settings.languageAndDensity', 'Language and Density')}>
                  <ToggleRow label={t('settings.chinese', 'Chinese')} active={locale === 'zh-CN'} onClick={() => saveSettings({ locale: 'zh-CN' })} t={t} />
                  <ToggleRow label={t('settings.english', 'English')} active={locale === 'en'} onClick={() => saveSettings({ locale: 'en' })} t={t} />
                  <ToggleRow label={t('settings.compactDensity', 'Compact density')} active={ui.density === 'compact'} onClick={() => saveSettings({ density: ui.density === 'compact' ? 'comfortable' : 'compact' })} t={t} />
                  <ToggleRow label={t('settings.reducedMotion', 'Reduced motion')} active={ui.motionLevel === 'reduced'} onClick={() => saveSettings({ motionLevel: ui.motionLevel === 'reduced' ? 'full' : 'reduced' })} t={t} />
                </Section>
                <Section title={t('settings.panelWidths', 'Panel Widths')}>
                  <Slider label={t('settings.sidebar', 'Sidebar')} value={ui.sidebarWidth} min={96} max={480} onChange={(value) => ui.setPanelWidth('sidebar', value)} />
                  <Slider label={t('settings.agentDock', 'Agent Dock')} value={ui.agentDockWidth} min={140} max={560} onChange={(value) => ui.setPanelWidth('agentDock', value)} />
                  <Slider label={t('settings.writingOutline', 'Writing Outline')} value={ui.writingOutlineWidth} min={120} max={560} onChange={(value) => ui.setPanelWidth('writingOutline', value)} />
                  <Slider label={t('settings.writingContext', 'Writing Context')} value={ui.writingContextWidth} min={140} max={560} onChange={(value) => ui.setPanelWidth('writingContext', value)} />
                </Section>
              </div>
            )}

            {activeTab === 'writing' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={t('settings.writingEditor', 'Writing Editor')}>
                  <ToggleRow label={t('settings.wideEditor', 'Wide editor')} active={ui.editorWidth === 'wide'} onClick={() => saveSettings({ editorWidth: ui.editorWidth === 'wide' ? 'focused' : 'wide' })} t={t} />
                  <ToggleRow label={t('settings.showWritingOutline', 'Show writing outline')} active={!ui.isWritingOutlineCollapsed} onClick={() => ui.toggleWritingPane('outline', ui.isWritingOutlineCollapsed)} t={t} />
                  <ToggleRow label={t('settings.showWritingContext', 'Show writing context')} active={!ui.isWritingContextCollapsed} onClick={() => ui.toggleWritingPane('context', ui.isWritingContextCollapsed)} t={t} />
                </Section>
                <Section title={t('settings.projectShortcuts', 'Project Shortcuts')}>
                  <button type="button" className="rounded-2xl border border-border px-4 py-3 text-left text-sm text-text hover:border-brand" onClick={() => project.createProject({ name: 'Starter Demo Project', template: 'starter-demo', locale })}>
                    {t('settings.quickStarter', 'Quick-create starter project')}
                  </button>
                  <button type="button" className="rounded-2xl border border-border px-4 py-3 text-left text-sm text-text hover:border-brand" onClick={() => project.createProject({ name: 'Blank Narrative Project', template: 'blank', locale })}>
                    {t('settings.quickBlank', 'Quick-create blank project')}
                  </button>
                </Section>
              </div>
            )}

            {activeTab === 'ai' && (
              <div className="space-y-6">
                {/* Active configuration summary */}
                <div className="rounded-3xl border border-brand/30 bg-brand/5 px-6 py-4">
                  <div className="mb-1 text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{t('settings.activeConfig', 'Active AI Configuration')}</div>
                  <div className="flex items-center gap-6 text-sm text-text">
                    <span>
                      <span className="text-text-3">{t('settings.provider', 'Provider')}: </span>
                      <span className="font-bold">
                        {ui.appSettings.providerProfiles.find(p => p.id === selectedProviderProfileId)?.label || t('settings.none', 'None')}
                      </span>
                    </span>
                    <span className="text-text-3">·</span>
                    <span>
                      <span className="text-text-3">{t('settings.model', 'Model')}: </span>
                      <span className="font-bold">
                        {ui.appSettings.modelProfiles.find(m => m.id === selectedModelProfileId)?.label || t('settings.none', 'None')}
                      </span>
                    </span>
                  </div>
                </div>

                {/* Provider Profiles */}
                <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
                  <Section title={t('settings.providerProfiles', 'Provider Profiles')}>
                    {ui.appSettings.providerProfiles.map((entry) => {
                      const isActive = entry.id === selectedProviderProfileId;
                      const isEditing = entry.id === activeProviderId;
                      return (
                        <div key={entry.id} className={cn('mb-2 flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm', isEditing ? 'border-brand bg-selected text-text' : 'border-border text-text-2 hover:border-brand')}>
                          <button type="button" className="flex-1 text-left" onClick={() => setActiveProviderId(entry.id)}>
                            <div className="font-bold">{entry.label}</div>
                            <div className="mt-0.5 text-xs">{entry.provider}</div>
                          </button>
                          <button
                            type="button"
                            title={t('settings.setActiveProvider', 'Set as active provider')}
                            className={cn('shrink-0 rounded-xl p-1.5 transition-colors', isActive ? 'text-brand' : 'text-text-3 hover:text-brand')}
                            onClick={() => saveSettings({ selectedProviderProfileId: entry.id })}
                          >
                            <Star size={14} fill={isActive ? 'currentColor' : 'none'} />
                          </button>
                        </div>
                      );
                    })}
                    <button type="button" className="mt-2 w-full rounded-2xl border border-border px-4 py-3 text-sm text-text hover:border-brand" onClick={() => saveSettings({ providerProfiles: [...ui.appSettings.providerProfiles, { id: `provider_${Date.now()}`, provider: 'custom', label: t('settings.newProvider', 'New Provider'), endpoint: '', apiKey: '', enabled: false }] })}>
                      <Plus size={12} className="mr-2 inline" />
                      {t('settings.addProvider', 'Add Provider')}
                    </button>
                  </Section>
                  {provider && (
                    <Section title={t('settings.providerDetails', 'Provider Details')}>
                      <Input label={t('settings.label', 'Label')} value={provider.label} onChange={(value) => updateProvider({ label: value })} />
                      <Input label={t('settings.provider', 'Provider')} value={provider.provider} onChange={(value) => updateProvider({ provider: value })} />
                      <Input label={t('settings.endpoint', 'Endpoint')} value={provider.endpoint} onChange={(value) => updateProvider({ endpoint: value })} />
                      <Input label={t('settings.apiKey', 'API Key')} value={provider.apiKey} onChange={(value) => updateProvider({ apiKey: value })} />
                      <Input label={t('settings.organization', 'Organization')} value={provider.organization || ''} onChange={(value) => updateProvider({ organization: value })} />
                      <Input label={t('settings.project', 'Project')} value={provider.project || ''} onChange={(value) => updateProvider({ project: value })} />
                      <div className="flex flex-wrap gap-3">
                        <ToggleRow label={t('settings.enableProvider', 'Enable provider')} active={provider.enabled} onClick={() => updateProvider({ enabled: !provider.enabled })} t={t} />
                        <button type="button" className="rounded-2xl border border-border px-4 py-3 text-sm text-text hover:border-brand" onClick={async () => {
                          const result = await electronApi.testProviderConnection(provider as any);
                          setProviderStatus(result.ok ? t('settings.connectionOk', 'Connection OK') : `${t('settings.connectionFailed', 'Connection failed')}: ${result.message}`);
                        }}>
                          <CheckCircle2 size={14} className="mr-2 inline" />
                          {t('settings.testConnection', 'Test Connection')}
                        </button>
                      </div>
                      {providerStatus && <div className="rounded-2xl border border-border bg-bg px-4 py-3 text-sm text-text-2">{providerStatus}</div>}
                      <button
                        type="button"
                        className={cn('w-full rounded-2xl border px-4 py-3 text-sm font-bold transition-colors', provider.id === selectedProviderProfileId ? 'border-brand bg-brand/10 text-brand' : 'border-border text-text hover:border-brand')}
                        onClick={() => saveSettings({ selectedProviderProfileId: provider.id })}
                      >
                        <Star size={14} fill={provider.id === selectedProviderProfileId ? 'currentColor' : 'none'} className="mr-2 inline" />
                        {provider.id === selectedProviderProfileId ? t('settings.activeProvider', 'Active Provider') : t('settings.setActiveProvider', 'Set as Active Provider')}
                      </button>
                    </Section>
                  )}
                </div>

                {/* Model Profiles */}
                <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
                  <Section title={t('settings.modelProfiles', 'Model Profiles')}>
                    {ui.appSettings.modelProfiles.map((entry) => {
                      const isActive = entry.id === selectedModelProfileId;
                      const isEditing = entry.id === activeModelId;
                      return (
                        <div key={entry.id} className={cn('mb-2 flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm', isEditing ? 'border-brand bg-selected text-text' : 'border-border text-text-2 hover:border-brand')}>
                          <button type="button" className="flex-1 text-left" onClick={() => setActiveModelId(entry.id)}>
                            <div className="font-bold">{entry.label}</div>
                            <div className="mt-0.5 text-xs">{entry.model}</div>
                          </button>
                          <button
                            type="button"
                            title={t('settings.setActiveModel', 'Set as active model')}
                            className={cn('shrink-0 rounded-xl p-1.5 transition-colors', isActive ? 'text-brand' : 'text-text-3 hover:text-brand')}
                            onClick={() => saveSettings({ selectedModelProfileId: entry.id })}
                          >
                            <Star size={14} fill={isActive ? 'currentColor' : 'none'} />
                          </button>
                        </div>
                      );
                    })}
                    <button type="button" className="mt-2 w-full rounded-2xl border border-border px-4 py-3 text-sm text-text hover:border-brand" onClick={() => saveSettings({ modelProfiles: [...ui.appSettings.modelProfiles, { id: `model_${Date.now()}`, label: t('settings.newModel', 'New Model'), model: 'gpt-4.1', temperature: 0.8, topP: 1, useCase: 'general' }] })}>
                      <Plus size={12} className="mr-2 inline" />
                      {t('settings.addModel', 'Add Model')}
                    </button>
                  </Section>
                  {model && (
                    <Section title={t('settings.modelDetails', 'Model Details')}>
                      <Input label={t('settings.label', 'Label')} value={model.label} onChange={(value) => updateModel({ label: value })} />
                      <Input label={t('settings.model', 'Model')} value={model.model} onChange={(value) => updateModel({ model: value })} />
                      <Input label={t('settings.useCase', 'Use Case')} value={model.useCase} onChange={(value) => updateModel({ useCase: value })} />
                      <Slider label={t('settings.temperature', 'Temperature')} value={model.temperature} min={0} max={2} step={0.1} onChange={(value) => updateModel({ temperature: value })} />
                      <Slider label={t('settings.topP', 'Top P')} value={model.topP} min={0} max={1} step={0.05} onChange={(value) => updateModel({ topP: value })} />
                      <button
                        type="button"
                        className={cn('w-full rounded-2xl border px-4 py-3 text-sm font-bold transition-colors', model.id === selectedModelProfileId ? 'border-brand bg-brand/10 text-brand' : 'border-border text-text hover:border-brand')}
                        onClick={() => saveSettings({ selectedModelProfileId: model.id })}
                      >
                        <Star size={14} fill={model.id === selectedModelProfileId ? 'currentColor' : 'none'} className="mr-2 inline" />
                        {model.id === selectedModelProfileId ? t('settings.activeModel', 'Active Model') : t('settings.setActiveModel', 'Set as Active Model')}
                      </button>
                    </Section>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'import-export' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={t('settings.exportDefaults', 'Export Defaults')}>
                  <ToggleRow label="Markdown" active={ui.appSettings.defaultExportFormat === 'markdown'} onClick={() => saveSettings({ defaultExportFormat: 'markdown' })} t={t} />
                  <ToggleRow label="HTML" active={ui.appSettings.defaultExportFormat === 'html'} onClick={() => saveSettings({ defaultExportFormat: 'html' })} t={t} />
                  <ToggleRow label={t('settings.defaultProjectExport', 'Default whole-project export')} active={ui.appSettings.defaultChapterExportScope === 'project'} onClick={() => saveSettings({ defaultChapterExportScope: 'project' })} t={t} />
                  <ToggleRow label={t('settings.defaultChapterExport', 'Default chapter export')} active={ui.appSettings.defaultChapterExportScope === 'chapter'} onClick={() => saveSettings({ defaultChapterExportScope: 'chapter' })} t={t} />
                </Section>
                <Section title={t('settings.notes', 'Notes')}>
                  <div className="rounded-2xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2">
                    {t('settings.securityNote', 'Sensitive values like API keys stay in app-level settings only. The project folder stores only the selected provider/model profile references.')}
                  </div>
                </Section>
              </div>
            )}

            {activeTab === 'appearance' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={t('settings.themeAndPanels', 'Theme and Panels')}>
                  <ToggleRow label={t('settings.darkTheme', 'Dark theme')} active={ui.appSettings.theme === 'dark'} onClick={() => saveSettings({ theme: 'dark' })} t={t} />
                  <ToggleRow label={t('settings.lightTheme', 'Light theme')} active={ui.appSettings.theme === 'light'} onClick={() => saveSettings({ theme: 'light' })} t={t} />
                  <ToggleRow label={t('settings.showSidebar', 'Show sidebar')} active={!ui.isSidebarCollapsed} onClick={() => ui.toggleSidebar(ui.isSidebarCollapsed)} t={t} />
                  <ToggleRow label={t('settings.showAgentDock', 'Show Agent Dock')} active={ui.isAgentDockOpen} onClick={() => ui.toggleAgentDock(!ui.isAgentDockOpen)} t={t} />
                </Section>
                <Section title={t('settings.resetLayout', 'Reset Layout')}>
                  <button type="button" className="rounded-2xl border border-border px-4 py-3 text-left text-sm text-text hover:border-brand" onClick={() => ui.resetLayout()}>
                    {t('settings.resetAllPanels', 'Reset all panel sizes and collapse states')}
                  </button>
                </Section>
              </div>
            )}

            {activeTab === 'prompts' && (
              <div className="flex h-full gap-0 overflow-hidden rounded-3xl border border-border">
                {/* Left panel — flow + prompt list */}
                <aside className="w-56 shrink-0 border-r border-border bg-bg-elev-2 overflow-y-auto custom-scrollbar">
                  {Object.entries(FLOW_LABELS).map(([flowId, flowLabel]) => {
                    const flowPrompts = sidecarPrompts[flowId] ?? [];
                    const isFlowOpen = selectedFlowId === flowId;
                    return (
                      <div key={flowId}>
                        <button
                          type="button"
                          className={cn('w-full px-4 py-3 text-left text-[10px] font-black uppercase tracking-[0.2em]', isFlowOpen ? 'bg-active text-brand-2' : 'text-text-3 hover:bg-hover')}
                          onClick={() => { setSelectedFlowId(flowId); if (flowPrompts.length > 0) setSelectedPromptName(flowPrompts[0].name); }}
                        >
                          {flowLabel}
                        </button>
                        {isFlowOpen && flowPrompts.map((p) => (
                          <button
                            key={p.name}
                            type="button"
                            className={cn('w-full px-4 py-2 text-left text-[11px] pl-6', selectedPromptName === p.name ? 'bg-selected text-text font-bold' : 'text-text-2 hover:bg-hover')}
                            onClick={() => setSelectedPromptName(p.name)}
                          >
                            {p.name.replace(/^W\d_/, '').replace(/_/g, ' ').toLowerCase()}
                          </button>
                        ))}
                        {isFlowOpen && flowPrompts.length === 0 && (
                          <div className="px-6 py-2 text-[10px] text-text-3 italic">
                            {t('settings.prompts.loading', 'Loading…')}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </aside>

                {/* Right panel — base prompt + user slot */}
                <div className="flex flex-1 flex-col overflow-hidden">
                  <div className="border-b border-border px-5 py-3">
                    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{selectedFlowId}</div>
                    <div className="mt-0.5 text-sm font-bold text-text">{selectedPromptName.replace(/_/g, ' ')}</div>
                  </div>

                  <div className="flex flex-1 flex-col gap-4 overflow-y-auto custom-scrollbar p-5">
                    {/* Base prompt — read only */}
                    <div>
                      <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                        {t('settings.prompts.basePrompt', 'Base Prompt (read-only)')}
                      </div>
                      <pre className="h-48 overflow-y-auto custom-scrollbar rounded-2xl border border-border bg-bg px-4 py-3 font-mono text-[10px] leading-relaxed text-text-2 whitespace-pre-wrap">
                        {selectedBaseText || t('settings.prompts.noContent', 'Select a prompt from the list. Open a project and ensure the sidecar is running.')}
                      </pre>
                    </div>

                    {/* User instruction slot — editable */}
                    <div>
                      <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                        {t('settings.prompts.userSlot', 'User Instruction Slot (appended to every call)')}
                      </div>
                      <textarea
                        data-testid="prompt-user-slot-textarea"
                        value={userSlot}
                        onChange={(e) => { setUserSlot(e.target.value); setPromptSaved(false); }}
                        rows={5}
                        placeholder={t('settings.prompts.userSlotPlaceholder', 'Add extra instructions here. These will be appended to the base prompt before every LLM call for this prompt.')}
                        className="w-full rounded-2xl border border-border bg-bg px-4 py-3 font-mono text-xs text-text outline-none resize-none focus:border-brand"
                      />
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        data-testid="prompt-save-btn"
                        onClick={handleSaveUserSlot}
                        className="inline-flex items-center gap-2 rounded-2xl bg-brand px-5 py-2 text-[11px] font-black uppercase tracking-widest text-text-invert hover:bg-brand/90"
                      >
                        <Save size={13} />
                        {promptSaved ? t('settings.prompts.saved', 'Saved!') : t('settings.prompts.save', 'Save')}
                      </button>
                      {promptSaved && (
                        <span className="text-xs text-green">{t('settings.prompts.savedNote', 'Changes apply on next import run.')}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'advanced' && (
              <Section title={t('settings.advancedNotes', 'Advanced Notes')}>
                <div className="rounded-2xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2">
                  {t('settings.advancedBody', 'This settings center already drives language, density, motion, theme, providers, models, export defaults, and panel layout. Remaining placeholder areas will be connected to real provider runtimes in the next phase.')}
                </div>
              </Section>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="rounded-3xl border border-border bg-card p-6">
    <div className="mb-4 text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{title}</div>
    <div className="space-y-4">{children}</div>
  </div>
);

const ToggleRow = ({ label, active, onClick, t }: { label: string; active: boolean; onClick: () => void; t: (key: string, fallback?: string) => string }) => (
  <button type="button" className={cn('flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm', active ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={onClick}>
    <span>{label}</span>
    <span className="text-[10px] font-black uppercase tracking-[0.16em]">{active ? t('settings.on', 'ON') : t('settings.off', 'OFF')}</span>
  </button>
);

const Input = ({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) => (
  <label className="block">
    <div className="mb-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <input value={value} onChange={(event) => onChange(event.target.value)} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
  </label>
);

const Slider = ({ label, value, min, max, onChange, step = 1 }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void; step?: number }) => (
  <label className="block">
    <div className="mb-2 flex items-center justify-between gap-3 text-sm text-text">
      <span>{label}</span>
      <span className="text-[11px] font-black uppercase tracking-[0.2em] text-text-3">{value}</span>
    </div>
    <input type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} className="w-full accent-brand" />
  </label>
);
