import React, { useMemo, useState } from 'react';
import { BarChart3, Brain, Flame, Heart, Plus, Sparkles, Star, Trash2, TrendingUp, UserCheck, Users } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

export const BetaReaderWorkspace = () => {
  const { betaPersonas, betaRuns, addBetaPersona, deleteBetaPersona, runBetaPersona } = useProjectStore();
  const { setLastActionStatus } = useUIStore();
  const { t } = useI18n();
  const [activePersonaId, setActivePersonaId] = useState<string | null>(betaPersonas[0]?.id || null);
  const [draftName, setDraftName] = useState('');
  const [draftProfile, setDraftProfile] = useState('');

  const activePersona = betaPersonas.find((persona) => persona.id === activePersonaId) || null;
  const activeRun = betaRuns.find((run) => run.personaId === activePersonaId) || betaRuns[0] || null;
  const aggregate = useMemo(() => {
    if (!betaRuns.length) return { engagement: 0, retention: 0, resonance: 0, pacing: 0, consistency: 0 };
    const totals = betaRuns.reduce((acc, run) => ({
      engagement: acc.engagement + run.aggregate.engagement,
      retention: acc.retention + run.aggregate.retention,
      resonance: acc.resonance + run.aggregate.resonance,
      pacing: acc.pacing + run.aggregate.pacing,
      consistency: acc.consistency + run.aggregate.consistency,
    }), { engagement: 0, retention: 0, resonance: 0, pacing: 0, consistency: 0 });
    return {
      engagement: Math.round(totals.engagement / betaRuns.length),
      retention: Math.round(totals.retention / betaRuns.length),
      resonance: Math.round(totals.resonance / betaRuns.length),
      pacing: Math.round(totals.pacing / betaRuns.length),
      consistency: Math.round(totals.consistency / betaRuns.length),
    };
  }, [betaRuns]);

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-80 border-r border-border bg-bg-elev-1" data-testid="beta-reader-list">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('beta.title')}</div>
              <div className="text-sm font-black text-text">Persona Lab</div>
            </div>
            <Users size={16} className="text-brand" />
          </div>
          <div className="grid gap-2">
            <input value={draftName} onChange={(event) => setDraftName(event.target.value)} placeholder="Persona name" className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
            <input value={draftProfile} onChange={(event) => setDraftProfile(event.target.value)} placeholder="What does this reader care about?" className="rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
            <button type="button" className="rounded-2xl bg-brand px-4 py-3 text-sm font-black text-white" onClick={() => {
              if (!draftName.trim()) return;
              addBetaPersona({
                id: `beta_${Date.now()}`,
                name: draftName.trim(),
                archetype: 'Custom',
                profile: draftProfile.trim() || 'General feedback persona.',
                tone: 'balanced',
                focusAreas: ['engagement', 'retention', 'resonance'],
                weights: { engagement: 80, retention: 76, resonance: 74, pacing: 70, consistency: 68 },
              });
              setDraftName('');
              setDraftProfile('');
              setLastActionStatus('Persona created');
            }}>
              <Plus size={14} className="mr-2 inline" />Create Persona
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {betaPersonas.map((persona) => (
            <button
              type="button"
              key={persona.id}
              data-testid={`beta-persona-${persona.id}`}
              className={cn('mb-2 w-full rounded-2xl border px-4 py-4 text-left transition-colors', activePersonaId === persona.id ? 'border-brand bg-active text-text' : 'border-transparent text-text-2 hover:bg-hover')}
              onClick={() => setActivePersonaId(persona.id)}
            >
              <div className="mb-2 flex items-center justify-between">
                <div className="text-sm font-black">{persona.name}</div>
                {!['beta_logician', 'beta_empath', 'beta_generalist'].includes(persona.id) && (
                  <button type="button" className="rounded border border-red/40 p-1 text-red" onClick={(event) => {
                    event.stopPropagation();
                    deleteBetaPersona(persona.id);
                  }}>
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
              <div className="text-xs leading-relaxed text-text-3">{persona.profile}</div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto custom-scrollbar p-10">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 grid gap-6 xl:grid-cols-[1fr_0.9fr]">
            <div className="rounded-[32px] border border-border bg-card p-8 shadow-1">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">{t('beta.subtitle')}</div>
                  <h2 className="mt-2 text-3xl font-black text-text">{activePersona?.name || 'Synthetic Cohort'}</h2>
                </div>
                <button type="button" data-testid="run-beta-reader-btn" className="rounded-2xl bg-brand px-8 py-3 text-[11px] font-black uppercase tracking-[0.25em] text-white shadow-2" onClick={() => {
                  if (!activePersona) return;
                  runBetaPersona(activePersona.id);
                  setLastActionStatus('Beta simulation complete');
                }}>
                  <Flame size={15} className="mr-2 inline" />{t('beta.run')}
                </button>
              </div>
              <p className="mb-6 text-sm leading-relaxed text-text-2">{activePersona?.profile || 'Select a persona to run a narrative review.'}</p>
              <div className="grid gap-4 md:grid-cols-3">
                <MetricCard label="Engagement" value={activeRun?.aggregate.engagement || 0} icon={<TrendingUp size={14} />} color="bg-amber-400" />
                <MetricCard label="Retention" value={activeRun?.aggregate.retention || 0} icon={<UserCheck size={14} />} color="bg-sky-400" />
                <MetricCard label="Resonance" value={activeRun?.aggregate.resonance || 0} icon={<Heart size={14} />} color="bg-red-400" />
              </div>
            </div>
            <div className="rounded-[32px] border border-border bg-card p-8 shadow-1">
              <div className="mb-5 flex items-center gap-3">
                <BarChart3 size={16} className="text-brand" />
                <div className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">Aggregate Panel</div>
              </div>
              <div className="space-y-4">
                <AggregateRow label="Engagement" value={aggregate.engagement} />
                <AggregateRow label="Retention" value={aggregate.retention} />
                <AggregateRow label="Resonance" value={aggregate.resonance} />
                <AggregateRow label="Pacing" value={aggregate.pacing} />
                <AggregateRow label="Consistency" value={aggregate.consistency} />
              </div>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
            <div className="rounded-[32px] border border-border bg-card p-8 shadow-1">
              <div className="mb-6 flex items-center gap-3">
                <Sparkles size={15} className="text-brand" />
                <h3 className="text-[11px] font-black uppercase tracking-[0.35em] text-text-3">{t('beta.feedback')}</h3>
              </div>
              <div className="space-y-4">
                {(activeRun?.feedback || []).map((item) => (
                  <div key={item.id} className="rounded-2xl border border-border bg-bg-elev-1 p-5">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-sm font-black text-text">{item.title}</div>
                      <span className={cn('rounded-full border px-2 py-1 text-[9px] font-black uppercase tracking-[0.18em]', item.type === 'positive' ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : item.type === 'critical' ? 'border-red-400/30 bg-red-400/10 text-red-300' : 'border-sky-400/30 bg-sky-400/10 text-sky-300')}>{item.tag}</span>
                    </div>
                    <div className="text-sm leading-relaxed text-text-2">{item.text}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[32px] border border-border bg-card p-8 shadow-1">
              <div className="mb-6 flex items-center gap-3">
                <Brain size={16} className="text-brand" />
                <div className="text-[11px] font-black uppercase tracking-[0.35em] text-text-3">Highlights</div>
              </div>
              <div className="space-y-4">
                {(activeRun?.aggregate.highlights || []).map((highlight, index) => (
                  <div key={`${highlight}-${index}`} className="rounded-2xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2">
                    <Star size={13} className="mr-3 inline text-brand" />{highlight}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

const MetricCard = ({ label, value, icon, color }: { label: string; value: number; icon: React.ReactNode; color: string }) => (
  <div className="rounded-2xl border border-border bg-bg-elev-1 p-5">
    <div className="mb-4 flex items-center justify-between">
      <span className="text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{label}</span>
      <div className="text-text-3">{icon}</div>
    </div>
    <div className="flex items-end gap-3">
      <div className="text-3xl font-black text-text">{value}%</div>
      <div className="mb-1 h-2 flex-1 overflow-hidden rounded-full border border-divider bg-bg">
        <div className={cn('h-full', color)} style={{ width: `${value}%` }} />
      </div>
    </div>
  </div>
);

const AggregateRow = ({ label, value }: { label: string; value: number }) => (
  <div className="flex items-center gap-4">
    <div className="w-28 text-[10px] font-black uppercase tracking-[0.25em] text-text-3">{label}</div>
    <div className="h-2 flex-1 overflow-hidden rounded-full border border-divider bg-bg">
      <div className="h-full bg-brand" style={{ width: `${value}%` }} />
    </div>
    <div className="w-12 text-right text-sm font-black text-text">{value}%</div>
  </div>
);
