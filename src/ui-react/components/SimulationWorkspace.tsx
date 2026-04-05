import React, { useState } from 'react';
import { PlayCircle, Plus, Sparkles } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

const ENGINE_PRESETS = [
  { type: 'scenario', en: 'Scenario Engine', zh: '情景引擎' },
  { type: 'character', en: 'Character Engine', zh: '角色引擎' },
  { type: 'author', en: 'Author Engine', zh: '作者引擎' },
  { type: 'reader', en: 'Reader Engine', zh: '读者引擎' },
  { type: 'logic', en: 'Logic Engine', zh: '逻辑引擎' },
  { type: 'custom', en: 'Custom Engine', zh: '自定义引擎' },
] as const;

export const SimulationWorkspace = () => {
  const { sidebarSection } = useUIStore();
  const { locale } = useI18n();
  const zh = locale === 'zh-CN';
  const {
    simulationEngines,
    simulationLabs,
    simulationReviewers,
    simulationRuns,
    chapters,
    projectRoot,
    createSimulationLab,
    updateSimulationLab,
    createSimulationReviewer,
    updateSimulationReviewer,
    addSimulationEngine,
    updateSimulationEngine,
    runSimulation,
    w5Status,
  } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const isRunning = w5Status === 'running';
  const [activeId, setActiveId] = useState(simulationLabs[0]?.id || simulationReviewers[0]?.id || null);

  const isReviewerMode = sidebarSection === 'reviewers';
  const collections = isReviewerMode ? simulationReviewers : simulationLabs;
  const active = collections.find((entry) => entry.id === activeId) || collections[0] || null;
  const engineList = simulationEngines.filter((engine) => active?.engineIds.includes(engine.id));
  const relatedRuns = simulationRuns.filter((run) => run.entityId === active?.id);

  const createContainer = () => {
    const id = `${isReviewerMode ? 'reviewer' : 'lab'}_${Date.now()}`;
    const base = {
      id,
      name: `${isReviewerMode ? (zh ? '新 Reviewer' : 'New Reviewer') : (zh ? '新 Lab' : 'New Lab')} ${collections.length + 1}`,
      description: '',
      engineIds: [],
    };
    if (isReviewerMode) {
      createSimulationReviewer({ ...base, scoringNotes: '' });
    } else {
      createSimulationLab({ ...base, summary: '' });
    }
    setActiveId(id);
  };

  const addPresetEngine = (type: typeof ENGINE_PRESETS[number]['type']) => {
    if (!active) return;
    const preset = ENGINE_PRESETS.find((entry) => entry.type === type)!;
    const id = `sim_engine_${Date.now()}`;
    addSimulationEngine({
      id,
      name: zh ? preset.zh : preset.en,
      type,
      summary: zh ? '占位结果容器，等待后续真实执行器接入。' : 'Placeholder result container for future executors.',
      promptOverride: '',
      enabled: true,
      inputNotes: '',
      targetCharacterId: null,
    });
    if (isReviewerMode) {
      updateSimulationReviewer({ ...(active as any), engineIds: [...active.engineIds, id] });
    } else {
      updateSimulationLab({ ...(active as any), engineIds: [...active.engineIds, id] });
    }
  };

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-80 border-r border-border bg-bg-elev-1">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{isReviewerMode ? (zh ? 'Reviewers' : 'Reviewers') : (zh ? 'Labs' : 'Labs')}</div>
              <div className="text-sm font-black text-text">{isReviewerMode ? (zh ? '检查与评分容器' : 'Review containers') : (zh ? '剧情推演容器' : 'Simulation containers')}</div>
            </div>
            <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={createContainer}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {collections.map((entry) => (
            <button key={entry.id} type="button" className={cn('mb-2 w-full rounded-2xl border px-4 py-4 text-left', active?.id === entry.id ? 'border-brand bg-selected' : 'border-border bg-card')} onClick={() => setActiveId(entry.id)}>
              <div className="text-sm font-black text-text">{entry.name}</div>
              <div className="mt-2 text-xs text-text-2">{entry.description || (isReviewerMode ? (zh ? '暂无说明' : 'No description') : (zh ? '暂无摘要' : 'No summary'))}</div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
        {active ? (
          <div className="mx-auto max-w-6xl space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{isReviewerMode ? (zh ? 'Reviewer 总览' : 'Reviewer Overview') : (zh ? 'Lab 总览' : 'Lab Overview')}</div>
                <div className="mt-2 text-3xl font-black text-text">{active.name}</div>
              </div>
              <button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" disabled={isRunning} onClick={() => { void runSimulation({ projectRoot, scenario_variable: active.description || active.name, affected_chapter_ids: chapters.map((c) => c.id), engines_selected: engineList.map((e) => e.type) }).then(() => setLastActionStatus(zh ? '推演完成' : 'Simulation complete')); }}>
                <PlayCircle size={14} className="mr-2 inline" />
                {isReviewerMode ? (zh ? '运行当前 Reviewer' : 'Run Reviewer') : (zh ? '运行当前 Lab' : 'Run Lab')}
              </button>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <Stat label={zh ? '引擎数量' : 'Engines'} value={String(active.engineIds.length)} />
              <Stat label={zh ? '运行记录' : 'Runs'} value={String(relatedRuns.length)} />
              <Stat label={zh ? '类型' : 'Mode'} value={isReviewerMode ? (zh ? '检查/评分' : 'Review') : (zh ? '预测/推演' : 'Projection')} />
            </div>

            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '基础信息' : 'Basics'}</div>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <input value={active.name} onChange={(event) => isReviewerMode ? updateSimulationReviewer({ ...(active as any), name: event.target.value }) : updateSimulationLab({ ...(active as any), name: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
                <textarea value={active.description} onChange={(event) => isReviewerMode ? updateSimulationReviewer({ ...(active as any), description: event.target.value }) : updateSimulationLab({ ...(active as any), description: event.target.value })} className="h-28 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '引擎' : 'Engines'}</div>
                <div className="flex flex-wrap gap-2">
                  {ENGINE_PRESETS.map((preset) => (
                    <button key={preset.type} type="button" className="rounded-full border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.16em] text-text-2 hover:border-brand" onClick={() => addPresetEngine(preset.type)}>
                      <Plus size={10} className="mr-1 inline" />
                      {zh ? preset.zh : preset.en}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                {engineList.map((engine) => (
                  <EngineCard key={engine.id} engine={engine} onChange={updateSimulationEngine} onRun={() => { void runSimulation({ projectRoot, scenario_variable: active.description || active.name, affected_chapter_ids: chapters.map((c) => c.id), engines_selected: [engine.type] }).then(() => setLastActionStatus(zh ? '引擎运行完成' : 'Engine run complete')); }} zh={zh} />
                ))}
                {!engineList.length && <div className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-3">{zh ? '还没有引擎，先添加一个预设。' : 'No engines yet. Add a preset first.'}</div>}
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{zh ? '最近运行结果' : 'Recent Runs'}</div>
              <div className="space-y-3">
                {relatedRuns.map((run) => (
                  <div key={run.id} className="rounded-2xl border border-border bg-bg p-4">
                    <div className="text-sm font-black text-text">{run.engineId || run.entityId}</div>
                    <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{run.status} / {run.createdAt}</div>
                    <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text-2">{run.output}</div>
                  </div>
                ))}
                {!relatedRuns.length && <div className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-3">{zh ? '暂无运行记录。' : 'No runs yet.'}</div>}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-text-3">
            <div className="text-center">
              <Sparkles size={96} className="mx-auto mb-6 opacity-10" />
              <div className="text-lg font-black text-text">{isReviewerMode ? (zh ? '先创建一个 Reviewer' : 'Create a reviewer first') : (zh ? '先创建一个 Lab' : 'Create a lab first')}</div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

const EngineCard = ({ engine, onChange, onRun, zh }: any) => (
  <div className="rounded-3xl border border-border bg-bg-elev-1 p-5">
    <div className="mb-4 flex items-center justify-between">
      <div>
        <div className="text-sm font-black text-text">{engine.name}</div>
        <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{engine.type}</div>
      </div>
      <button type="button" className="rounded-xl bg-brand px-4 py-2 text-[10px] font-black uppercase tracking-[0.16em] text-white" onClick={onRun}>
        {zh ? '单独运行' : 'Run'}
      </button>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <input value={engine.name} onChange={(event) => onChange({ ...engine, name: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
      <input value={engine.summary} onChange={(event) => onChange({ ...engine, summary: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '用途摘要' : 'Summary'} />
    </div>
    <textarea value={engine.promptOverride || ''} onChange={(event) => onChange({ ...engine, promptOverride: event.target.value })} className="mt-4 h-28 w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? 'Prompt 覆盖' : 'Prompt override'} />
    <textarea value={engine.inputNotes || ''} onChange={(event) => onChange({ ...engine, inputNotes: event.target.value })} className="mt-4 h-24 w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={zh ? '输入备注' : 'Input notes'} />
  </div>
);

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <div className="mt-2 text-2xl font-black text-text">{value}</div>
  </div>
);
