import React from 'react';
import { EdgeProps, getBezierPath, EdgeLabelRenderer } from '@xyflow/react';

export function BranchEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <path
        id={id}
        d={edgePath}
        className={`fill-none ${selected ? 'stroke-brand' : 'stroke-text-3'}`}
        strokeWidth={selected ? 3 : 2}
        opacity={0.8}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              position: 'absolute',
            }}
            className="bg-bg-elev-2 border border-border px-1.5 py-0.5 rounded text-xs text-text-2 pointer-events-none"
            data-testid={`timeline-branch-label-${id}`}
          >
            {data.label as string}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
