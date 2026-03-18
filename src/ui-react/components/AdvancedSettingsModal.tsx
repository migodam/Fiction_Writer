import React, { useMemo, useState } from 'react';
import { CheckCircle2, Plus, Settings, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { electronApi } from '../services/electronApi';

const TABS = ['workspace', 'writing', 'providers', 'models', 'import-export', 'appearance', 'advanced'] as const;

export const AdvancedSettingsModal = () => {
  const ui = useUIStore();
  const project = useProjectStore();
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('workspace');
  const [activeProviderId, setActiveProviderId] = useState(ui.appSettings.providerProfiles[0]?.id || '');
  const [activeModelId, setActiveModelId] = useState(ui.appSettings.modelProfiles[0]?.id || '');
  const [providerStatus, setProviderStatus] = useState<string | null>(null);

  const locale = ui.locale;
  const zh = locale === 'zh-CN';
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
    workspace: zh ? '工作区' : 'Workspace',
    writing: zh ? '写作' : 'Writing',
    providers: zh ? 'Provider' : 'Providers',
    models: zh ? '模型' : 'Models',
    'import-export': zh ? '导入导出' : 'Import / Export',
    appearance: zh ? '外观' : 'Appearance',
    advanced: zh ? '高级' : 'Advanced',
  }), [zh]);

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
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{zh ? '设置中心' : 'Settings Center'}</div>
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
                <Section title={zh ? '语言与密度' : 'Language and Density'}>
                  <ToggleRow label={zh ? '中文' : 'Chinese'} active={locale === 'zh-CN'} onClick={() => saveSettings({ locale: 'zh-CN' })} />
                  <ToggleRow label={zh ? 'English' : 'English'} active={locale === 'en'} onClick={() => saveSettings({ locale: 'en' })} />
                  <ToggleRow label={zh ? '紧凑布局' : 'Compact density'} active={ui.density === 'compact'} onClick={() => saveSettings({ density: ui.density === 'compact' ? 'comfortable' : 'compact' })} />
                  <ToggleRow label={zh ? '减少动效' : 'Reduced motion'} active={ui.motionLevel === 'reduced'} onClick={() => saveSettings({ motionLevel: ui.motionLevel === 'reduced' ? 'full' : 'reduced' })} />
                </Section>
                <Section title={zh ? '面板宽度' : 'Panel Widths'}>
                  <Slider label={zh ? '侧栏' : 'Sidebar'} value={ui.sidebarWidth} min={96} max={480} onChange={(value) => ui.setPanelWidth('sidebar', value)} />
                  <Slider label={zh ? 'Agent Dock' : 'Agent Dock'} value={ui.agentDockWidth} min={140} max={560} onChange={(value) => ui.setPanelWidth('agentDock', value)} />
                  <Slider label={zh ? '写作大纲' : 'Writing Outline'} value={ui.writingOutlineWidth} min={120} max={560} onChange={(value) => ui.setPanelWidth('writingOutline', value)} />
                  <Slider label={zh ? '写作上下文' : 'Writing Context'} value={ui.writingContextWidth} min={140} max={560} onChange={(value) => ui.setPanelWidth('writingContext', value)} />
                </Section>
              </div>
            )}

            {activeTab === 'writing' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={zh ? '写作编辑器' : 'Writing Editor'}>
                  <ToggleRow label={zh ? '宽版编辑区' : 'Wide editor'} active={ui.editorWidth === 'wide'} onClick={() => saveSettings({ editorWidth: ui.editorWidth === 'wide' ? 'focused' : 'wide' })} />
                  <ToggleRow label={zh ? '显示写作大纲' : 'Show writing outline'} active={!ui.isWritingOutlineCollapsed} onClick={() => ui.toggleWritingPane('outline', ui.isWritingOutlineCollapsed)} />
                  <ToggleRow label={zh ? '显示写作上下文' : 'Show writing context'} active={!ui.isWritingContextCollapsed} onClick={() => ui.toggleWritingPane('context', ui.isWritingContextCollapsed)} />
                </Section>
                <Section title={zh ? '项目快捷操作' : 'Project Shortcuts'}>
                  <button type="button" className="rounded-2xl border border-border px-4 py-3 text-left text-sm text-text hover:border-brand" onClick={() => project.createProject({ name: 'Starter Demo Project', template: 'starter-demo', locale })}>
                    {zh ? '快速创建演示项目' : 'Quick-create starter project'}
                  </button>
                  <button type="button" className="rounded-2xl border border-border px-4 py-3 text-left text-sm text-text hover:border-brand" onClick={() => project.createProject({ name: 'Blank Narrative Project', template: 'blank', locale })}>
                    {zh ? '快速创建空白项目' : 'Quick-create blank project'}
                  </button>
                </Section>
              </div>
            )}

            {activeTab === 'providers' && (
              <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
                <Section title={zh ? 'Provider 配置' : 'Provider Profiles'}>
                  {ui.appSettings.providerProfiles.map((entry) => (
                    <button key={entry.id} type="button" className={cn('mb-2 block w-full rounded-2xl border px-4 py-3 text-left text-sm', activeProviderId === entry.id ? 'border-brand bg-selected text-text' : 'border-border text-text-2 hover:border-brand')} onClick={() => setActiveProviderId(entry.id)}>
                      <div className="font-bold">{entry.label}</div>
                      <div className="mt-1 text-xs">{entry.provider}</div>
                    </button>
                  ))}
                  <button type="button" className="mt-2 w-full rounded-2xl border border-border px-4 py-3 text-sm text-text hover:border-brand" onClick={() => saveSettings({ providerProfiles: [...ui.appSettings.providerProfiles, { id: `provider_${Date.now()}`, provider: 'custom', label: zh ? '新 Provider' : 'New Provider', endpoint: '', apiKey: '', enabled: false }] })}>
                    <Plus size={12} className="mr-2 inline" />
                    {zh ? '新增 Provider' : 'Add Provider'}
                  </button>
                </Section>
                {provider && (
                  <Section title={zh ? 'Provider 详情' : 'Provider Details'}>
                    <Input label="Label" value={provider.label} onChange={(value) => updateProvider({ label: value })} />
                    <Input label="Provider" value={provider.provider} onChange={(value) => updateProvider({ provider: value })} />
                    <Input label="Endpoint" value={provider.endpoint} onChange={(value) => updateProvider({ endpoint: value })} />
                    <Input label="API Key" value={provider.apiKey} onChange={(value) => updateProvider({ apiKey: value })} />
                    <Input label="Organization" value={provider.organization || ''} onChange={(value) => updateProvider({ organization: value })} />
                    <Input label="Project" value={provider.project || ''} onChange={(value) => updateProvider({ project: value })} />
                    <div className="flex gap-3">
                      <ToggleRow label={zh ? '启用该 Provider' : 'Enable provider'} active={provider.enabled} onClick={() => updateProvider({ enabled: !provider.enabled })} />
                      <button type="button" className="rounded-2xl border border-border px-4 py-3 text-sm text-text hover:border-brand" onClick={async () => {
                        const result = await electronApi.testProviderConnection(provider as any);
                        setProviderStatus(result.ok ? (zh ? '连接成功' : 'Connection OK') : `${zh ? '连接失败' : 'Connection failed'}: ${result.message}`);
                      }}>
                        <CheckCircle2 size={14} className="mr-2 inline" />
                        {zh ? '测试连接' : 'Test Connection'}
                      </button>
                    </div>
                    {providerStatus && <div className="rounded-2xl border border-border bg-bg px-4 py-3 text-sm text-text-2">{providerStatus}</div>}
                  </Section>
                )}
              </div>
            )}

            {activeTab === 'models' && (
              <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
                <Section title={zh ? '模型配置' : 'Model Profiles'}>
                  {ui.appSettings.modelProfiles.map((entry) => (
                    <button key={entry.id} type="button" className={cn('mb-2 block w-full rounded-2xl border px-4 py-3 text-left text-sm', activeModelId === entry.id ? 'border-brand bg-selected text-text' : 'border-border text-text-2 hover:border-brand')} onClick={() => setActiveModelId(entry.id)}>
                      <div className="font-bold">{entry.label}</div>
                      <div className="mt-1 text-xs">{entry.model}</div>
                    </button>
                  ))}
                  <button type="button" className="mt-2 w-full rounded-2xl border border-border px-4 py-3 text-sm text-text hover:border-brand" onClick={() => saveSettings({ modelProfiles: [...ui.appSettings.modelProfiles, { id: `model_${Date.now()}`, label: zh ? '新模型' : 'New Model', model: 'gpt-4.1', temperature: 0.8, topP: 1, useCase: 'general' }] })}>
                    <Plus size={12} className="mr-2 inline" />
                    {zh ? '新增模型' : 'Add Model'}
                  </button>
                </Section>
                {model && (
                  <Section title={zh ? '模型详情' : 'Model Details'}>
                    <Input label="Label" value={model.label} onChange={(value) => updateModel({ label: value })} />
                    <Input label="Model" value={model.model} onChange={(value) => updateModel({ model: value })} />
                    <Input label="Use Case" value={model.useCase} onChange={(value) => updateModel({ useCase: value })} />
                    <Slider label="Temperature" value={model.temperature} min={0} max={2} step={0.1} onChange={(value) => updateModel({ temperature: value })} />
                    <Slider label="Top P" value={model.topP} min={0} max={1} step={0.05} onChange={(value) => updateModel({ topP: value })} />
                  </Section>
                )}
              </div>
            )}

            {activeTab === 'import-export' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={zh ? '导出默认值' : 'Export Defaults'}>
                  <ToggleRow label="Markdown" active={ui.appSettings.defaultExportFormat === 'markdown'} onClick={() => saveSettings({ defaultExportFormat: 'markdown' })} />
                  <ToggleRow label="HTML" active={ui.appSettings.defaultExportFormat === 'html'} onClick={() => saveSettings({ defaultExportFormat: 'html' })} />
                  <ToggleRow label={zh ? '默认整本导出' : 'Default whole-project export'} active={ui.appSettings.defaultChapterExportScope === 'project'} onClick={() => saveSettings({ defaultChapterExportScope: 'project' })} />
                  <ToggleRow label={zh ? '默认按章节导出' : 'Default chapter export'} active={ui.appSettings.defaultChapterExportScope === 'chapter'} onClick={() => saveSettings({ defaultChapterExportScope: 'chapter' })} />
                </Section>
                <Section title={zh ? '说明' : 'Notes'}>
                  <div className="rounded-2xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2">
                    {zh ? 'API Key 等敏感信息只保存在应用级设置，不写入项目目录。项目目录只保存已选中的 provider / model profile 引用。' : 'Sensitive values like API keys stay in app-level settings only. The project folder stores only the selected provider/model profile references.'}
                  </div>
                </Section>
              </div>
            )}

            {activeTab === 'appearance' && (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section title={zh ? '主题与面板' : 'Theme and Panels'}>
                  <ToggleRow label={zh ? '深色主题' : 'Dark theme'} active={ui.appSettings.theme === 'dark'} onClick={() => saveSettings({ theme: 'dark' })} />
                  <ToggleRow label={zh ? '浅色主题' : 'Light theme'} active={ui.appSettings.theme === 'light'} onClick={() => saveSettings({ theme: 'light' })} />
                  <ToggleRow label={zh ? '显示侧栏' : 'Show sidebar'} active={!ui.isSidebarCollapsed} onClick={() => ui.toggleSidebar(ui.isSidebarCollapsed)} />
                  <ToggleRow label={zh ? '显示 Agent Dock' : 'Show Agent Dock'} active={ui.isAgentDockOpen} onClick={() => ui.toggleAgentDock(!ui.isAgentDockOpen)} />
                </Section>
                <Section title={zh ? '布局重置' : 'Reset Layout'}>
                  <button type="button" className="rounded-2xl border border-border px-4 py-3 text-left text-sm text-text hover:border-brand" onClick={() => ui.resetLayout()}>
                    {zh ? '重置所有面板尺寸和折叠状态' : 'Reset all panel sizes and collapse states'}
                  </button>
                </Section>
              </div>
            )}

            {activeTab === 'advanced' && (
              <Section title={zh ? '高级说明' : 'Advanced Notes'}>
                <div className="rounded-2xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2">
                  {zh ? '当前设置页已经接通：语言、密度、动效、主题、provider、模型、导出默认值、面板宽度和显示状态。仍然保留占位的部分，会在后续接入真实 provider runtime。' : 'This settings center already drives language, density, motion, theme, providers, models, export defaults, and panel layout. Remaining placeholder areas will be connected to real provider runtimes in the next phase.'}
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

const ToggleRow = ({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) => (
  <button type="button" className={cn('flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm', active ? 'border-brand bg-active text-text' : 'border-border text-text-2')} onClick={onClick}>
    <span>{label}</span>
    <span className="text-[10px] font-black uppercase tracking-[0.16em]">{active ? 'ON' : 'OFF'}</span>
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
