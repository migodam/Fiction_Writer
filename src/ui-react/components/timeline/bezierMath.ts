/**
 * Pure math utilities for SVG Bézier timeline.
 * No React dependencies — safe to unit-test in isolation.
 */

export interface Point {
  x: number;
  y: number;
}

// ── Cubic Bézier primitives ──────────────────────────────────

export function cubicBezierPoint(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const u = 1 - t;
  const u2 = u * u;
  const u3 = u2 * u;
  const t2 = t * t;
  const t3 = t2 * t;
  return {
    x: u3 * p0.x + 3 * u2 * t * p1.x + 3 * u * t2 * p2.x + t3 * p3.x,
    y: u3 * p0.y + 3 * u2 * t * p1.y + 3 * u * t2 * p2.y + t3 * p3.y,
  };
}

export function cubicBezierTangent(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
  const u = 1 - t;
  return {
    x: 3 * u * u * (p1.x - p0.x) + 6 * u * t * (p2.x - p1.x) + 3 * t * t * (p3.x - p2.x),
    y: 3 * u * u * (p1.y - p0.y) + 6 * u * t * (p2.y - p1.y) + 3 * t * t * (p3.y - p2.y),
  };
}

// ── Branch → control points ──────────────────────────────────

export interface ControlPoints {
  p0: Point;
  p1: Point;
  p2: Point;
  p3: Point;
}

export function buildBranchControlPoints(
  anchorStartPos: Point | undefined,
  anchorEndPos: Point | undefined,
  laneOffset: number,
  bend: number,
  canvasWidth: number,
): ControlPoints {
  const p0 = anchorStartPos ?? { x: 80, y: laneOffset };
  const p3 = anchorEndPos ?? { x: canvasWidth - 80, y: laneOffset };
  const dx = (p3.x - p0.x) * Math.max(bend, 0.15);
  const controlY = Number.isFinite(laneOffset) ? laneOffset : (p0.y + p3.y) / 2;
  const p1: Point = { x: p0.x + dx, y: controlY };
  const p2: Point = { x: p3.x - dx, y: controlY };
  return { p0, p1, p2, p3 };
}

export function buildSVGPath(cp: ControlPoints): string {
  return `M ${cp.p0.x} ${cp.p0.y} C ${cp.p1.x} ${cp.p1.y} ${cp.p2.x} ${cp.p2.y} ${cp.p3.x} ${cp.p3.y}`;
}

export function fanLaneOffset(index: number, spacing: number): number {
  const step = Math.floor(index / 2) + 1;
  const sign = index % 2 === 0 ? -1 : 1;
  return sign * step * spacing;
}

export function offsetControlPoints(cp: ControlPoints, offset: number): ControlPoints {
  const tangent = cubicBezierTangent(cp.p0, cp.p1, cp.p2, cp.p3, 0.5);
  const length = Math.hypot(tangent.x, tangent.y) || 1;
  const normal = {
    x: -tangent.y / length,
    y: tangent.x / length,
  };

  return {
    p0: cp.p0,
    p1: {
      x: cp.p1.x + normal.x * offset,
      y: cp.p1.y + normal.y * offset,
    },
    p2: {
      x: cp.p2.x + normal.x * offset,
      y: cp.p2.y + normal.y * offset,
    },
    p3: cp.p3,
  };
}

// ── Nearest-point queries ────────────────────────────────────

export function nearestTOnCurve(
  cp: ControlPoints,
  point: Point,
  coarseSteps = 80,
): { t: number; dist: number; pt: Point } {
  let bestT = 0;
  let bestDist = Infinity;
  let bestPt = cp.p0;

  // Coarse sweep
  for (let i = 0; i <= coarseSteps; i++) {
    const t = i / coarseSteps;
    const pt = cubicBezierPoint(cp.p0, cp.p1, cp.p2, cp.p3, t);
    const dist = Math.hypot(pt.x - point.x, pt.y - point.y);
    if (dist < bestDist) {
      bestDist = dist;
      bestT = t;
      bestPt = pt;
    }
  }

  // Bisection refinement (6 iterations ≈ 1/5000 precision)
  let lo = Math.max(0, bestT - 1 / coarseSteps);
  let hi = Math.min(1, bestT + 1 / coarseSteps);
  for (let iter = 0; iter < 6; iter++) {
    const mid = (lo + hi) / 2;
    const ptL = cubicBezierPoint(cp.p0, cp.p1, cp.p2, cp.p3, lo);
    const ptM = cubicBezierPoint(cp.p0, cp.p1, cp.p2, cp.p3, mid);
    const ptH = cubicBezierPoint(cp.p0, cp.p1, cp.p2, cp.p3, hi);
    const dL = Math.hypot(ptL.x - point.x, ptL.y - point.y);
    const dM = Math.hypot(ptM.x - point.x, ptM.y - point.y);
    const dH = Math.hypot(ptH.x - point.x, ptH.y - point.y);
    if (dM <= dL && dM <= dH) {
      bestDist = dM;
      bestT = mid;
      bestPt = ptM;
      lo = (lo + mid) / 2;
      hi = (mid + hi) / 2;
    } else if (dL < dH) {
      hi = mid;
    } else {
      lo = mid;
    }
  }

  return { t: bestT, dist: bestDist, pt: bestPt };
}

// ── Coordinate transforms ────────────────────────────────────

export function screenToCanvas(
  screenPt: Point,
  svgEl: SVGSVGElement | null,
  view?: { panX?: number; panY?: number; zoom?: number },
): Point {
  if (!svgEl) return screenPt;
  const ctm = svgEl.getScreenCTM();
  if (!ctm) return screenPt;
  const pt = new DOMPoint(screenPt.x, screenPt.y).matrixTransform(ctm.inverse());
  return { x: pt.x, y: pt.y };
}

export function applyViewTransform(pt: Point, panX: number, panY: number, zoom: number): Point {
  return {
    x: pt.x * zoom + panX,
    y: pt.y * zoom + panY,
  };
}

export function inverseViewTransform(pt: Point, panX: number, panY: number, zoom: number): Point {
  return {
    x: (pt.x - panX) / zoom,
    y: (pt.y - panY) / zoom,
  };
}

// ── Event t-parameter from orderIndex ─────────────────────────

export function tFromOrderIndex(totalOnBranch: number, index: number): number {
  if (totalOnBranch <= 1) return 0.5;
  const pad = 0.08;
  return pad + (index / (totalOnBranch - 1)) * (1 - 2 * pad);
}
