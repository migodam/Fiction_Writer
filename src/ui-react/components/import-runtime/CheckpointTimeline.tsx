import React, { useState } from 'react';
import { GitFork, Eye } from 'lucide-react';
import { useProjectStore } from '../../store';
import { runtimeCheckpointCapability, type RuntimeCheckpoint } from './types';

export const CheckpointTimeline: React.FC<{ checkpoints: RuntimeCheckpoint[]; onFork: (checkpointId: string) => void; action: string | null; t: (key: string, fallback?: string) => string }> = ({ checkpoints, onFork, action, t }) => {
  const [expandedCheckpointId, setExpandedCheckpointId] = useState<string | null>(null);
  const runtimeError = useProjectStore((state) => state.w1RuntimeError);
  if (checkpoints.length === 0) return null;
  const forkError = runtimeError?.startsWith('runtime_fork_') ? runtimeError : null;
  const forkErrorMessage = forkError === 'runtime_fork_not_resumable'
    ? t('import.forkNotResumableError', 'This checkpoint cannot be resumed. The active attempt was not changed.')
    : t('import.forkFailedError', 'The checkpoint fork failed. The active attempt was not changed.');
  return <section className="mt-3 border-t border-border pt-3" data-testid="w1-checkpoint-timeline">
    <div className="text-xs font-semibold text-text">{t('import.timeTravel', 'Time Travel')}</div>
    <p className="mt-1 text-[11px] text-text-3">{t('import.forkNotRewind', 'Preview a checkpoint or fork a new attempt. The current attempt is never rewound.')}</p>
    {forkError && <p className="mt-2 border-l-2 border-red bg-red/10 px-2 py-1 text-[11px] text-red" role="alert" data-testid="w1-checkpoint-fork-error">{forkErrorMessage}</p>}
    <div className="mt-2 flex gap-2 overflow-x-auto pb-1">{checkpoints.map((checkpoint) => {
      const capability = runtimeCheckpointCapability(checkpoint);
      const isExpanded = expandedCheckpointId === checkpoint.checkpoint_id;
      const unavailableReason = capability.reason
        ? `${t('import.checkpointPreviewOnlyReason', 'Preview only: {reason}.').replace('{reason}', capability.reason)}`
        : t('import.checkpointPreviewOnlyLegacy', 'Preview only: this checkpoint has no verified resumable snapshot.');
      const forkTitle = capability.resumable
        ? t('import.forkCheckpoint', 'Fork attempt from checkpoint')
        : unavailableReason;
      return <div key={checkpoint.checkpoint_id} className="min-w-44 border-l-2 border-brand/50 pl-2 text-xs">
        <div className="truncate text-text">{checkpoint.label || checkpoint.checkpoint_id}</div><div className="text-text-3">#{checkpoint.sequence ?? '?'}</div>
        <div className={`mt-1 text-[10px] font-semibold ${capability.resumable ? 'text-green' : 'text-text-3'}`} data-testid={`w1-checkpoint-status-${checkpoint.checkpoint_id}`}>
          {capability.resumable ? t('import.checkpointResumable', 'Resumable') : t('import.checkpointPreviewOnly', 'Preview only')}
        </div>
        {!capability.resumable && <div className="mt-0.5 max-w-52 text-[10px] leading-4 text-text-3" data-testid={`w1-checkpoint-reason-${checkpoint.checkpoint_id}`}>{unavailableReason}</div>}
        <div className="mt-1 flex gap-1">
          <button type="button" title={t('import.previewCheckpoint', 'Preview checkpoint')} aria-label={t('import.previewCheckpoint', 'Preview checkpoint')} aria-expanded={isExpanded} onClick={() => setExpandedCheckpointId(isExpanded ? null : checkpoint.checkpoint_id)} className="rounded p-1 text-text-3 hover:bg-hover" data-testid={`w1-checkpoint-preview-${checkpoint.checkpoint_id}`}><Eye size={13}/></button>
          <button type="button" title={forkTitle} aria-label={forkTitle} onClick={() => onFork(checkpoint.checkpoint_id)} disabled={action !== null || !capability.resumable} className="rounded p-1 text-brand hover:bg-brand/10 disabled:opacity-50" data-testid={`w1-checkpoint-fork-${checkpoint.checkpoint_id}`}><GitFork size={13}/></button>
        </div>
        {isExpanded && <div className="mt-2 max-w-60 border border-border bg-bg-elev-1 p-2 text-[10px] leading-4 text-text-2" data-testid={`w1-checkpoint-details-${checkpoint.checkpoint_id}`}>
          <div>{capability.resumable ? t('import.checkpointDetailsResumable', 'A verified snapshot is available. Forking creates a separate child attempt.') : unavailableReason}</div>
          {checkpoint.summary && <div className="mt-1 text-text-3">{checkpoint.summary}</div>}
        </div>}
      </div>;
    })}</div>
  </section>;
};
