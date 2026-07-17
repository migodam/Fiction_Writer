import React, { useMemo } from 'react';
import { Network } from 'lucide-react';
import { runtimeAgentId, runtimeSummary, type RuntimeEvent } from './types';

export const AgentDag: React.FC<{ events: RuntimeEvent[]; selectedAgent: string | null; onSelect: (agent: string | null) => void; t: (key: string, fallback?: string) => string }> = ({ events, selectedAgent, onSelect, t }) => {
  const agents = useMemo(() => Array.from(new Map(events.map((event) => [runtimeAgentId(event), runtimeSummary(event)])).entries()), [events]);
  if (agents.length === 0) return null;
  return <section className="mt-3 border-t border-border pt-3" data-testid="w1-runtime-dag"><div className="flex items-center gap-2 text-xs font-semibold text-text"><Network size={14}/>{t('import.agentDag', 'Agent activity')}</div><div className="mt-2 flex flex-wrap gap-1">
    {agents.map(([id, summary]) => <button type="button" key={id} onClick={() => onSelect(selectedAgent === id ? null : id)} className={`max-w-44 truncate rounded border px-2 py-1 text-[11px] ${selectedAgent === id ? 'border-brand bg-brand/10 text-brand' : 'border-border text-text-2 hover:bg-hover'}`} title={summary} data-testid={`w1-runtime-agent-${id}`}>{id}</button>)}
  </div></section>;
};
