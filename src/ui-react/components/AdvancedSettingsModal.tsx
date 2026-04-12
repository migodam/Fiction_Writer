import React, { useMemo, useState } from 'react';
import { CheckCircle2, Plus, Settings, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { electronApi } from '../services/electronApi';
import { useI18n } from '../i18n';

const TABS = ['workspace', 'writing', 'providers', 'models', 'import-export', 'appearance', 'advanced'] as const;

export const AdvancedSettingsModal = () => {
  const ui = useUIStore();
  const project = useProjectStore();
  const { t } = useI18n();
  const locale = ui.locale;
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('workspace');
  const [activeProviderId, setActiveProviderId] = useState(ui.appSettings.providerProfiles[0]?.id || '');
  const [activeModelId, setActiveModelId] = useState(ui.appSettings.modelProfiles[0]?.id || '');
  const [providerStatus, setProviderStatus] = useState<string | null>(null);

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

  const labels = useMemo(() => ({
    workspace: t('settings.workspace', 'Workspace'),
    writing: t('settings.writing', 'Writing'),
    providers: t('settings.providers', 'Providers'),
    models: t('settings.models', 'Models'),
    'import-export': t('settings.importExport', 'Import / Export'),
    appearance: t('settings.appearance', 'Appearance'),
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

            {activeTab === 'providers' && (
              <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
                <Section title={t('settings.providerProfiles', 'Provider Profiles')}>
                  {ui.appSettings.providerProfiles.map((entry) => (
                    <button key={entry.id} type="button" className={cn('mb-2 block w-full rounded-2xl border px-4 py-3 text-left text-sm', activeProviderId === entry.id ? 'border-brand bg-selected text-text' : 'border-border text-text-2 hover:border-brand')} onClick={() => setActiveProviderId(entry.id)}>
                      <div className="font-bold">{entry.label}</div>
                      <div className="mt-1 text-xs">{entry.provider}</div>
                    </button>
                  ))}
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
                    <div className="flex gap-3">
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
                  </Section>
                )}
              </div>
            )}

            {activeTab === 'models' && (
              <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
                <Section title={t('settings.modelProfiles', 'Model Profiles')}>
                  {ui.appSettings.modelProfiles.map((entry) => (
                    <button key={entry.id} type="button" className={cn('mb-2 block w-full rounded-2xl border px-4 py-3 text-left text-sm', activeModelId === entry.id ? 'border-brand bg-selected text-text' : 'border-border text-text-2 hover:border-brand')} onClick={() => setActiveModelId(entry.id)}>
                      <div className="font-bold">{entry.label}</div>
                      <div className="mt-1 text-xs">{entry.model}</div>
                    </button>
                  ))}
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
                  </Section>
                )}
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
