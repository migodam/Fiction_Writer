import React from 'react';
import { GitFork, Eye } from 'lucide-react';
import type { RuntimeCheckpoint } from './types';

export const CheckpointTimeline: React.FC<{ checkpoints: RuntimeCheckpoint[]; onFork: (checkpointId: string) => void; action: string | null; t: (key: string, fallback?: string) => string }> = ({ checkpoints, onFork, action, t }) => {
  if (checkpoints.length === 0) return null;
  return <section className="mt-3 border-t border-border pt-3" data-testid="w1-checkpoint-timeline">
    <div className="text-xs font-semibold text-text">{t('import.timeTravel', 'Time Travel')}</div>
    <p className="mt-1 text-[11px] text-text-3">{t('import.forkNotRewind', 'Preview a checkpoint or fork a new attempt. The current attempt is never rewound.')}</p>
    <div className="mt-2 flex gap-2 overflow-x-auto pb-1">{checkpoints.map((checkpoint) => <div key={checkpoint.checkpoint_id} className="min-w-36 border-l-2 border-brand/50 pl-2 text-xs">
      <div className="truncate text-text">{checkpoint.label || checkpoint.checkpoint_id}</div><div className="text-text-3">#{checkpoint.sequence ?? '?'}</div>
      <div className="mt-1 flex gap-1"><button type="button" title={t('import.previewCheckpoint', 'Preview checkpoint')} className="rounded p-1 text-text-3 hover:bg-hover"><Eye size={13}/></button><button type="button" title={t('import.forkCheckpoint', 'Fork attempt from checkpoint')} onClick={() => onFork(checkpoint.checkpoint_id)} disabled={action !== null} className="rounded p-1 text-brand hover:bg-brand/10 disabled:opacity-50" data-testid={`w1-checkpoint-fork-${checkpoint.checkpoint_id}`}><GitFork size={13}/></button></div>
    </div>)}</div>
  </section>;
};
