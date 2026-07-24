import React from 'react';
import { useProjectStore } from '../store';
import { useI18n } from '../i18n';
import { AgentChat } from './agent';
import { W0OrchestratorPanel } from './agent/W0OrchestratorPanel';
import { RuntimeExecutionSurface } from './agent/RuntimeExecutionSurface';

export const AgentWorkspace = () => {
  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="agent-workspace">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <W0OrchestratorPanel />
        <div className="min-h-0 flex-1">
          <AgentChat />
        </div>
      </div>
      <RuntimePanel />
    </div>
  );
};

const RuntimePanel: React.FC = () => {
  const { w1RuntimeEvents, w1RuntimeCheckpoints, w1RuntimeSelectedAgent, setW1RuntimeSelectedAgent } = useProjectStore();
  const { t } = useI18n();

  return (
    <aside className="w-[22rem] border-l border-border bg-bg-elev-1 p-4" data-testid="agent-runs-panel">
      <RuntimeExecutionSurface events={w1RuntimeEvents} checkpoints={w1RuntimeCheckpoints} selectedAgent={w1RuntimeSelectedAgent} onSelectAgent={setW1RuntimeSelectedAgent} t={t} />
    </aside>
  );
};
