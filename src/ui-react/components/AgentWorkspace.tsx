import React from 'react';
import { CornerDownLeft, FileSearch, Layers3 } from 'lucide-react';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import { AgentChat } from './agent';

export const AgentWorkspace = () => {
  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="agent-workspace">
      <div className="flex-1 overflow-hidden">
        <AgentChat />
      </div>
      <AgentRunsPanel />
    </div>
  );
};

// Right panel showing recent task requests and runs
const AgentRunsPanel: React.FC = () => {
  const { taskRequests, taskRuns, proposals } = useProjectStore();
  const { t } = useI18n();

  return (
    <aside className="w-80 border-l border-border bg-bg-elev-1 overflow-y-auto custom-scrollbar p-5" data-testid="agent-runs-panel">
      <div className="mb-4 grid grid-cols-3 gap-2">
        <MetricCard label={t('agent.requests')} value={String(taskRequests.length)} icon={<Layers3 size={12} />} />
        <MetricCard label={t('agent.runs.title')} value={String(taskRuns.length)} icon={<CornerDownLeft size={12} />} />
        <MetricCard label={t('agent.proposals')} value={String(proposals.length)} icon={<FileSearch size={12} />} />
      </div>

      <div className="mb-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">{t('agent.runs.title')}</div>
      <div className="space-y-2">
        {taskRequests.slice(0, 12).map((task) => (
          <div key={task.id} className="rounded-2xl border border-border bg-card p-3" data-testid={`agent-request-${task.id}`}>
            <div className="text-[10px] font-black text-text line-clamp-2">{task.title}</div>
            <div className="mt-1 text-[9px] uppercase tracking-[0.18em] text-text-3">{task.status}</div>
          </div>
        ))}
      </div>
    </aside>
  );
};

const MetricCard = ({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) => (
  <div className="rounded-2xl border border-border bg-card p-3">
    <div className="flex items-center justify-between text-[9px] font-black uppercase tracking-[0.18em] text-text-3">
      <span>{label}</span>
      {icon}
    </div>
    <div className="mt-1 text-xl font-black text-text">{value}</div>
  </div>
);
