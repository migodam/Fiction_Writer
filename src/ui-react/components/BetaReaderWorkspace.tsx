import React, { useMemo, useState } from 'react';
import { BarChart3, Heart, Plus, Sparkles, Trash2, TrendingUp, UserCheck, Users } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { cn } from '../utils';
import { useI18n } from '../i18n';

export const BetaReaderWorkspace = () => {
  const { betaPersonas, betaRuns, chapters, addBetaPersona, deleteBetaPersona, runBetaPersona, runBetaReader, w6Status, projectRoot } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const isRunning = w6Status === 'running';
  const [activePersonaId, setActivePersonaId] = useState<string | null>(betaPersonas[0]?.id || null);
  const [draft, setDraft] = useState({ name: '', profile: '' });

  const activePersona = betaPersonas.find((entry) => entry.id === activePersonaId) || null;
  const activeRun = betaRuns.find((entry) => entry.personaId === activePersonaId) || betaRuns[0] || null;
  const aggregate = useMemo(() => {
    if (!betaRuns.length) return { engagement: 0, retention: 0, resonance: 0, pacing: 0, consistency: 0 };
    return betaRuns.reduce((acc, run) => ({
      engagement: acc.engagement + run.aggregate.engagement,
      retention: acc.retention + run.aggregate.retention,
      resonance: acc.resonance + run.aggregate.resonance,
      pacing: acc.pacing + run.aggregate.pacing,
      consistency: acc.consistency + run.aggregate.consistency,
    }), { engagement: 0, retention: 0, resonance: 0, pacing: 0, consistency: 0 });
  }, [betaRuns]);

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-80 border-r border-border bg-bg-elev-1" data-testid="beta-reader-list">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Beta Reader</div>
              <div className="text-sm font-black text-text">{t('beta.readerPersonas', 'Reader Personas')}</div>
            </div>
            <Users size={16} className="text-brand" />
          </div>
          <div className="grid gap-2">
            <input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder={t('beta.personaName', 'Persona name')} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
            <input value={draft.profile} onChange={(event) => setDraft((current) => ({ ...current, profile: event.target.value }))} placeholder={t('beta.personaFocus', 'What do they care about?')} className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
            <button
              type="button"
              className="rounded-2xl bg-brand px-4 py-3 text-sm font-black text-white"
              onClick={() => {
                if (!draft.name.trim()) return;
                addBetaPersona({
                  id: `beta_${Date.now()}`,
                  name: draft.name.trim(),
                  archetype: t('beta.custom', 'Custom'),
                  profile: draft.profile.trim() || t('beta.generalProfile', 'General reader persona.'),
                  tone: 'balanced',
                  focusAreas: ['engagement', 'retention', 'resonance'],
                  weights: { engagement: 80, retention: 76, resonance: 74, pacing: 70, consistency: 68 },
                });
                setDraft({ name: '', profile: '' });
                setLastActionStatus(t('beta.personaCreated', 'Persona created'));
              }}
            >
              <Plus size={14} className="mr-2 inline" />
              {t('beta.createPersona', 'Create Persona')}
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {betaPersonas.map((persona) => (
            <div key={persona.id} role="button" tabIndex={0} className={cn('mb-2 w-full cursor-pointer rounded-2xl border px-4 py-4 text-left transition-colors', activePersonaId === persona.id ? 'border-brand bg-active text-text' : 'border-transparent text-text-2 hover:bg-hover')} onClick={() => setActivePersonaId(persona.id)} onKeyDown={(e) => e.key === 'Enter' && setActivePersonaId(persona.id)} data-testid={`beta-persona-${persona.id}`}>
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-sm font-black text-text">{persona.name}</div>
                <button type="button" className="rounded border border-red/40 p-1 text-red" onClick={(event) => {
                  event.stopPropagation();
                  deleteBetaPersona(persona.id);
                  setLastActionStatus(t('beta.personaDeleted', 'Persona deleted'));
                  if (activePersonaId === persona.id) setActivePersonaId(betaPersonas.find((entry) => entry.id !== persona.id)?.id || null);
                }} data-testid="delete-beta-persona-btn">
                  <Trash2 size={12} />
                </button>
              </div>
              <div className="text-xs leading-relaxed text-text-3">{persona.profile}</div>
            </div>
          ))}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
        <div className="mx-auto max-w-6xl">
          <div className="mb-8 grid gap-4 md:grid-cols-4">
            <MetricCard label={t('beta.engagement', 'Engagement')} value={activeRun?.aggregate.engagement || 0} icon={<TrendingUp size={14} />} />
            <MetricCard label={t('beta.retention', 'Retention')} value={activeRun?.aggregate.retention || 0} icon={<UserCheck size={14} />} />
            <MetricCard label={t('beta.resonance', 'Resonance')} value={activeRun?.aggregate.resonance || 0} icon={<Heart size={14} />} />
            <MetricCard label={t('beta.personas', 'Personas')} value={betaPersonas.length} icon={<Users size={14} />} />
          </div>

          <div className="rounded-[32px] border border-border bg-card p-8 shadow-1">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('beta.currentPersona', 'Current Persona')}</div>
                <div className="mt-2 text-3xl font-black text-text">{activePersona?.name || t('beta.noPersonaSelected', 'No persona selected')}</div>
              </div>
              <button type="button" className="rounded-2xl bg-brand px-8 py-3 text-[11px] font-black uppercase tracking-[0.25em] text-white" disabled={isRunning || !activePersona} onClick={() => { if (activePersona) { void runBetaReader({ projectRoot, persona_id: activePersona.id, target_chapter_ids: chapters.map((c) => c.id) }).then(() => setLastActionStatus(t('beta.readerSimulationComplete', 'Reader simulation complete'))); } }} data-testid="run-beta-reader-btn">
                <Sparkles size={14} className="mr-2 inline" />
                {t('beta.runPersona', 'Run Persona')}
              </button>
            </div>

            <div className="grid gap-6 xl:grid-cols-[1fr_0.85fr]">
              <div>
                <div className="rounded-3xl border border-border bg-bg-elev-1 p-5">
                  <div className="mb-3 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('beta.profile', 'Profile')}</div>
                  <div className="text-sm leading-relaxed text-text-2">{activePersona?.profile || t('beta.selectPersonaPrompt', 'Select a persona to review feedback.')}</div>
                </div>
                <div className="mt-6 space-y-4">
                  {(activeRun?.feedback || []).map((item) => (
                    <div key={item.id} className="rounded-2xl border border-border bg-bg-elev-1 p-5">
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <div className="text-sm font-black text-text">{item.title}</div>
                        <span className="rounded-full border border-border px-2 py-1 text-[9px] font-black uppercase tracking-[0.18em] text-text-3">{item.tag}</span>
                      </div>
                      <div className="text-sm leading-relaxed text-text-2">{item.text}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="rounded-3xl border border-border bg-bg-elev-1 p-5">
                  <div className="mb-4 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                    <BarChart3 size={12} className="text-brand" />
                    {t('beta.aggregateScores', 'Aggregate Scores')}
                  </div>
                  <div className="space-y-4">
                    <AggregateRow label={t('beta.engagement', 'Engagement')} value={Math.round(aggregate.engagement / Math.max(betaRuns.length, 1))} />
                    <AggregateRow label={t('beta.retention', 'Retention')} value={Math.round(aggregate.retention / Math.max(betaRuns.length, 1))} />
                    <AggregateRow label={t('beta.resonance', 'Resonance')} value={Math.round(aggregate.resonance / Math.max(betaRuns.length, 1))} />
                    <AggregateRow label={t('beta.pacing', 'Pacing')} value={Math.round(aggregate.pacing / Math.max(betaRuns.length, 1))} />
                    <AggregateRow label={t('beta.consistency', 'Consistency')} value={Math.round(aggregate.consistency / Math.max(betaRuns.length, 1))} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

const MetricCard = ({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) => (
  <div className="rounded-2xl border border-border bg-card p-4 shadow-1">
    <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
      <span>{label}</span>
      {icon}
    </div>
    <div className="mt-2 text-2xl font-black text-text">{value}%</div>
  </div>
);

const AggregateRow = ({ label, value }: { label: string; value: number }) => (
  <div className="flex items-center gap-4">
    <div className="w-24 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{label}</div>
    <div className="h-2 flex-1 overflow-hidden rounded-full border border-divider bg-bg">
      <div className="h-full bg-brand" style={{ width: `${value}%` }} />
    </div>
    <div className="w-12 text-right text-sm font-black text-text">{value}%</div>
  </div>
);
