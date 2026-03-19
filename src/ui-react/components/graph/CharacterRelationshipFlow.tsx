import React, { useCallback, useMemo } from 'react';
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
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useProjectStore, useUIStore } from '../../store';
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
      <Handle type="target" position={Position.Top} className="!border-border !bg-brand" />
      <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full text-white font-black text-lg" style={{ background: color }}>
        {initial}
      </div>
      <div className="text-center text-sm font-black text-text leading-tight">{data.label}</div>
      <div className="mt-1 rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-white" style={{ background: color }}>
        {data.importance}
      </div>
      <Handle type="source" position={Position.Bottom} className="!border-border !bg-brand" />
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

export const CharacterRelationshipFlow: React.FC = () => {
  const { characters, relationships, setSelectedEntity } = useProjectStore();
  const { openContextMenu } = useUIStore();

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

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedEntity('character', node.id);
  }, [setSelectedEntity]);

  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        { id: 'view', label: 'View Profile', action: () => setSelectedEntity('character', node.id) },
      ],
    });
  }, [openContextMenu, setSelectedEntity]);

  if (characters.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-text-3">
        <div className="text-center">
          <div className="text-lg font-black">No characters yet</div>
          <div className="mt-2 text-sm">Create characters to see the relationship graph.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full" data-testid="character-relationship-flow">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
};
