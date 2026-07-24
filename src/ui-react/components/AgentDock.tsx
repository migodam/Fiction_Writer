import React from 'react';
import { Bot, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { RuntimeExecutionSurface } from './agent/RuntimeExecutionSurface';

export const AgentDock = () => {
  const { isAgentDockOpen, toggleAgentDock } = useUIStore();
  const {
    w1RuntimeEvents,
    w1RuntimeCheckpoints,
    w1RuntimeSelectedAgent,
    setW1RuntimeSelectedAgent,
  } = useProjectStore();
  const { t } = useI18n();
  const navigate = useNavigate();

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

      <div className="min-h-0 flex-1 overflow-hidden p-3">
        <RuntimeExecutionSurface
          events={w1RuntimeEvents}
          checkpoints={w1RuntimeCheckpoints}
          selectedAgent={w1RuntimeSelectedAgent}
          onSelectAgent={setW1RuntimeSelectedAgent}
          t={t}
          compact
          onOpenWorkspace={() => navigate('/agents')}
        />
      </div>
    </aside>
  );
};
