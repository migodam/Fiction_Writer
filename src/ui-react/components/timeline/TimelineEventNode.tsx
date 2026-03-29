import React from 'react';
import { Handle, Position, NodeProps } from '@xyflow/react';

interface EventNodeData {
  label: string;
  importance?: 'critical' | 'high' | 'medium' | 'low';
  summary?: string;
  timeText?: string;
  onEdit?: () => void;
  eventId: string;
}

const importanceBorderColor = (importance?: string): string => {
  if (importance === 'critical') return '#ef4444';
  if (importance === 'high') return '#f59e0b';
  if (importance === 'medium') return '#3b82f6';
  return '#6b7280';
};

const importanceDotCount = (importance?: string): number => {
  if (importance === 'critical') return 5;
  if (importance === 'high') return 4;
  if (importance === 'medium') return 3;
  if (importance === 'low') return 2;
  return 1;
};

export function TimelineEventNode({ data, selected, id }: NodeProps) {
  const d = data as EventNodeData;
  const borderColor = importanceBorderColor(d.importance);
  const dotCount = importanceDotCount(d.importance);

  return (
    <div
      data-testid={`timeline-event-node-${id}`}
      onDoubleClick={() => d.onEdit?.()}
      className="relative min-w-[160px] max-w-[220px] rounded-2xl border-2 bg-bg-elev-1 p-3 shadow-sm cursor-pointer select-none"
      style={{
        borderColor: selected ? '#f59e0b' : borderColor,
        boxShadow: selected ? `0 0 0 2px #f59e0b55` : undefined,
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3 mb-1 truncate">
        {d.timeText || ''}
      </div>
      <div className="text-sm font-black text-text leading-tight truncate">{d.label}</div>
      {d.summary && (
        <div className="mt-1 text-xs text-text-2 line-clamp-2 leading-relaxed">{d.summary}</div>
      )}
      <div className="mt-2 flex gap-0.5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: i < dotCount ? borderColor : 'rgba(255,255,255,0.1)' }}
          />
        ))}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
