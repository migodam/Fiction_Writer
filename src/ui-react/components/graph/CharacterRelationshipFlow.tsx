import React, { useCallback, useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  NodeTypes,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  MarkerType,
  Connection,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import type { Character, Relationship } from '../../models/project';

// Custom character node
const CharacterNode: React.FC<{ data: { character: Character; label: string; importance: string } }> = ({ data }) => {
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
    <div className="relative flex flex-col items-center rounded-2xl border-2 border-border bg-card px-4 py-3 shadow-md transition-shadow hover:shadow-lg" style={{ minWidth: 120 }}>
      <Handle type="target" position={Position.Left} className="!border-border !bg-brand" />
      <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full text-white font-black text-lg" style={{ background: color }}>
        {initial}
      </div>
      <div className="text-center text-sm font-black text-text leading-tight">{data.label}</div>
      <div className="mt-1 rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-white" style={{ background: color }}>
        {data.importance}
      </div>
      <Handle type="source" position={Position.Right} className="!border-border !bg-brand" />
    </div>
  );
};

const nodeTypes: NodeTypes = { character: CharacterNode };

// Relationship status → edge color
const statusColor: Record<string, string> = {
  active: '#22c55e',
  strained: '#f59e0b',
  broken: '#ef4444',
  unknown: '#94a3b8',
};

// Characters → React Flow nodes, auto-layout in grid
function buildNodes(characters: Character[]): Node[] {
  return characters.map((char, index) => ({
    id: char.id,
    type: 'character',
    position: { x: (index % 5) * 200, y: Math.floor(index / 5) * 180 },
    data: { character: char, label: char.name, importance: char.importance || 'ungrouped' },
  }));
}

// Relationships → React Flow edges
function buildEdges(relationships: Relationship[]): Edge[] {
  return relationships.map((rel) => ({
    id: rel.id,
    source: rel.sourceId,
    target: rel.targetId,
    label: rel.type || '',
    style: { stroke: statusColor[rel.status || 'unknown'], strokeWidth: Math.max(1, (rel.strength || 5) / 3) },
    markerEnd: rel.directionality !== 'bidirectional' ? { type: MarkerType.ArrowClosed, color: statusColor[rel.status || 'unknown'] } : undefined,
    markerStart: rel.directionality === 'bidirectional' ? { type: MarkerType.ArrowClosed } : undefined,
    animated: rel.status === 'active',
  }));
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
  const { characters, relationships, setSelectedEntity, addRelationship, updateRelationship, deleteRelationship } = useProjectStore();
  const { openContextMenu } = useUIStore();
  const { t } = useI18n();
  const [editingEdgeId, setEditingEdgeId] = useState<string | null>(null);

  const initialNodes = useMemo(() => buildNodes(characters), [characters]);
  const initialEdges = useMemo(() => buildEdges(relationships), [relationships]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes when characters change
  React.useEffect(() => {
    setNodes(buildNodes(characters));
  }, [characters, setNodes]);

  React.useEffect(() => {
    setEdges(buildEdges(relationships));
  }, [relationships, setEdges]);

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
