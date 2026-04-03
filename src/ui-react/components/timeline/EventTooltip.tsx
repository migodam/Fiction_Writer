import React from 'react';
import type { TimelineEvent } from '../../models/project';

interface EventTooltipProps {
  event: TimelineEvent;
  visible: boolean;
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

export function EventTooltip({ event, visible }: EventTooltipProps) {
  if (!visible) return null;
  const borderColor = importanceBorderColor(event.importance);
  const dotCount = importanceDotCount(event.importance);

  return (
    <foreignObject
      width={200}
      height={120}
      style={{ pointerEvents: 'none', overflow: 'visible' }}
      data-testid={`timeline-event-tooltip-${event.id}`}
    >
      <div
        className="rounded-xl border border-border bg-bg-elev-1 p-3 shadow-lg"
        style={{ width: 200, boxSizing: 'border-box' }}
      >
        <div className="text-[10px] font-black uppercase tracking-[0.18em] text-text-3 mb-1 truncate">
          {event.time || ''}
        </div>
        <div className="text-sm font-black text-text leading-tight truncate">
          {event.title}
        </div>
        {event.summary && (
          <div className="mt-1 text-xs text-text-2 line-clamp-2 leading-relaxed">
            {event.summary}
          </div>
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
      </div>
    </foreignObject>
  );
}
