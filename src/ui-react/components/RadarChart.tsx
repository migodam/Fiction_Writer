import React from 'react';
import type { CharacterPovScore } from '../models/project';

export const RadarChart = ({
  metrics,
  size = 260,
}: {
  metrics: CharacterPovScore[];
  size?: number;
}) => {
  const center = size / 2;
  const radius = size * 0.34;
  const total = Math.max(metrics.length, 3);
  const levels = [0.25, 0.5, 0.75, 1];

  const pointFor = (index: number, scale: number) => {
    const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
    return {
      x: center + Math.cos(angle) * radius * scale,
      y: center + Math.sin(angle) * radius * scale,
    };
  };

  const polygon = metrics
    .map((metric, index) => {
      const point = pointFor(index, Math.max(0, Math.min(metric.score, 100)) / 100);
      return `${point.x},${point.y}`;
    })
    .join(' ');

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full">
      {levels.map((level) => (
        <polygon
          key={level}
          points={Array.from({ length: total })
            .map((_, index) => {
              const point = pointFor(index, level);
              return `${point.x},${point.y}`;
            })
            .join(' ')}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth="1"
        />
      ))}
      {Array.from({ length: total }).map((_, index) => {
        const point = pointFor(index, 1);
        return (
          <line
            key={index}
            x1={center}
            y1={center}
            x2={point.x}
            y2={point.y}
            stroke="rgba(255,255,255,0.1)"
            strokeWidth="1"
          />
        );
      })}
      <polygon points={polygon} fill="rgba(245, 158, 11, 0.22)" stroke="rgba(245, 158, 11, 0.9)" strokeWidth="2" />
      {metrics.map((metric, index) => {
        const point = pointFor(index, Math.max(0, Math.min(metric.score, 100)) / 100);
        const labelPoint = pointFor(index, 1.14);
        return (
          <g key={metric.key}>
            <circle cx={point.x} cy={point.y} r="4" fill="#f59e0b" />
            <text x={labelPoint.x} y={labelPoint.y} fill="currentColor" fontSize="11" textAnchor="middle">
              {metric.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
