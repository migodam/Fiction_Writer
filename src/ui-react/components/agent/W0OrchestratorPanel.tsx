import React, { useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, ClipboardList, Loader2, Play, RotateCcw, ShieldAlert, XCircle } from 'lucide-react';
import { useProjectStore } from '../../store';
import { cn } from '../../utils';

type OrchestratorStep = {
  step_id?: string;
  workflow?: string;
  rationale?: string;
  status?: string;
  requires_permission?: boolean;
  config?: Record<string, unknown>;
};

type PermissionRequest = {
  step_id?: string;
  description?: string;
  risk_level?: string;
  affected_entities?: string[];
};

const statusLabel: Record<string, string> = {
  idle: 'Idle',
  planning: 'Planning',
  executing: 'Executing',
  waiting_permission: 'Needs permission',
  done: 'Done',
  error: 'Error',
};

const isBusyStatus = (status: string) => status === 'planning' || status === 'executing';

export const W0OrchestratorPanel: React.FC = () => {
  const {
    projectRoot,
    orchestratorStatus,
    orchestratorProgress,
    orchestratorPlan,
    orchestratorCurrentStep,
    orchestratorPendingPermission,
    orchestratorErrors,
    orchestratorSessionId,
    startOrchestrator,
    grantPermission,
    denyPermission,
    resetOrchestrator,
  } = useProjectStore();

  const [goal, setGoal] = useState('');
  const [denyReason, setDenyReason] = useState('Denied from W0 control surface');

  const plan = orchestratorPlan as OrchestratorStep[];
  const permission = orchestratorPendingPermission as PermissionRequest | null;
  const busy = isBusyStatus(orchestratorStatus);
  const percent = Math.round(Math.max(0, Math.min(orchestratorProgress, 1)) * 100);
  const canStart = goal.trim().length > 0 && !busy && orchestratorStatus !== 'waiting_permission';
  const statusTone = useMemo(() => {
    if (orchestratorStatus === 'done') return 'text-green-400';
    if (orchestratorStatus === 'error') return 'text-red-400';
    if (orchestratorStatus === 'waiting_permission') return 'text-amber-400';
    if (busy) return 'text-brand';
    return 'text-text-3';
  }, [busy, orchestratorStatus]);

  const start = async () => {
    if (!canStart) return;
    await startOrchestrator({
      projectRoot,
      goal: goal.trim(),
      auto_apply_threshold: 0.85,
    });
  };

  const pendingStepId = permission?.step_id ?? plan[orchestratorCurrentStep]?.step_id ?? '';

  return (
    <section className="border-b border-border bg-bg-elev-1 p-4" data-testid="w0-orchestrator-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-brand/30 bg-brand/10 text-brand">
            <ClipboardList size={16} />
          </div>
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-brand-2">W0 Orchestrator</div>
            <div className="text-sm font-black text-text">Goal planner and workflow control</div>
          </div>
        </div>
        <div className={cn('flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em]', statusTone)} data-testid="w0-status">
          {busy && <Loader2 size={13} className="animate-spin" />}
          {orchestratorStatus === 'done' && <CheckCircle2 size={13} />}
          {orchestratorStatus === 'error' && <AlertCircle size={13} />}
          {orchestratorStatus === 'waiting_permission' && <ShieldAlert size={13} />}
          <span>{statusLabel[orchestratorStatus] ?? orchestratorStatus}</span>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <label className="block">
          <span className="sr-only">Orchestrator goal</span>
          <textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="Describe the workflow goal W0 should plan and run."
            rows={3}
            className="w-full resize-none rounded-xl border border-border bg-bg px-3 py-2 text-sm text-text outline-none placeholder:text-text-3 focus:border-brand"
            data-testid="w0-goal-input"
            disabled={busy || orchestratorStatus === 'waiting_permission'}
          />
        </label>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={() => void start()}
            disabled={!canStart}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.18em] text-white disabled:opacity-40"
            data-testid="w0-start-btn"
          >
            <Play size={14} />
            Start W0
          </button>
          <button
            type="button"
            onClick={resetOrchestrator}
            disabled={busy}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-bg px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.18em] text-text-2 disabled:opacity-40"
            data-testid="w0-reset-btn"
          >
            <RotateCcw size={14} />
            Reset
          </button>
        </div>
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
          <span data-testid="w0-step-counter">Step {Math.min(orchestratorCurrentStep + 1, Math.max(plan.length, 1))} / {Math.max(plan.length, 1)}</span>
          <span data-testid="w0-progress-label">{percent}%</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-bg">
          <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${percent}%` }} data-testid="w0-progress-bar" />
        </div>
        {orchestratorSessionId && (
          <div className="mt-2 text-[10px] text-text-3" data-testid="w0-session-id">
            Session {orchestratorSessionId}
          </div>
        )}
      </div>

      {permission && (
        <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3" data-testid="w0-permission-card">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.18em] text-amber-400">
            <ShieldAlert size={13} />
            Permission required
          </div>
          <div className="mt-2 text-sm font-semibold text-text">{permission.description ?? 'W0 needs approval before continuing.'}</div>
          <div className="mt-1 text-[11px] text-text-3">
            Risk: {permission.risk_level ?? 'unknown'}
            {permission.affected_entities?.length ? ` · Affects: ${permission.affected_entities.join(', ')}` : ''}
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => void grantPermission(projectRoot, pendingStepId)}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand px-3 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-white"
              data-testid="w0-grant-btn"
            >
              <CheckCircle2 size={13} />
              Grant
            </button>
            <input
              value={denyReason}
              onChange={(event) => setDenyReason(event.target.value)}
              className="min-w-0 flex-1 rounded-xl border border-border bg-bg px-3 py-2 text-xs text-text outline-none focus:border-brand"
              data-testid="w0-deny-reason-input"
            />
            <button
              type="button"
              onClick={() => void denyPermission(projectRoot, pendingStepId, denyReason.trim() || 'Denied')}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-400/40 bg-red-400/10 px-3 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-red-400"
              data-testid="w0-deny-btn"
            >
              <XCircle size={13} />
              Deny
            </button>
          </div>
        </div>
      )}

      {orchestratorStatus === 'error' && (
        <div className="mt-4 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200" data-testid="w0-error-card">
          {orchestratorErrors.length > 0 ? orchestratorErrors.join('\n') : 'W0 stopped before completion. Check provider settings or sidecar status, then reset and retry.'}
        </div>
      )}

      {orchestratorStatus === 'done' && (
        <div className="mt-4 rounded-xl border border-green-400/30 bg-green-400/10 p-3 text-sm text-green-200" data-testid="w0-result-card">
          W0 completed the planned workflow path.
        </div>
      )}

      <div className="mt-4 grid gap-2" data-testid="w0-plan-list">
        {plan.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-bg p-3 text-sm text-text-3" data-testid="w0-plan-empty">
            No plan yet.
          </div>
        ) : plan.map((step, index) => (
          <div key={step.step_id ?? index} className="rounded-xl border border-border bg-bg p-3" data-testid={`w0-plan-step-${index}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
                {step.workflow ?? 'Workflow'} · {step.step_id ?? `step_${index + 1}`}
              </div>
              <div className="rounded-lg border border-border bg-bg-elev-2 px-2 py-1 text-[9px] font-black uppercase tracking-[0.16em] text-text-3">
                {step.status ?? 'pending'}
              </div>
            </div>
            <div className="mt-2 text-sm text-text-2">{step.rationale || 'No rationale provided.'}</div>
          </div>
        ))}
      </div>
    </section>
  );
};
