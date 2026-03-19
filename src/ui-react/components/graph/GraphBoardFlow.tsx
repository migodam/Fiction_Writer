import React, { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  NodeChange,
  addEdge,
  Connection,
  NodeTypes,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useProjectStore } from '../../store';
import type { GraphBoard, GraphNode as ProjectGraphNode, GraphEdge as ProjectGraphEdge } from '../../models/project';

// Kind-based colors
const kindColors: Record<string, string> = {
  free_note: '#fef08a',
  character_ref: '#bfdbfe',
  event_ref: '#bbf7d0',
  location_ref: '#fed7aa',
  world_item_ref: '#e9d5ff',
  image_card: '#f1f5f9',
  group_frame: '#f8fafc',
};

// Custom node renderer
const GraphBoardNode: React.FC<{ data: { node: ProjectGraphNode } }> = ({ data }) => {
  const n = data.node;
  const bg = kindColors[n.kind] || '#f1f5f9';
  return (
    <div
      className="rounded-2xl border border-border p-3 shadow-sm"
      style={{ background: bg, width: n.width || 180, minHeight: n.height || 80 }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="text-[9px] font-black uppercase tracking-widest text-text-3 mb-1">{n.kind.replace('_', ' ')}</div>
      <div className="text-sm font-black text-text leading-tight">{n.label}</div>
      {n.description && <div className="mt-1 text-xs text-text-2 line-clamp-2">{n.description}</div>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

const nodeTypes: NodeTypes = { graphBoard: GraphBoardNode };

// Convert our model to React Flow format
function toRFNodes(nodes: ProjectGraphNode[]): Node[] {
  return nodes.map((n) => ({
    id: n.id,
    type: 'graphBoard',
    position: { x: n.x, y: n.y },
    data: { node: n },
    style: { width: n.width, height: n.height },
  }));
}

function toRFEdges(edges: ProjectGraphEdge[]): Edge[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.sourceId,
    target: e.targetId,
    label: e.label,
  }));
}

interface GraphBoardFlowProps {
  board: GraphBoard;
}

export const GraphBoardFlow: React.FC<GraphBoardFlowProps> = ({ board }) => {
  const { updateGraphNode, addGraphEdge } = useProjectStore();

  const initialNodes = useMemo(() => toRFNodes(board.nodes), [board.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const initialEdges = useMemo(() => toRFEdges(board.edges), [board.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync board changes (when board switches)
  React.useEffect(() => {
    setNodes(toRFNodes(board.nodes));
    setEdges(toRFEdges(board.edges));
  }, [board.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist node position changes back to store
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChange(changes);
    changes.forEach((change) => {
      if (change.type === 'position' && change.position && !change.dragging) {
        const storeNode = board.nodes.find((n) => n.id === change.id);
        if (storeNode) {
          updateGraphNode(board.id, { ...storeNode, x: change.position.x, y: change.position.y });
        }
      }
    });
  }, [board, updateGraphNode, onNodesChange]);

  const onConnect = useCallback((params: Connection) => {
    const edge: ProjectGraphEdge = {
      id: `edge_${Date.now()}`,
      sourceId: params.source!,
      targetId: params.target!,
      label: '',
    };
    addGraphEdge(board.id, edge);
    setEdges((eds) => addEdge({ ...params, id: edge.id }, eds));
  }, [board.id, addGraphEdge, setEdges]);

  return (
    <div className="h-full w-full" data-testid="graph-board-flow">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
};
