import React, { useMemo, useState } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  GitBranch,
  Hammer,
  ListTree,
  PlayCircle,
  ShieldAlert,
  Wrench,
} from 'lucide-react';
import type { RuntimeCheckpoint, RuntimeEvent } from '../import-runtime/types';
import { normalizeAgentEvents, type AgentEventKind, type AgentEventV1 } from './agentEvents';
import { cn } from '../../utils';

type Translator = (key: string, fallback?: string) => string;

const EVENT_ICON: Record<AgentEventKind, React.ReactNode> = {
  plan: <ListTree size={14} />,
  agent: <Bot size={14} />,
  tool: <Wrench size={14} />,
  chunk: <GitBranch size={14} />,
  result: <Hammer size={14} />,
  retry: <GitBranch size={14} />,
  cost: <ClipboardCheck size={14} />,
  recovery: <GitBranch size={14} />,
  approval: <ShieldAlert size={14} />,
  error: <CircleAlert size={14} />,
};

const EVENT_TONE: Record<AgentEventKind, string> = {
  plan: 'text-brand bg-brand/10',
  agent: 'text-text-2 bg-bg-elev-2',
  tool: 'text-brand-2 bg-brand/10',
  chunk: 'text-cyan bg-cyan/10',
  result: 'text-green bg-green/10',
  retry: 'text-amber bg-amber/10',
  cost: 'text-blue bg-blue/10',
  recovery: 'text-cyan bg-cyan/10',
  approval: 'text-amber bg-amber/10',
  error: 'text-red bg-red/10',
};

const labelForKind = (kind: AgentEventKind, t: Translator) => t(`agentRuntime.kind.${kind}`, kind.replace('_', ' '));
const labelForStatus = (status: AgentEventV1['status'], t: Translator) => t(`agentRuntime.status.${status}`, status.replace('_', ' '));

