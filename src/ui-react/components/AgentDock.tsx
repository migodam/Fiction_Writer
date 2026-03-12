import React from 'react';
import { Bot, ChevronRight, FolderKanban, ShieldAlert, Sparkles } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';

export const AgentDock = () => {
  const { isAgentDockOpen, toggleAgentDock } = useUIStore();
  const { projectRoot, projectName, proposals, issues, selectedEntity, taskRequests, taskRuns, taskArtifacts } = useProjectStore();
  const { t } = useI18n();

  if (!isAgentDockOpen) {
    return (
      <aside
        className="h-full border-l border-border bg-bg-elev-1 flex flex-col items-center py-4 gap-4"
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
          <FolderKanban size={16} />
          <Sparkles size={16} />
          <ShieldAlert size={16} />
        </div>
      </aside>
    );
  }

  return (
    <aside className="h-full border-l border-border bg-bg-elev-1 flex flex-col" data-testid="agent-dock">
      <div className="flex items-center justify-between border-b border-border px-4 py-3 bg-bg-elev-2">
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

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar space-y-4">
        <section className="rounded-2xl border border-border bg-card p-4 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('agentDock.project')}</div>
          <div className="mt-2 text-lg font-black text-text">{projectName}</div>
          <div className="mt-3 break-all text-xs leading-relaxed text-text-2">{projectRoot}</div>
        </section>

        <section className="rounded-2xl border border-border bg-card p-4 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('agentDock.liveQueue')}</div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Metric label="Inbox" value={String(proposals.length)} />
            <Metric label="Issues" value={String(issues.length)} />
            <Metric label="Tasks" value={String(taskRequests.filter((entry) => entry.status === 'queued' || entry.status === 'running').length)} />
            <Metric label="Runs" value={String(taskRuns.length)} />
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card p-4 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('agentDock.context')}</div>
          <div className="mt-3 text-sm text-text-2">
            {selectedEntity.id ? `Selected ${selectedEntity.type}: ${selectedEntity.id}` : t('agentDock.noContext')}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card p-4 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Task Queue</div>
          <div className="mt-3 space-y-3">
            {taskRequests.slice(0, 4).map((task) => (
              <div key={task.id} className="rounded-xl border border-border bg-bg p-3">
                <div className="text-sm font-bold text-text">{task.title}</div>
                <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-text-3">{task.status} · {task.source}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card p-4 shadow-1">
          <div className="text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Artifacts</div>
          <div className="mt-3 space-y-3">
            {taskArtifacts.slice(0, 3).map((artifact) => (
              <div key={artifact.id} className="rounded-xl border border-border bg-bg p-3">
                <div className="text-sm font-bold text-text">{artifact.summary}</div>
                <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-text-3">{artifact.type}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-dashed border-border bg-bg p-4 text-sm text-text-2">
          {t('agentDock.future')}
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
