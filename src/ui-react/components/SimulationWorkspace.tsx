import React, { useState } from 'react';
import { PlayCircle, Plus, Sparkles, Trash2, X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

const ENGINE_PRESETS = [
  { type: 'scenario', labelKey: 'simulation.engineScenario' },
  { type: 'character', labelKey: 'simulation.engineCharacter' },
  { type: 'author', labelKey: 'simulation.engineAuthor' },
  { type: 'reader', labelKey: 'simulation.engineReader' },
  { type: 'logic', labelKey: 'simulation.engineLogic' },
  { type: 'custom', labelKey: 'simulation.engineCustom' },
] as const;

export const SimulationWorkspace = () => {
  const { sidebarSection } = useUIStore();
  const { t } = useI18n();
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
    deleteSimulationLab,
    deleteSimulationReviewer,
    removeSimulationEngine,
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
      name: `${isReviewerMode ? t('simulation.newReviewer') : t('simulation.newLab')} ${collections.length + 1}`,
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

  const handleDeleteContainer = (entryId: string) => {
    if (isReviewerMode) {
      if (window.confirm(t('simulation.confirmDeleteReviewer'))) {
        deleteSimulationReviewer(entryId);
        if (active?.id === entryId) setActiveId(null);
        setLastActionStatus(t('simulation.reviewerDeleted'));
      }
    } else {
      if (window.confirm(t('simulation.confirmDeleteLab'))) {
        deleteSimulationLab(entryId);
        if (active?.id === entryId) setActiveId(null);
        setLastActionStatus(t('simulation.labDeleted'));
      }
    }
  };

  const handleRemoveEngine = (engineId: string) => {
    if (window.confirm(t('simulation.confirmRemoveEngine'))) {
      removeSimulationEngine(engineId);
      if (isReviewerMode && active) {
        updateSimulationReviewer({ ...(active as any), engineIds: active.engineIds.filter((eid: string) => eid !== engineId) });
      } else if (active) {
        updateSimulationLab({ ...(active as any), engineIds: active.engineIds.filter((eid: string) => eid !== engineId) });
      }
      setLastActionStatus(t('simulation.engineRemoved'));
    }
  };

  const addPresetEngine = (type: typeof ENGINE_PRESETS[number]['type']) => {
    if (!active) return;
    const preset = ENGINE_PRESETS.find((entry) => entry.type === type)!;
    const id = `sim_engine_${Date.now()}`;
    addSimulationEngine({
      id,
      name: t(preset.labelKey),
      type,
      summary: t('simulation.placeholderResult'),
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
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{isReviewerMode ? t('simulation.reviewers') : t('simulation.labs')}</div>
              <div className="text-sm font-black text-text">{isReviewerMode ? t('simulation.reviewContainers') : t('simulation.simulationContainers')}</div>
            </div>
            <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" onClick={createContainer}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {collections.map((entry) => (
            <div key={entry.id} className={cn('mb-2 w-full rounded-2xl border px-4 py-4 text-left', active?.id === entry.id ? 'border-brand bg-selected' : 'border-border bg-card')}>
              <button type="button" className="w-full text-left" onClick={() => setActiveId(entry.id)}>
                <div className="text-sm font-black text-text">{entry.name}</div>
                <div className="mt-2 text-xs text-text-2">{entry.description || (isReviewerMode ? t('simulation.noDescription') : t('simulation.noSummary'))}</div>
              </button>
              <button type="button" className="mt-2 flex items-center gap-1 text-xs text-red/70 hover:text-red" onClick={() => handleDeleteContainer(entry.id)}>
                <Trash2 size={12} />
                {isReviewerMode ? t('simulation.deleteReviewer') : t('simulation.deleteLab')}
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
        {active ? (
          <div className="mx-auto max-w-6xl space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{isReviewerMode ? t('simulation.reviewerOverview') : t('simulation.labOverview')}</div>
                <div className="mt-2 text-3xl font-black text-text">{active.name}</div>
              </div>
              <button type="button" className="rounded-xl bg-brand px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-white" disabled={isRunning} onClick={() => { void runSimulation({ projectRoot, scenario_variable: active.description || active.name, affected_chapter_ids: chapters.map((c) => c.id), engines_selected: engineList.map((e) => e.type) }).then(() => setLastActionStatus(t('simulation.simulationComplete'))); }}>
                <PlayCircle size={14} className="mr-2 inline" />
                {isReviewerMode ? t('simulation.runReviewer') : t('simulation.runLab')}
              </button>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <Stat label={t('simulation.engines')} value={String(active.engineIds.length)} />
              <Stat label={t('simulation.runs')} value={String(relatedRuns.length)} />
              <Stat label={t('simulation.mode')} value={isReviewerMode ? t('simulation.review') : t('simulation.projection')} />
            </div>

            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('simulation.basics')}</div>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <input value={active.name} onChange={(event) => isReviewerMode ? updateSimulationReviewer({ ...(active as any), name: event.target.value }) : updateSimulationLab({ ...(active as any), name: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
                <textarea value={active.description} onChange={(event) => isReviewerMode ? updateSimulationReviewer({ ...(active as any), description: event.target.value }) : updateSimulationLab({ ...(active as any), description: event.target.value })} className="h-28 rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('simulation.engines')}</div>
                <div className="flex flex-wrap gap-2">
                  {ENGINE_PRESETS.map((preset) => (
                    <button key={preset.type} type="button" className="rounded-full border border-border px-3 py-2 text-[10px] font-black uppercase tracking-[0.16em] text-text-2 hover:border-brand" onClick={() => addPresetEngine(preset.type)}>
                      <Plus size={10} className="mr-1 inline" />
                      {t(preset.labelKey)}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                {engineList.map((engine) => (
                  <EngineCard key={engine.id} engine={engine} onChange={updateSimulationEngine} onRun={() => { void runSimulation({ projectRoot, scenario_variable: active.description || active.name, affected_chapter_ids: chapters.map((c) => c.id), engines_selected: [engine.type] }).then(() => setLastActionStatus(t('simulation.engineRunComplete'))); }} onRemove={() => handleRemoveEngine(engine.id)} t={t} />
                ))}
                {!engineList.length && <div className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-3">{t('simulation.noEnginesYet')}</div>}
              </div>
            </div>

            <div className="rounded-3xl border border-border bg-card p-6">
              <div className="mb-4 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('simulation.recentRuns')}</div>
              <div className="space-y-3">
                {relatedRuns.map((run) => (
                  <div key={run.id} className="rounded-2xl border border-border bg-bg p-4">
                    <div className="text-sm font-black text-text">{run.engineId || run.entityId}</div>
                    <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{run.status} / {run.createdAt}</div>
                    <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text-2">{run.output}</div>
                  </div>
                ))}
                {!relatedRuns.length && <div className="rounded-2xl border border-dashed border-border bg-bg p-6 text-sm text-text-3">{t('simulation.noRunsYet')}</div>}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-text-3">
            <div className="text-center">
              <Sparkles size={96} className="mx-auto mb-6 opacity-10" />
              <div className="text-lg font-black text-text">{isReviewerMode ? t('simulation.createReviewerFirst') : t('simulation.createLabFirst')}</div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

const EngineCard = ({ engine, onChange, onRun, onRemove, t }: any) => (
  <div className="rounded-3xl border border-border bg-bg-elev-1 p-5">
    <div className="mb-4 flex items-center justify-between">
      <div>
        <div className="text-sm font-black text-text">{engine.name}</div>
        <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-text-3">{engine.type}</div>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" className="rounded-xl bg-brand px-4 py-2 text-[10px] font-black uppercase tracking-[0.16em] text-white" onClick={onRun}>
          {t('simulation.engineRun')}
        </button>
        <button type="button" className="rounded-xl border border-red/40 px-2 py-2 text-red hover:bg-red/10" onClick={onRemove} title={t('simulation.removeEngine')}>
          <X size={14} />
        </button>
      </div>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <input value={engine.name} onChange={(event: any) => onChange({ ...engine, name: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
      <input value={engine.summary} onChange={(event: any) => onChange({ ...engine, summary: event.target.value })} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('simulation.summary')} />
    </div>
    <textarea value={engine.promptOverride || ''} onChange={(event: any) => onChange({ ...engine, promptOverride: event.target.value })} className="mt-4 h-28 w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('simulation.promptOverride')} />
    <textarea value={engine.inputNotes || ''} onChange={(event: any) => onChange({ ...engine, inputNotes: event.target.value })} className="mt-4 h-24 w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" placeholder={t('simulation.inputNotes')} />
  </div>
);

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
    <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <div className="mt-2 text-2xl font-black text-text">{value}</div>
  </div>
);