export const RuntimeExecutionSurface: React.FC<{
  events: RuntimeEvent[];
  checkpoints: RuntimeCheckpoint[];
  selectedAgent: string | null;
  onSelectAgent: (agentId: string | null) => void;
  t: Translator;
  compact?: boolean;
  onOpenWorkspace?: () => void;
}> = ({ events, checkpoints, selectedAgent, onSelectAgent, t, compact = false, onOpenWorkspace }) => {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const views = useMemo(() => normalizeAgentEvents(events), [events]);
  const agents = useMemo(() => [...new Set(views.map((item) => item.actorId))], [views]);
  const filtered = selectedAgent ? views.filter((item) => item.actorId === selectedAgent) : views;
  const visible = compact ? filtered.slice(0, 6) : filtered;
  const active = views.find((item) => item.status === 'running') ?? views[0];
  const pendingActions = views.filter((item) => item.requiresAction).length;

  const toggleExpanded = (id: string) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <section className={cn('flex min-h-0 flex-col', compact ? 'gap-3' : 'h-full')} data-testid="agent-runtime-surface">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-brand-2">{t('agentRuntime.execution', 'Execution')}</div>
          <div className="mt-0.5 text-sm font-semibold text-text" data-testid="agent-runtime-stage">{active ? active.summary : t('agentRuntime.waiting', 'Waiting for a runtime event')}</div>
        </div>
        {onOpenWorkspace && <button type="button" onClick={onOpenWorkspace} className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-text-2 hover:bg-hover" data-testid="agent-runtime-open-workspace"><PlayCircle size={13} />{t('agentRuntime.openWorkspace', 'Open')}</button>}
      </div>

      <div className="flex flex-wrap items-center gap-1" data-testid="agent-runtime-agent-filter">
        <button type="button" onClick={() => onSelectAgent(null)} className={cn('rounded border px-2 py-1 text-[10px]', selectedAgent === null ? 'border-brand bg-brand/10 text-brand' : 'border-border text-text-3 hover:bg-hover')} data-testid="agent-runtime-agent-all">{t('agentRuntime.allAgents', 'All agents')}</button>
        {agents.map((agent) => <button type="button" key={agent} onClick={() => onSelectAgent(agent)} className={cn('max-w-32 truncate rounded border px-2 py-1 text-[10px]', selectedAgent === agent ? 'border-brand bg-brand/10 text-brand' : 'border-border text-text-3 hover:bg-hover')} data-testid={`agent-runtime-agent-${agent}`}>{agent}</button>)}
      </div>

      <div className="grid grid-cols-3 gap-px overflow-hidden border border-border bg-border text-xs" data-testid="agent-runtime-summary">
        <Summary label={t('agentRuntime.events', 'Events')} value={String(views.length)} />
        <Summary label={t('agentRuntime.checkpoints', 'Checkpoints')} value={String(checkpoints.length)} />
        <Summary label={t('agentRuntime.actions', 'Actions')} value={String(pendingActions)} tone={pendingActions > 0 ? 'text-amber' : undefined} />
      </div>

      {pendingActions > 0 && <div className="border-l-2 border-amber bg-amber/10 px-2 py-1.5 text-[11px] text-text-2" data-testid="agent-runtime-human-action">{t('agentRuntime.humanAction', 'Human action is required before this run can continue.')}</div>}

      <div className={cn('min-h-0 space-y-1 overflow-y-auto custom-scrollbar', compact ? 'max-h-80' : 'flex-1 pr-1')} data-testid="agent-runtime-event-list">
        {visible.length === 0 && <div className="border border-dashed border-border px-3 py-4 text-xs text-text-3" data-testid="agent-runtime-empty">{t('agentRuntime.empty', 'No durable execution events yet.')}</div>}
        {visible.map((item) => {
          const isExpanded = expanded.has(item.id);
          return <article key={item.id} className="border border-border bg-bg" data-testid={`agent-runtime-event-${item.id}`}>
            <button type="button" onClick={() => toggleExpanded(item.id)} className="flex w-full items-start gap-2 px-2 py-2 text-left hover:bg-hover" aria-expanded={isExpanded}>
              <span className={cn('mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center', EVENT_TONE[item.kind])}>{EVENT_ICON[item.kind]}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2"><span className="text-[10px] font-semibold uppercase tracking-wide text-text-3">{labelForKind(item.kind, t)}</span><span className="truncate text-[10px] text-text-3">{item.actorId}</span><span className={cn('shrink-0 text-[10px] font-semibold', item.status === 'failed' || item.status === 'blocked' || item.status === 'unknown_outcome' ? 'text-red' : item.status === 'recovering' ? 'text-cyan' : 'text-text-3')}>{labelForStatus(item.status, t)}</span></span>
                <span className="mt-0.5 block break-words text-xs text-text">{item.title}: {item.summary}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-[10px] text-text-3">{item.chunk && <span>{item.chunk}</span>}{item.retry && <span>R{item.retry}</span>}{item.costUsd !== null && <span>${item.costUsd.toFixed(4)}</span>}{isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
            </button>
            {isExpanded && <div className="border-t border-border px-3 py-2 text-[11px] text-text-2" data-testid={`agent-runtime-event-detail-${item.id}`}>
              {item.tool && <p><strong>{t('agentRuntime.tool', 'Tool')}:</strong> {item.tool}</p>}
              {item.detail && <p className={item.tool ? 'mt-1' : undefined}>{item.detail}</p>}
              <p className={item.detail || item.tool ? 'mt-1' : undefined}>{t('agentRuntime.sequence', 'Sequence')} #{item.sequence}{item.timestamp ? ` · ${item.timestamp}` : ''}</p>
              {item.requiresAction && <p className="mt-1 font-medium text-amber">{t('agentRuntime.requiresApproval', 'Awaiting a recorded human decision.')}</p>}
            </div>}
          </article>;
        })}
      </div>
      {compact && filtered.length > visible.length && <button type="button" className="text-left text-xs text-brand hover:underline" onClick={onOpenWorkspace}>{t('agentRuntime.moreEvents', 'Open full execution history')}</button>}
      <p className="text-[10px] leading-4 text-text-3" data-testid="agent-runtime-no-hidden-thought">{t('agentRuntime.noHiddenThought', 'Shows durable actions, tool results, and decisions. Private reasoning is not displayed.')}</p>
    </section>
  );
};

const Summary: React.FC<{ label: string; value: string; tone?: string }> = ({ label, value, tone }) => <div className="bg-bg-elev-1 px-2 py-2"><div className="text-[9px] uppercase tracking-wide text-text-3">{label}</div><div className={cn('mt-0.5 text-sm font-semibold text-text', tone)}>{value}</div></div>;
