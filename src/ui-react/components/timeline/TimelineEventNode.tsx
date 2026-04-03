import React, { useCallback } from 'react';
import type { TimelineEvent } from '../../models/project';
import type { Point } from './bezierMath';
import { EventTooltip } from './EventTooltip';

interface TimelineEventNodeProps {
  event: TimelineEvent;
  position: Point;
  isHovered: boolean;
  dragMode: 'move' | 'drop' | null;
  onPointerDown: (eventId: string, e: React.PointerEvent<SVGCircleElement>) => void;
  onPointerUp: (eventId: string) => void;
  onPointerMove: (eventId: string, e: React.PointerEvent<SVGCircleElement>) => void;
  onContextMenu: (eventId: string, e: React.MouseEvent<SVGCircleElement>) => void;
  onHover: (eventId: string | null) => void;
}

const importanceRadius = (importance?: string): number => {
  if (importance === 'critical') return 13;
  if (importance === 'high') return 10;
  if (importance === 'medium') return 8;
  return 6;
};

const importanceColor = (importance?: string): string => {
  if (importance === 'critical') return '#ef4444';
  if (importance === 'high') return '#f59e0b';
  if (importance === 'medium') return '#3b82f6';
  return '#6b7280';
};

export function TimelineEventNode({
  event,
  position,
  isHovered,
  dragMode,
  onPointerDown,
  onPointerUp,
  onPointerMove,
  onContextMenu,
  onHover,
}: TimelineEventNodeProps) {
  const baseR = importanceRadius(event.importance);
  const color = importanceColor(event.importance);
  const isDragging = dragMode !== null;
  const isDropDragging = dragMode === 'drop';

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<SVGCircleElement>) => {
      e.stopPropagation();
      onPointerDown(event.id, e);
    },
    [event.id, onPointerDown]
  );

  const handlePointerUp = useCallback(() => onPointerUp(event.id), [event.id, onPointerUp]);

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<SVGCircleElement>) => onPointerMove(event.id, e),
    [event.id, onPointerMove]
  );

  const handleContextMenu = useCallback(
    (e: React.MouseEvent<SVGCircleElement>) => {
      e.preventDefault();
      e.stopPropagation();
      onContextMenu(event.id, e);
    },
    [event.id, onContextMenu]
  );

  const handlePointerEnter = useCallback(() => onHover(event.id), [event.id, onHover]);
  const handlePointerLeave = useCallback(() => onHover(null), [onHover]);

  return (
    <g
      transform={`translate(${position.x},${position.y})`}
      opacity={isDragging ? 0.7 : 1}
      data-testid={`timeline-event-node-${event.id}`}
      data-position-x={position.x}
      data-position-y={position.y}
    >
      {/* Hover ring — expands on hover */}
      <circle
        r={isHovered ? baseR + 8 : baseR + 2}
        fill="none"
        stroke={color}
        strokeWidth={2}
        opacity={isHovered ? 0.3 : 0.1}
        style={{ transition: 'r 0.15s ease, opacity 0.15s ease' }}
      />

      {/* Base circle */}
      <circle
        r={baseR}
        fill="var(--bg-elev-1, #1e1e2e)"
        stroke={color}
        strokeWidth={2.5}
      />

      {/* Importance fill dot */}
      <circle r={baseR * 0.5} fill={color} opacity={0.8} />

      {isDropDragging && (
        <circle
          r={baseR + 11}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeDasharray="3 3"
          opacity={0.55}
          data-testid={`timeline-event-drop-indicator-${event.id}`}
        />
      )}

      {/* Pointer event target */}
      <circle
        r={baseR + 6}
        fill="transparent"
        stroke="none"
        pointerEvents="all"
        style={{ cursor: isDropDragging ? 'grabbing' : 'pointer' }}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerMove={handlePointerMove}
        onContextMenu={handleContextMenu}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        data-testid={`timeline-event-hitarea-${event.id}`}
      />

      {/* Tooltip on hover (not during drag) */}
      <EventTooltip event={event} visible={isHovered && !isDragging} />

      {/* Title label below node */}
      <text
        y={baseR + 16}
        textAnchor="middle"
        fill="currentColor"
        fontSize={10}
        fontWeight={600}
        opacity={0.8}
        pointerEvents="none"
        style={{ userSelect: 'none' }}
      >
        {event.title.length > 18 ? event.title.slice(0, 18) + '…' : event.title}
      </text>
    </g>
  );
}
