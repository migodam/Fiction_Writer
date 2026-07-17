import React from 'react';
import { AlertTriangle, Pause, Play, RefreshCw, RotateCcw, X } from 'lucide-react';
import { useProjectStore } from '../../store';
import type { RuntimeRun, RuntimeUnknownCall } from './types';

interface RecoveryCenterProps {
  runs: RuntimeRun[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onResume: (run: RuntimeRun) => void;
  onPause: () => void;
  onCancel: () => void;
  activeLineageId: string | null;
  action: string | null;
  t: (key: string, fallback?: string) => string;
}

export const RecoveryCenter: React.FC<RecoveryCenterProps> = ({ runs, loading, error, onRefresh, onResume, onPause, onCancel, activeLineageId, action, t }) => {
  const decideUnknownOutcome = useProjectStore((state) => state.decideW1UnknownOutcome);
  if (!loading && !error && runs.length === 0) return null;
  return <section className="mb-4 border-y border-border py-3" data-testid="w1-recovery-center">
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-text"><AlertTriangle size={14} className="text-amber" />{t('import.recoveryCenter', 'Recovery Center')}</div>
      <div className="flex items-center gap-1"><button type="button" title={t('import.pause', 'Pause')} onClick={onPause} disabled={!activeLineageId || action !== null} className="rounded p-1 text-text-3 disabled:opacity-40 hover:bg-hover hover:text-text" data-testid="w1-runtime-pause"><Pause size={14} /></button><button type="button" title={t('import.cancel', 'Cancel')} onClick={onCancel} disabled={!activeLineageId || action !== null} className="rounded p-1 text-text-3 disabled:opacity-40 hover:bg-hover hover:text-red" data-testid="w1-runtime-cancel"><X size={14} /></button><button type="button" title={t('import.refreshRecovery', 'Refresh recovery runs')} onClick={onRefresh} className="rounded p-1 text-text-3 hover:bg-hover hover:text-text" data-testid="w1-recovery-refresh"><RefreshCw size={14} /></button></div>
    </div>
    {error === 'needs_credentials' ? <p className="mt-2 text-xs text-amber" data-testid="w1-recovery-needs-credentials">{t('import.needsCredentials', 'Add an API key to the active provider in Settings, then resume this attempt.')}</p> : null}
    {error === 'runtime_decision_failed' ? <p className="mt-2 text-xs text-red" data-testid="w1-unknown-decision-error">{t('import.unknownDecisionFailed', 'The decision could not be saved. No retry or cancellation was performed.')}</p> : null}
    {error && error !== 'needs_credentials' && error !== 'runtime_decision_failed' ? <p className="mt-2 text-xs text-text-3" data-testid="w1-recovery-fallback">{t('import.recoveryUnavailable', 'Recovery runtime unavailable; legacy import controls remain available.')}</p> : null}
    {runs.map((run) => <div key={run.lineage_id} className="mt-2 grid items-center gap-2 text-xs sm:grid-cols-[1fr_auto]" data-testid={`w1-recovery-run-${run.lineage_id}`}>
      <div className="min-w-0 text-text-2">
        <div className="font-medium text-text">{run.summary || run.lineage_id}</div>
        <div className="mt-0.5 text-text-3">{t('import.recoveryProgress', 'Completed {completed}; remaining {remaining}.').replace('{completed}', String(run.completed ?? '?')).replace('{remaining}', String(run.remaining ?? '?'))} {run.source_compatible === false ? t('import.sourceIncompatible', 'Source changed') : t('import.sourceCompatible', 'Source compatible')} {run.api_cost_usd == null ? t('import.costUnknown', 'Cost unknown') : `$${run.api_cost_usd.toFixed(2)}`}</div>
        {run.unknown_calls?.map((call) => <UnknownOutcomeDecision key={call.tool_call_id} run={run} call={call} action={action} onDecision={decideUnknownOutcome} t={t} />)}
      </div>
      <button type="button" onClick={() => onResume(run)} disabled={action !== null || run.source_compatible === false || run.unknown_calls?.some((call) => call.decision_state !== 'authorize_retry_once')} className="inline-flex items-center justify-center gap-1 rounded border border-brand/40 px-2 py-1 text-[11px] font-semibold text-brand disabled:opacity-50 hover:bg-brand/10" data-testid={`w1-recovery-resume-${run.lineage_id}`}><Play size={12}/>{t('import.resume', 'Resume')}</button>
    </div>)}
  </section>;
};

const UnknownOutcomeDecision: React.FC<{
  run: RuntimeRun;
  call: RuntimeUnknownCall;
  action: string | null;
  onDecision: ReturnType<typeof useProjectStore.getState>['decideW1UnknownOutcome'];
  t: RecoveryCenterProps['t'];
}> = ({ run, call, action, onDecision, t }) => {
  const isPending = call.decision_state === 'pending';
  const isWorking = action?.endsWith(`:${call.tool_call_id}`) ?? false;
  return <div className="mt-2 border-l-2 border-amber bg-amber/10 px-3 py-2" data-testid={`w1-unknown-outcome-${call.tool_call_id}`}>
    <div className="flex items-center gap-1.5 font-semibold text-text"><AlertTriangle size={13} className="shrink-0 text-amber" />{t('import.unknownOutcomeTitle', 'Paid provider call has an unknown outcome')}</div>
    <p className="mt-1 text-[11px] leading-4 text-text-2">{t('import.unknownOutcomeBody', 'The provider may have completed this paid call, but its response was not confirmed. It will not be retried until you explicitly authorize one retry.')}</p>
    <div className="mt-1 break-all text-[11px] text-text-3">{t('import.toolCallId', 'Tool call ID')}: {call.tool_call_id}</div>
    <div className="text-[11px] text-text-3">{t('import.safeReason', 'Reason')}: {call.safe_reason === 'transport_outcome_unknown' ? t('import.transportOutcomeUnknown', 'Connection ended before the outcome could be confirmed.') : call.safe_reason}</div>
    {isPending ? <div className="mt-2 flex flex-wrap gap-2">
      <button type="button" onClick={() => void onDecision(run, call, 'authorize_retry_once')} disabled={action !== null} className="inline-flex items-center gap-1 rounded border border-brand/40 px-2 py-1 text-[11px] font-semibold text-brand hover:bg-brand/10 disabled:opacity-50" data-testid={`w1-unknown-authorize-${call.tool_call_id}`}><RotateCcw size={12} />{isWorking && action?.includes('authorize_retry_once') ? t('import.savingDecision', 'Saving decision...') : t('import.authorizeOneRetry', 'Authorize one retry')}</button>
      <button type="button" onClick={() => void onDecision(run, call, 'cancel')} disabled={action !== null} className="inline-flex items-center gap-1 rounded border border-red/40 px-2 py-1 text-[11px] font-semibold text-red hover:bg-red/10 disabled:opacity-50" data-testid={`w1-unknown-cancel-${call.tool_call_id}`}><X size={12} />{isWorking && action?.includes(':cancel:') ? t('import.savingDecision', 'Saving decision...') : t('import.cancelUnknownCall', 'Cancel attempt')}</button>
    </div> : <div className="mt-2 text-[11px] font-semibold text-text-2" data-testid={`w1-unknown-decision-${call.tool_call_id}`}>{call.decision_state === 'authorize_retry_once' ? t('import.retryAuthorized', 'One retry authorized') : t('import.attemptCancelled', 'Attempt cancelled')}</div>}
  </div>;
};
