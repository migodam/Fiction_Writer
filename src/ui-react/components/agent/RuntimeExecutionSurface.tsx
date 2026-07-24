import React, { useMemo, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  FileOutput,
  GitBranch,
  Hammer,
  ListTree,
  PlayCircle,
  ShieldAlert,
  Wrench,
} from 'lucide-react';
import type { RuntimeCheckpoint, RuntimeEvent } from '../import-runtime/types';
import { runtimeAgentId, runtimeSummary } from '../import-runtime/types';
import { cn } from '../../utils';

export type ExecutionEventKind =
  | 'plan'
  | 'agent'
  | 'tool_call'
  | 'tool_result'
  | 'review'
  | 'approval'
  | 'artifact'
  | 'checkpoint'
  | 'error'
  | 'result';

type Translator = (key: string, fallback?: string) => string;

type EventView = {
  event: RuntimeEvent;
  kind: ExecutionEventKind;
  agentId: string;
  summary: string;
  detail: string | null;
  progress: string | null;
  cost: string | null;
  requiresAction: boolean;
};

const eventKindFor = (event: RuntimeEvent): ExecutionEventKind => {
  const value = event.event_type.toLowerCase().replace(/[.:-]/g, '_');
  if (/(^|_)plan|planner/.test(value)) return 'plan';
  if (/tool.*(call|start|intent)|(^|_)tool_call/.test(value)) return 'tool_call';
  if (/tool.*(result|complete|finish)|(^|_)tool_result/.test(value)) return 'tool_result';
  if (/review|judge|validator/.test(value)) return 'review';
  if (/approval|decision|human_gate|permission/.test(value)) return 'approval';
  if (/artifact|receipt|proposal/.test(value)) return 'artifact';
  if (/checkpoint|snapshot/.test(value)) return 'checkpoint';
  if (/error|failed|failure|blocked|cancel/.test(value)) return 'error';
  if (/result|complete|completed|done|success/.test(value)) return 'result';
  return 'agent';
};

const stringValue = (value: unknown): string | null => {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
};

const firstValue = (payload: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = stringValue(payload[key]);
    if (value) return value;
  }
  return null;
};

const eventViewFor = (event: RuntimeEvent): EventView => {
  const payload = event.payload ?? {};
  const completed = Number(payload.completed ?? payload.completed_steps ?? payload.completedSteps);
  const total = Number(payload.total ?? payload.total_steps ?? payload.totalSteps);
  const percentage = Number(payload.progress ?? payload.progress_percent ?? payload.progressPercent);
  const progress = Number.isFinite(completed) && Number.isFinite(total) && total > 0
    ? `${completed}/${total}`
    : Number.isFinite(percentage) ? `${Math.round(percentage <= 1 ? percentage * 100 : percentage)}%` : null;
  const rawCost = Number(payload.cost_usd ?? payload.costUsd ?? payload.api_cost_usd ?? payload.apiCostUsd);
  const cost = Number.isFinite(rawCost) ? `$${rawCost.toFixed(rawCost < 0.1 ? 4 : 2)}` : null;
  const requiresAction = Boolean(
    payload.requires_human_action ?? payload.requiresHumanAction ?? payload.requires_approval ?? payload.requiresApproval ??
    payload.action_required ?? payload.actionRequired,
  ) || eventKindFor(event) === 'approval';
  return {
    event,
    kind: eventKindFor(event),
    agentId: runtimeAgentId(event),
    summary: runtimeSummary(event),
    detail: firstValue(payload, ['detail', 'reason', 'tool_name', 'toolName', 'artifact_path', 'artifactPath']),
    progress,
    cost,
    requiresAction,
  };
};

const EVENT_ICON: Record<ExecutionEventKind, React.ReactNode> = {
  plan: <ListTree size={14} />,
  agent: <Bot size={14} />,
  tool_call: <Wrench size={14} />,
  tool_result: <Hammer size={14} />,
  review: <ClipboardCheck size={14} />,
  approval: <ShieldAlert size={14} />,
  artifact: <FileOutput size={14} />,
  checkpoint: <GitBranch size={14} />,
  error: <CircleAlert size={14} />,
  result: <CheckCircle2 size={14} />,
};

const EVENT_TONE: Record<ExecutionEventKind, string> = {
  plan: 'text-brand bg-brand/10',
  agent: 'text-text-2 bg-bg-elev-2',
  tool_call: 'text-brand-2 bg-brand/10',
  tool_result: 'text-green bg-green/10',
  review: 'text-blue bg-blue/10',
  approval: 'text-amber bg-amber/10',
  artifact: 'text-cyan bg-cyan/10',
  checkpoint: 'text-text-2 bg-bg-elev-2',
  error: 'text-red bg-red/10',
  result: 'text-green bg-green/10',
};

const labelForKind = (kind: ExecutionEventKind, t: Translator) => t(`agentRuntime.kind.${kind}`, kind.replace('_', ' '));

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
  const views = useMemo(() => events.map(eventViewFor).sort((a, b) => b.event.sequence - a.event.sequence), [events]);
  const agents = useMemo(() => [...new Set(views.map((item) => item.agentId))], [views]);
  const filtered = selectedAgent ? views.filter((item) => item.agentId === selectedAgent) : views;
  const visible = compact ? filtered.slice(0, 6) : filtered;
  const active = views.find((item) => item.kind === 'tool_call' || item.kind === 'agent') ?? views[0];
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
          const isExpanded = expanded.has(item.event.event_id);
          return <article key={item.event.event_id} className="border border-border bg-bg" data-testid={`agent-runtime-event-${item.event.event_id}`}>
            <button type="button" onClick={() => toggleExpanded(item.event.event_id)} className="flex w-full items-start gap-2 px-2 py-2 text-left hover:bg-hover" aria-expanded={isExpanded}>
              <span className={cn('mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center', EVENT_TONE[item.kind])}>{EVENT_ICON[item.kind]}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2"><span className="text-[10px] font-semibold uppercase tracking-wide text-text-3">{labelForKind(item.kind, t)}</span><span className="truncate text-[10px] text-text-3">{item.agentId}</span></span>
                <span className="mt-0.5 block break-words text-xs text-text">{item.summary}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-[10px] text-text-3">{item.progress && <span>{item.progress}</span>}{item.cost && <span>{item.cost}</span>}{isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
            </button>
            {isExpanded && <div className="border-t border-border px-3 py-2 text-[11px] text-text-2" data-testid={`agent-runtime-event-detail-${item.event.event_id}`}>
              {item.detail && <p>{item.detail}</p>}
              <p className={cn(item.detail && 'mt-1')}>{t('agentRuntime.sequence', 'Sequence')} #{item.event.sequence}{item.event.created_at ? ` · ${item.event.created_at}` : ''}</p>
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
