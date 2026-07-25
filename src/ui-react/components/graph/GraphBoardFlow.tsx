import React, { useCallback, useMemo, useState } from 'react';
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
  useNodesInitialized,
  useNodes,
  NodeChange,
  EdgeChange,
  addEdge,
  Connection,
  NodeTypes,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { X } from 'lucide-react';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import type { GraphBoard, GraphNode as ProjectGraphNode, GraphEdge as ProjectGraphEdge, GraphNodeKind } from '../../models/project';

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

const NODE_KIND_OPTIONS: GraphNodeKind[] = [
  'free_note',
  'character_ref',
  'event_ref',
  'location_ref',
  'world_item_ref',
  'image_card',
  'group_frame',
];

// Custom node renderer
const GraphBoardNode: React.FC<{ data: { node: ProjectGraphNode } }> = ({ data }) => {
  const n = data.node;
  const bg = kindColors[n.kind] || '#f1f5f9';
  return (
    <div
      className="graph-node-drag-handle rounded-2xl border border-border p-3 shadow-sm"
      data-testid={`graph-node-${n.id}`}
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

const GraphInteractionReadiness: React.FC<{
  expectedNodeIds: string[];
  onChange: (ready: boolean) => void;
}> = ({ expectedNodeIds, onChange }) => {
  const nodesInitialized = useNodesInitialized({ includeHiddenNodes: false });
  const renderedNodes = useNodes();
  const expectedSignature = expectedNodeIds.join('|');
  const renderedSignature = renderedNodes.map((node) => node.id).sort().join('|');
  const isCurrentBoardReady = nodesInitialized && expectedSignature === renderedSignature;

  React.useEffect(() => {
    onChange(isCurrentBoardReady);
  }, [isCurrentBoardReady, onChange]);

  return null;
};

// Convert our model to React Flow format
function toRFNodes(nodes: ProjectGraphNode[]): Node[] {
  return nodes.map((n) => ({
    id: n.id,
    type: 'graphBoard',
    position: { x: n.x, y: n.y },
    data: { node: n },
    // Capture the undo snapshot on the real pointer-down event.
    dragHandle: '.graph-node-drag-handle',
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

// Inline NodeEditModal
const NodeEditModal: React.FC<{
  nodeId: string;
  board: GraphBoard;
  onClose: () => void;
}> = ({ nodeId, board, onClose }) => {
  const { updateGraphNode } = useProjectStore();
  const { t } = useI18n();
  const node = board.nodes.find((n) => n.id === nodeId);
  const [label, setLabel] = useState(node?.label || '');
  const [description, setDescription] = useState(node?.description || '');
  const [kind, setKind] = useState<GraphNodeKind>(node?.kind || 'free_note');

  if (!node) return null;

  const handleSave = () => {
    updateGraphNode(board.id, { ...node, label, description, kind });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-6" data-testid="graph-node-edit-modal">
      <div className="w-full max-w-md rounded-[32px] border border-border bg-bg-elev-1 shadow-2">
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
          <div className="text-sm font-black text-text">{t('graph.editNode')}</div>
          <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('graph.nodeLabel')}</div>
            <input
              className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none text-sm text-text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div>
            <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('graph.nodeDescription')}</div>
            <textarea
              className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none text-sm text-text-2 h-24 resize-none"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">{t('graph.nodeKind')}</div>
            <select
              className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none text-sm text-text"
              value={kind}
              onChange={(e) => setKind(e.target.value as GraphNodeKind)}
            >
              {NODE_KIND_OPTIONS.map((k) => (
                <option key={k} value={k}>{k.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              data-testid="graph-node-modal-cancel-btn"
              className="rounded-xl border border-border px-5 py-3 text-sm text-text-2"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              data-testid="graph-node-modal-save-btn"
              className="rounded-xl bg-brand px-5 py-3 text-sm font-black text-white"
              onClick={handleSave}
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

interface GraphBoardFlowProps {
  board: GraphBoard;
}

export const GraphBoardFlow: React.FC<GraphBoardFlowProps> = ({ board }) => {
  const { updateGraphNode, addGraphEdge, deleteGraphNode, deleteGraphEdge } = useProjectStore();
  const { openContextMenu } = useUIStore();
  const { t } = useI18n();
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [readyBoardId, setReadyBoardId] = useState<string | null>(null);
  const [dragEnabledBoardId, setDragEnabledBoardId] = useState<string | null>(null);
  const [interactionReadyBoardId, setInteractionReadyBoardId] = useState<string | null>(null);
  const boardNodesReady = readyBoardId === board.id;
  const dragEnabled = dragEnabledBoardId === board.id;
  const interactionReady = interactionReadyBoardId === board.id;
  const handleInteractionReadiness = useCallback((ready: boolean) => {
    setReadyBoardId(ready ? board.id : null);
  }, [board.id]);

  React.useEffect(() => {
    if (!boardNodesReady) return;
    let readyFrame = 0;
    const enableFrame = requestAnimationFrame(() => {
      setDragEnabledBoardId(board.id);
      readyFrame = requestAnimationFrame(() => setInteractionReadyBoardId(board.id));
    });
    return () => {
      cancelAnimationFrame(enableFrame);
      cancelAnimationFrame(readyFrame);
    };
  }, [board.id, boardNodesReady]);

  const initialNodes = useMemo(() => toRFNodes(board.nodes), [board.id]);
  const initialEdges = useMemo(() => toRFEdges(board.edges), [board.id]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync board changes (when board switches or nodes/edges updated externally)
  React.useEffect(() => {
    setNodes(toRFNodes(board.nodes));
    setEdges(toRFEdges(board.edges));
  }, [board.id, board.nodes, board.edges]);

  // Persist node position changes back to store
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChange(changes);
    changes.forEach((change) => {
      if (change.type === 'position' && change.position && !change.dragging) {
        // Use fresh store state to avoid stale closure overwriting label edits
        const currentBoards = useProjectStore.getState().graphBoards;
        const currentBoard = currentBoards.find((b) => b.id === board.id);
        if (!currentBoard) return;
        const storeNode = currentBoard.nodes.find((n) => n.id === change.id);
        if (storeNode) {
          updateGraphNode(board.id, { ...storeNode, x: change.position.x, y: change.position.y });
        }
      }
    });
  }, [board.id, updateGraphNode, onNodesChange]);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    onEdgesChange(changes);
  }, [onEdgesChange]);

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

  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    setEditingNodeId(node.id);
  }, []);

  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    const nodeId = node.id;
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      returnFocus: e.currentTarget as HTMLElement,
      items: [
        {
          id: 'edit',
          label: t('graph.editNode'),
          action: () => setEditingNodeId(nodeId),
        },
        {
          id: 'delete',
          label: t('graph.deleteNode'),
          action: () => {
            deleteGraphNode(board.id, nodeId);
            setNodes((nds) => nds.filter((n) => n.id !== nodeId));
            setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
          },
          destructive: true,
        },
      ],
    });
  }, [board.id, openContextMenu, t, deleteGraphNode, setNodes, setEdges]);

  const onNodeDragStart = useCallback(() => {
    useProjectStore.getState().beginUndoTransaction('Move graph node');
  }, []);

  const onNodeDragStop = useCallback((_: React.MouseEvent, node: Node) => {
    // Controlled React Flow can omit the final `dragging: false` NodeChange.
    // Its drag-stop callback always carries the authoritative final position.
    const currentBoard = useProjectStore.getState().graphBoards.find((entry) => entry.id === board.id);
    const currentNode = currentBoard?.nodes.find((entry) => entry.id === node.id);
    if (currentNode && (currentNode.x !== node.position.x || currentNode.y !== node.position.y)) {
      updateGraphNode(board.id, {
        ...currentNode,
        x: node.position.x,
        y: node.position.y,
      });
    }
    useProjectStore.getState().commitUndoTransaction();
  }, [board.id, updateGraphNode]);

  const onEdgeContextMenu = useCallback((e: React.MouseEvent, edge: Edge) => {
    e.preventDefault();
    const edgeId = edge.id;
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      returnFocus: e.currentTarget as HTMLElement,
      items: [
        {
          id: 'delete',
          label: t('graph.deleteEdge'),
          action: () => {
            deleteGraphEdge(board.id, edgeId);
            setEdges((eds) => eds.filter((ed) => ed.id !== edgeId));
          },
          destructive: true,
        },
      ],
    });
  }, [board.id, openContextMenu, t, deleteGraphEdge, setEdges]);

  return (
    <div
      className="relative h-full min-h-0 min-w-0 w-full overflow-hidden"
      data-testid="graph-board-flow"
      data-graph-interaction-ready={interactionReady ? 'true' : 'false'}
    >
      <ReactFlow
        className="relative z-0"
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        nodesDraggable={dragEnabled}
        minZoom={0.1}
        maxZoom={2}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        onEdgeContextMenu={onEdgeContextMenu}
        onNodeDragStart={onNodeDragStart}
        onNodeDragStop={onNodeDragStop}
        nodeDragThreshold={0}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <GraphInteractionReadiness
          key={board.id}
          expectedNodeIds={board.nodes.map((node) => node.id).sort()}
          onChange={handleInteractionReadiness}
        />
        <Background variant={BackgroundVariant.Dots} gap={24} />
        <Controls />
        <MiniMap />
      </ReactFlow>
      {editingNodeId && (
        <NodeEditModal
          nodeId={editingNodeId}
          board={board}
          onClose={() => setEditingNodeId(null)}
        />
      )}
    </div>
  );
};
