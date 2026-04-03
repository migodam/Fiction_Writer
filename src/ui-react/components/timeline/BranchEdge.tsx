import React, { useCallback } from 'react';
import type { TimelineBranch } from '../../models/project';
import { buildSVGPath, nearestTOnCurve } from './bezierMath';
import type { Point } from './bezierMath';

interface BranchEdgeProps {
  branch: TimelineBranch;
  controlPoints: { p0: Point; p1: Point; p2: Point; p3: Point };
  isDrawMode: boolean;
  isSelected: boolean;
  renderMode?: 'default' | 'collapsed';
  overlapHostBranchId?: string | null;
  collapsedBranchIds?: string[];
  showStartArrow?: boolean;
  showEndArrow?: boolean;
  onPathClick: (branchId: string, t: number, svgPoint: Point) => void;
  onPathContextMenu: (branchId: string, svgPoint: Point, clientPoint: Point) => void;
  onPointerMove: (branchId: string, t: number) => void;
  onPointerLeave: () => void;
}

function computeT(
  e: React.PointerEvent<SVGPathElement>,
  controlPoints: { p0: Point; p1: Point; p2: Point; p3: Point },
  branchId: string,
  callback: (branchId: string, t: number, svgPoint: Point) => void
) {
  e.stopPropagation();
  const svg = e.currentTarget.closest('svg');
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const pt: Point = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  const result = nearestTOnCurve(controlPoints, pt, 100);
  callback(branchId, result.t, pt);
}

export function BranchEdge({
  branch,
  controlPoints,
  isDrawMode,
  isSelected,
  renderMode = 'default',
  overlapHostBranchId = null,
  collapsedBranchIds = [],
  showStartArrow = false,
  showEndArrow = true,
  onPathClick,
  onPathContextMenu,
  onPointerMove,
  onPointerLeave,
}: BranchEdgeProps) {
  const pathD = buildSVGPath(controlPoints);
  const strokeColor = branch.color || '#38bdf8';
  const thickness = (branch.geometry?.thickness ?? 1) * 2;
  const selectedStrokeWidth = thickness + 6;

  const handleHitAreaClick = useCallback(
    (e: React.PointerEvent<SVGPathElement>) =>
      computeT(e, controlPoints, branch.id, onPathClick),
    [controlPoints, branch.id, onPathClick]
  );

  const handleContextMenu = useCallback(
    (e: React.MouseEvent<SVGPathElement>) => {
      e.preventDefault();
      e.stopPropagation();
      const svg = e.currentTarget.closest('svg');
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const pt: Point = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      const result = nearestTOnCurve(controlPoints, pt, 100);
      onPathContextMenu(branch.id, result.pt, { x: e.clientX, y: e.clientY });
    },
    [branch.id, controlPoints, onPathContextMenu]
  );

  const handleHitAreaMove = useCallback(
    (e: React.PointerEvent<SVGPathElement>) =>
      computeT(e, controlPoints, branch.id, (_id, t) => onPointerMove(_id, t)),
    [controlPoints, branch.id, onPointerMove]
  );

  const midPt = {
    x: (controlPoints.p0.x + controlPoints.p3.x) / 2,
    y: (controlPoints.p0.y + controlPoints.p3.y) / 2,
  };

  return (
    <g
      data-testid={`timeline-branch-${branch.id}`}
      data-render-mode={renderMode}
      data-overlap-host-branch-id={overlapHostBranchId ?? ''}
      data-collapsed-branch-ids={collapsedBranchIds.join(',')}
    >
      {isSelected && (
        <path
          d={pathD}
          fill="none"
          stroke={strokeColor}
          strokeWidth={selectedStrokeWidth}
          opacity={0.16}
          strokeLinecap="round"
          pointerEvents="none"
          data-testid={`timeline-branch-selection-${branch.id}`}
        />
      )}
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth={thickness}
        opacity={isSelected ? 1 : renderMode === 'collapsed' ? 0.92 : 0.85}
        strokeLinecap="round"
        markerStart={showStartArrow ? 'url(#branch-arrow)' : undefined}
        markerEnd={showEndArrow ? 'url(#branch-arrow)' : undefined}
        pointerEvents="none"
        style={{ cursor: isDrawMode ? 'crosshair' : 'pointer' }}
        data-testid={`timeline-branch-path-${branch.id}`}
      />
      <path
        d={pathD}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        pointerEvents="stroke"
        onClick={handleHitAreaClick}
        onContextMenu={handleContextMenu}
        onPointerMove={handleHitAreaMove}
        onPointerLeave={onPointerLeave}
        data-testid={`timeline-branch-hitarea-${branch.id}`}
      />
      {branch.name && (
        <text
          x={midPt.x}
          y={midPt.y - 8}
          textAnchor="middle"
          alignmentBaseline="middle"
          fill={strokeColor}
          fontSize={11}
          fontWeight={700}
          opacity={0.7}
          pointerEvents="none"
          data-testid={`timeline-branch-label-${branch.id}`}
        >
          {branch.name}
        </text>
      )}
    </g>
  );
}
