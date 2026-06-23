import React, { useCallback, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  NodeTypes,
  EdgeTypes,
  EdgeProps,
  BaseEdge,
  EdgeLabelRenderer,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  MarkerType,
  Connection,
  getBezierPath,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import { cn } from '../../utils';
import type { Character, Relationship } from '../../models/project';

type CharacterNodeData = {
  character: Character;
  label: string;
  importance: string;
  layoutRole: 'center' | 'ring';
};

type RelationshipEdgeData = {
  label: string;
  color: string;
  labelOffset: number;
};

const importanceRank: Record<string, number> = {
  core: 0,
  major: 1,
  supporting: 2,
  minor: 3,
  ungrouped: 4,
};

// Custom character node
const CharacterNode: React.FC<{ id: string; data: CharacterNodeData }> = ({ id, data }) => {
  const { t } = useI18n();
  const importanceColors: Record<string, string> = {
    core: '#ef4444',
    major: '#f59e0b',
    supporting: '#22c55e',
    minor: '#94a3b8',
    ungrouped: '#64748b',
  };
  const color = importanceColors[data.importance] || importanceColors.ungrouped;
  const initial = data.label?.[0]?.toUpperCase() || '?';
  return (
    <div
      className="relative flex flex-col items-center rounded-2xl border-2 border-border bg-card px-4 py-3 shadow-md transition-shadow hover:shadow-lg"
      style={{ minWidth: 120 }}
      data-testid={`relationship-character-node-${id}`}
      data-layout-role={data.layoutRole}
    >
      <Handle type="target" position={Position.Left} className="!border-border !bg-brand" />
      <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full text-white font-black text-lg" style={{ background: color }}>
        {initial}
      </div>
      <div className="text-center text-sm font-black text-text leading-tight">{data.label}</div>
      <div className="mt-1 rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-white" style={{ background: color }}>
        {t('characters.importance.' + data.importance, data.importance)}
      </div>
      <Handle type="source" position={Position.Right} className="!border-border !bg-brand" />
    </div>
  );
};

const nodeTypes: NodeTypes = { character: CharacterNode };

const RelationshipEdge: React.FC<EdgeProps<Edge<RelationshipEdgeData>>> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  markerStart,
  data,
}) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const labelOffset = data?.labelOffset ?? 0;
  const label = data?.label || '';

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} markerStart={markerStart} />
      {label && (
        <EdgeLabelRenderer>
          <button
            type="button"
            data-testid={`relationship-edge-label-${id}`}
            className="nodrag nopan absolute rounded-full border border-border bg-bg-elev-1/95 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-text shadow-sm backdrop-blur"
            style={{
              color: data?.color,
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY + labelOffset}px)`,
              pointerEvents: 'all',
            }}
            title={label}
          >
            {label}
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

const edgeTypes: EdgeTypes = { relationship: RelationshipEdge };

// Relationship status → edge color
const statusColor: Record<string, string> = {
  active: '#22c55e',
  strained: '#f59e0b',
  broken: '#ef4444',
  unknown: '#94a3b8',
};

function relationshipDegrees(relationships: Relationship[]) {
  return relationships.reduce<Record<string, number>>((acc, rel) => {
    acc[rel.sourceId] = (acc[rel.sourceId] || 0) + 1;
    acc[rel.targetId] = (acc[rel.targetId] || 0) + 1;
    return acc;
  }, {});
}

function sortByGraphPriority(characters: Character[], relationships: Relationship[]) {
  const degree = relationshipDegrees(relationships);
  return [...characters].sort((a, b) => {
    const degreeDelta = (degree[b.id] || 0) - (degree[a.id] || 0);
    if (degreeDelta !== 0) return degreeDelta;
    const importanceDelta = (importanceRank[a.importance || 'ungrouped'] ?? 99) - (importanceRank[b.importance || 'ungrouped'] ?? 99);
    if (importanceDelta !== 0) return importanceDelta;
    return (a.name || a.id).localeCompare(b.name || b.id, 'zh-Hans-CN');
  });
}

// Characters → React Flow nodes, deterministic radial layout by relationship degree.
function buildRadialNodes(characters: Character[], relationships: Relationship[]): Node<CharacterNodeData>[] {
  if (characters.length === 0) return [];

  const sorted = sortByGraphPriority(characters, relationships);
  const hasRelationships = relationships.length > 0;
  const center = hasRelationships ? sorted[0] : null;
  const ringCharacters = center ? sorted.slice(1) : sorted;
  const ringCount = ringCharacters.length;
  const radiusX = ringCount <= 6 ? 340 : 420;
  const radiusY = ringCount <= 6 ? 230 : 280;
  const centerNode: Node<CharacterNodeData>[] = center
    ? [{
        id: center.id,
        type: 'character',
        position: { x: 0, y: 0 },
        data: { character: center, label: center.name, importance: center.importance || 'ungrouped', layoutRole: 'center' },
      }]
    : [];

  const ringNodes: Node<CharacterNodeData>[] = ringCharacters.map((char, index) => {
    const ring = Math.floor(index / 12);
    const indexInRing = index % 12;
    const countInRing = Math.min(12, ringCount - ring * 12);
    const angle = -Math.PI / 2 + (2 * Math.PI * indexInRing) / Math.max(1, countInRing);
    const currentRadiusX = radiusX + ring * 190;
    const currentRadiusY = radiusY + ring * 150;
    return {
      id: char.id,
      type: 'character',
      position: {
        x: Math.round(Math.cos(angle) * currentRadiusX),
        y: Math.round(Math.sin(angle) * currentRadiusY),
      },
      data: { character: char, label: char.name, importance: char.importance || 'ungrouped', layoutRole: 'ring' },
    };
  });

  return [...centerNode, ...ringNodes];
}

// Relationships → React Flow edges
function buildEdges(relationships: Relationship[]): Edge<RelationshipEdgeData>[] {
  const pairTotals = relationships.reduce<Record<string, number>>((acc, rel) => {
    const pairKey = [rel.sourceId, rel.targetId].sort().join('__');
    acc[pairKey] = (acc[pairKey] || 0) + 1;
    return acc;
  }, {});
  const pairSeen: Record<string, number> = {};

  return relationships.map((rel, index) => {
    const pairKey = [rel.sourceId, rel.targetId].sort().join('__');
    const pairIndex = pairSeen[pairKey] || 0;
    pairSeen[pairKey] = pairIndex + 1;
    const color = statusColor[rel.status || 'unknown'];
    const pairOffset = (pairIndex - (pairTotals[pairKey] - 1) / 2) * 34;
    const alternatingOffset = pairTotals[pairKey] > 1 ? 0 : ((index % 3) - 1) * 18;
    return {
    id: rel.id,
    type: 'relationship',
    source: rel.sourceId,
    target: rel.targetId,
    label: rel.type || '',
    data: { label: rel.type || '', color, labelOffset: pairOffset + alternatingOffset },
    style: { stroke: color, strokeWidth: Math.max(1, (rel.strength || 5) / 3) },
    markerEnd: rel.directionality !== 'bidirectional' ? { type: MarkerType.ArrowClosed, color } : undefined,
    markerStart: rel.directionality === 'bidirectional' ? { type: MarkerType.ArrowClosed } : undefined,
    animated: rel.status === 'active',
  };
  });
}

export type GraphLayoutMode = 'radial' | 'cluster' | 'force-lite';

const TIER_ORDER = ['core', 'major', 'supporting', 'minor', 'ungrouped'] as const;

function buildClusterNodes(chars: Character[], rels: Relationship[]): Node<CharacterNodeData>[] {
  const degree = relationshipDegrees(rels);
  const groups = new Map<string, Character[]>(TIER_ORDER.map((t) => [t, []]));
  for (const c of chars) {
    const tier = (c.importance ?? 'ungrouped') as typeof TIER_ORDER[number];
    (groups.get(tier) ?? groups.get('ungrouped')!).push(c);
  }
  const nodes: Node<CharacterNodeData>[] = [];
  let col = 0;
  for (const tier of TIER_ORDER) {
    const group = (groups.get(tier) ?? []).sort((a, b) => (degree[b.id] ?? 0) - (degree[a.id] ?? 0));
    if (group.length === 0) continue;
    group.forEach((char, row) =>
      nodes.push({
        id: char.id,
        type: 'character',
        position: { x: col * 220, y: row * 120 },
        data: { character: char, label: char.name, importance: char.importance ?? 'ungrouped', layoutRole: 'ring' as const },
      }),
    );
    col++;
  }
  return nodes;
}

function buildForceLiteNodes(
  chars: Character[],
  rels: Relationship[],
  iterations = 50,
): Node<CharacterNodeData>[] {
  const sorted = [...chars].sort((a, b) => a.id.localeCompare(b.id));
  const n = sorted.length;
  const R = 300;
  const positions = sorted.map((_, i) => ({
    x: Math.round(Math.cos((2 * Math.PI * i) / Math.max(n, 1)) * R),
    y: Math.round(Math.sin((2 * Math.PI * i) / Math.max(n, 1)) * R),
  }));
  const idToIdx = new Map(sorted.map((c, i) => [c.id, i]));
  const k = 120;
  for (let iter = 0; iter < iterations; iter++) {
    const forces = positions.map(() => ({ x: 0, y: 0 }));
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = positions[i].x - positions[j].x || 0.01;
        const dy = positions[i].y - positions[j].y || 0.01;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const fr = (k * k) / d;
        forces[i].x += (dx / d) * fr; forces[i].y += (dy / d) * fr;
        forces[j].x -= (dx / d) * fr; forces[j].y -= (dy / d) * fr;
      }
    }
    for (const rel of rels) {
      const i = idToIdx.get(rel.sourceId);
      const j = idToIdx.get(rel.targetId);
      if (i === undefined || j === undefined) continue;
      const dx = positions[j].x - positions[i].x;
      const dy = positions[j].y - positions[i].y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const fa = (d * d) / k;
      forces[i].x += (dx / d) * fa; forces[i].y += (dy / d) * fa;
      forces[j].x -= (dx / d) * fa; forces[j].y -= (dy / d) * fa;
    }
    const t = Math.max(10, 100 - iter * 2);
    for (let i = 0; i < n; i++) {
      const fl = Math.sqrt(forces[i].x ** 2 + forces[i].y ** 2) || 1;
      positions[i].x = Math.round(positions[i].x + (forces[i].x / fl) * Math.min(fl, t));
      positions[i].y = Math.round(positions[i].y + (forces[i].y / fl) * Math.min(fl, t));
    }
  }
  return sorted.map((char, i) => ({
    id: char.id,
    type: 'character',
    position: positions[i],
    data: { character: char, label: char.name, importance: char.importance ?? 'ungrouped', layoutRole: 'ring' as const },
  }));
}

function resolveNodeLabelCollisions(
  nodes: Node<CharacterNodeData>[],
  nodeW = 140,
  nodeH = 80,
): Node<CharacterNodeData>[] {
  const sorted = [...nodes].sort(
    (a, b) => (importanceRank[a.data.importance] ?? 99) - (importanceRank[b.data.importance] ?? 99),
  );
  const placed: Array<{ x: number; y: number }> = [];
  return sorted.map((node) => {
    const { x } = node.position;
    let y = node.position.y;
    while (placed.some((p) => Math.abs(p.x - x) < nodeW && Math.abs(p.y - y) < nodeH)) {
      y += 16;
    }
    placed.push({ x, y });
    return { ...node, position: { x, y } };
  });
}

// Edge edit panel
const EdgeEditPanel: React.FC<{
  relationship: Relationship;
  characters: Character[];
  t: (key: string, fallback?: string) => string;
  onSave: (rel: Relationship) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}> = ({ relationship, characters, t, onSave, onDelete, onClose }) => {
  const [form, setForm] = useState<Relationship>({ ...relationship });

  const sourceChar = characters.find((c) => c.id === form.sourceId);
  const targetChar = characters.find((c) => c.id === form.targetId);

  return (
    <div className="absolute right-4 top-4 z-50 w-72 rounded-lg border border-border bg-bg-elev-1 p-4 shadow-xl" data-testid="edge-edit-panel">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-black text-text">{t('characters.editRelationship', 'Edit Relationship')}</span>
        <button
          onClick={onClose}
          className="text-text-3 hover:text-text transition-colors text-xs"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-text-3">
        {sourceChar?.name || form.sourceId} → {targetChar?.name || form.targetId}
      </div>

      {/* Type */}
      <label className="mt-3 block">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-text-3">
          {t('characters.relationshipType', 'Type')}
        </span>
        <input
          type="text"
          value={form.type}
          onChange={(e) => setForm({ ...form, type: e.target.value })}
          className="w-full rounded border border-border bg-bg px-2 py-1 text-sm text-text focus:outline-none focus:ring-1 focus:ring-brand"
        />
      </label>

      {/* Description */}
      <label className="mt-3 block">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-text-3">
          {t('characters.relationshipDescription', 'Description')}
        </span>
        <textarea
          value={form.description || ''}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          rows={2}
          className="w-full rounded border border-border bg-bg px-2 py-1 text-sm text-text focus:outline-none focus:ring-1 focus:ring-brand resize-none"
        />
      </label>

      {/* Strength slider */}
      <label className="mt-3 block">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-text-3">
          {t('characters.relationshipStrength', 'Strength')}: {form.strength ?? 5}
        </span>
        <input
          type="range"
          min={1}
          max={10}
          value={form.strength ?? 5}
          onChange={(e) => setForm({ ...form, strength: Number(e.target.value) })}
          className="w-full accent-brand"
        />
      </label>

      {/* Status dropdown */}
      <label className="mt-3 block">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-text-3">
          {t('characters.relationshipStatus', 'Status')}
        </span>
        <select
          value={form.status || 'active'}
          onChange={(e) => setForm({ ...form, status: e.target.value as Relationship['status'] })}
          className="w-full rounded border border-border bg-bg px-2 py-1 text-sm text-text focus:outline-none focus:ring-1 focus:ring-brand"
        >
          <option value="active">Active</option>
          <option value="strained">Strained</option>
          <option value="broken">Broken</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>

      {/* Directionality toggle */}
      <label className="mt-3 block">
        <span className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-text-3">
          {t('characters.relationshipDirectionality', 'Directionality')}
        </span>
        <div className="mt-1 flex gap-2">
          <button
            type="button"
            onClick={() => setForm({ ...form, directionality: 'bidirectional' })}
            className={`flex-1 rounded border px-2 py-1 text-xs font-bold transition-colors ${
              form.directionality === 'bidirectional'
                ? 'border-brand bg-brand/20 text-text'
                : 'border-border bg-bg text-text-3 hover:text-text'
            }`}
          >
            ↔ Bidirectional
          </button>
          <button
            type="button"
            onClick={() => setForm({ ...form, directionality: 'source_to_target' })}
            className={`flex-1 rounded border px-2 py-1 text-xs font-bold transition-colors ${
              form.directionality !== 'bidirectional'
                ? 'border-brand bg-brand/20 text-text'
                : 'border-border bg-bg text-text-3 hover:text-text'
            }`}
          >
            → One-way
          </button>
        </div>
      </label>

      {/* Actions */}
      <div className="mt-4 flex gap-2">
        <button
          onClick={() => { onSave(form); onClose(); }}
          className="flex-1 rounded bg-brand px-3 py-1.5 text-xs font-black text-white hover:bg-brand/80 transition-colors"
          data-testid="save-relationship-btn"
        >
          {t('characters.saveRelationship', 'Save')}
        </button>
        <button
          onClick={() => { onDelete(form.id); onClose(); }}
          className="flex-1 rounded border border-red-500/50 bg-bg px-3 py-1.5 text-xs font-black text-red-400 hover:bg-red-500/10 transition-colors"
          data-testid="delete-relationship-btn"
        >
          {t('characters.deleteRelationship', 'Delete')}
        </button>
      </div>
    </div>
  );
};

export const CharacterRelationshipFlow: React.FC = () => {
  const { characters, relationships, graphImportanceFilter, setSelectedEntity, addRelationship, updateRelationship, deleteRelationship } = useProjectStore();
  const { openContextMenu } = useUIStore();
  const { t } = useI18n();
  const [editingEdgeId, setEditingEdgeId] = useState<string | null>(null);
  const [layoutMode, setLayoutMode] = useState<GraphLayoutMode>('radial');

  const visibleChars = useMemo(
    () =>
      graphImportanceFilter.length === 0
        ? characters
        : characters.filter((c) => !graphImportanceFilter.includes(c.importance || 'ungrouped')),
    [characters, graphImportanceFilter],
  );

  const visibleCharIds = useMemo(() => new Set(visibleChars.map((c) => c.id)), [visibleChars]);

  const visibleRelationships = useMemo(
    () => relationships.filter((r) => visibleCharIds.has(r.sourceId) && visibleCharIds.has(r.targetId)),
    [relationships, visibleCharIds],
  );

  const buildByMode = useCallback(
    (chars: Character[], rels: Relationship[], mode: GraphLayoutMode) => {
      const base =
        mode === 'cluster' ? buildClusterNodes(chars, rels)
        : mode === 'force-lite' ? buildForceLiteNodes(chars, rels)
        : buildRadialNodes(chars, rels);
      return resolveNodeLabelCollisions(base);
    },
    [],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(
    buildByMode(visibleChars, visibleRelationships, layoutMode),
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(buildEdges(visibleRelationships));

  // Update nodes when visible characters, relationships, or layout mode change
  React.useEffect(() => {
    setNodes(buildByMode(visibleChars, visibleRelationships, layoutMode));
  }, [visibleChars, visibleRelationships, layoutMode, setNodes, buildByMode]);

  React.useEffect(() => {
    setEdges(buildEdges(visibleRelationships));
  }, [visibleRelationships, setEdges]);

  const editingRelationship = editingEdgeId
    ? relationships.find((r) => r.id === editingEdgeId) ?? null
    : null;

  const handleConnect = useCallback((params: Connection) => {
    if (!params.source || !params.target) return;
    addRelationship({
      id: `rel_${Date.now()}`,
      sourceId: params.source,
      targetId: params.target,
      type: '',
      description: '',
      category: 'general',
      directionality: 'bidirectional',
      status: 'active',
      strength: 5,
      sourceNotes: '',
    });
  }, [addRelationship]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedEntity('character', node.id);
  }, [setSelectedEntity]);

  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { id: 'view', label: t('characters.viewProfile', 'View Profile'), action: () => setSelectedEntity('character', node.id) },
      ],
    });
  }, [openContextMenu, setSelectedEntity, t]);

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setEditingEdgeId(edge.id);
  }, []);

  if (characters.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-text-3">
        <div className="text-center">
          <div className="text-lg font-black">{t('characters.noCharacters', 'No Characters')}</div>
          <div className="mt-2 text-sm">{t('characters.noGraphBody', 'Create characters to see the relationship graph.')}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full" data-testid="character-relationship-flow">
      <div className="absolute top-3 left-3 z-10 flex gap-1 rounded-xl border border-border bg-bg-elev-1 p-1 shadow">
        {(['radial', 'cluster', 'force-lite'] as GraphLayoutMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            data-testid={`graph-layout-mode-${mode}`}
            onClick={() => setLayoutMode(mode)}
            className={cn(
              'rounded-lg px-3 py-1 text-[10px] font-black uppercase tracking-widest transition-colors',
              layoutMode === mode ? 'bg-brand text-white' : 'text-text-3 hover:text-text',
            )}
          >
            {mode === 'radial' ? '辐射' : mode === 'cluster' ? '聚类' : '力导向'}
          </button>
        ))}
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        onEdgeClick={onEdgeClick}
        onConnect={handleConnect}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
      {editingRelationship && (
        <EdgeEditPanel
          relationship={editingRelationship}
          characters={characters}
          t={t}
          onSave={updateRelationship}
          onDelete={deleteRelationship}
          onClose={() => setEditingEdgeId(null)}
        />
      )}
    </div>
  );
};
