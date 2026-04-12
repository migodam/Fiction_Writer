import React from 'react';
import { Bot, ChevronRight } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';

export const AgentDock = () => {
  const { isAgentDockOpen, toggleAgentDock } = useUIStore();
  const {
    taskRequests,
    taskRuns,
  } = useProjectStore();
  const { t } = useI18n();

  if (!isAgentDockOpen) {
    return (
      <aside
        className="flex h-full flex-col items-center gap-4 border-l border-border bg-bg-elev-1 py-4"
        data-testid="agent-dock-collapsed"
      >
        <button
          type="button"
          data-testid="agent-dock-expand"
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-bg-elev-2 text-brand transition-all hover:border-brand"
          onClick={() => toggleAgentDock(true)}
        >
          <Bot size={18} />
        </button>
        <div className="flex flex-col items-center gap-3 text-text-3">
          <Bot size={16} />
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-full flex-col border-l border-border bg-bg-elev-1" data-testid="agent-dock">
      <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand/30 bg-brand/10 text-brand">
            <Bot size={18} />
          </div>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">{t('agentDock.title')}</div>
            <div className="text-sm font-black text-text">{t('agentDock.subtitle')}</div>
          </div>
        </div>
        <button
          type="button"
          className="rounded-lg border border-border p-2 text-text-3 transition-colors hover:text-text"
          onClick={() => toggleAgentDock(false)}
          data-testid="agent-dock-collapse"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
        {/* Active tasks */}
        <section className="rounded-2xl border border-border bg-card p-4 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('agentDock.liveQueue')}</div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <Metric label={t('agentDock.queued')} value={String(taskRequests.filter((r) => r.status === 'queued').length)} />
            <Metric label={t('agentDock.running')} value={String(taskRuns.filter((r) => r.status === 'running').length)} />
          </div>
          {taskRuns.length > 0 && (
            <div className="mt-3 space-y-2">
              {taskRuns.slice(0, 3).map((run) => (
                <div key={run.id} className="rounded-xl border border-border bg-bg px-3 py-2">
                  <div className="text-[10px] font-black text-text line-clamp-1">{run.summary}</div>
                  <div className="mt-0.5 text-[9px] uppercase tracking-wider text-text-3">{run.status}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Quick link to agents */}
        <section className="rounded-2xl border border-dashed border-border bg-bg p-4 text-sm text-text-2">
          {t('agentDock.viewHistory')}
        </section>
      </div>
    </aside>
  );
};

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-xl border border-border bg-bg-elev-2 p-3">
    <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{label}</div>
    <div className="mt-2 text-2xl font-black text-text">{value}</div>
  </div>
);
