import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Crosshair,
  Database,
  Edit3,
  Link as LinkIcon,
  Maximize2,
  Minimize2,
  Move,
  Network,
  PanelTopOpen,
  Plus,
  RefreshCw,
  ScanSearch,
  Trash2,
} from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';
import type { GraphBoard, GraphNode } from '../models/project';

const MIN_ZOOM = 0.45;
const MAX_ZOOM = 1.9;

const kindStyles: Record<string, string> = {
  free_note: 'bg-amber-100/10 border-amber-200/30 text-amber-300',
  character_ref: 'bg-sky-100/10 border-sky-200/30 text-sky-300',
  event_ref: 'bg-amber-300/10 border-amber-300/40 text-amber-200',
  location_ref: 'bg-emerald-100/10 border-emerald-200/30 text-emerald-300',
  world_item_ref: 'bg-cyan-100/10 border-cyan-200/30 text-cyan-300',
  image_card: 'bg-white/5 border-white/10 text-text-2',
  group_frame: 'bg-transparent border-dashed border-white/18 text-text-3',
};

export const GraphWorkspace = () => {
  const location = useLocation();
  const {
    graphBoards,
    activeGraphBoardId,
    selectedEntity,
    setSelectedEntity,
    addGraphBoard,
    updateGraphBoard,
    deleteGraphBoard,
    setActiveGraphBoard,
    addGraphNode,
    updateGraphNode,
    addGraphEdge,
    setGraphBoardView,
    addGraphSyncProposal,
  } = useProjectStore();
  const { setLastActionStatus, openContextMenu } = useUIStore();
  const { t } = useI18n();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const board = useMemo(
    () => graphBoards.find((entry) => entry.id === activeGraphBoardId) || graphBoards[0],
    [activeGraphBoardId, graphBoards],
  );
  const [isAutoLayoutRunning, setIsAutoLayoutRunning] = useState(false);
  const [edgeDraftSource, setEdgeDraftSource] = useState<string | null>(null);
  const [nodeDraft, setNodeDraft] = useState<{ mode: 'create' | 'update'; node: GraphNode } | null>(null);

  useEffect(() => {
    if (location.pathname.endsWith('/relationships')) {
      const boardId = graphBoards.find((entry) => entry.id === 'board_relationships')?.id || graphBoards[0]?.id;
      if (boardId && boardId !== activeGraphBoardId) setActiveGraphBoard(boardId);
    }
  }, [activeGraphBoardId, graphBoards, location.pathname, setActiveGraphBoard]);

  const boardBounds = useMemo(() => getNodeBounds(board?.nodes || []), [board?.nodes]);
  const sceneBounds = useMemo(() => {
    const minX = Math.min(0, boardBounds.minX - 280);
    const minY = Math.min(0, boardBounds.minY - 220);
    const maxX = Math.max(2200, boardBounds.maxX + 320);
    const maxY = Math.max(1600, boardBounds.maxY + 260);
    return {
      minX,
      minY,
      width: maxX - minX,
      height: maxY - minY,
    };
  }, [boardBounds]);

  const applyZoom = (nextZoom: number, clientX?: number, clientY?: number) => {
    if (!board) return;
    const clampedZoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
    const rect = canvasRef.current?.getBoundingClientRect();
    const anchorX = rect
      ? typeof clientX === 'number'
        ? clientX - rect.left
        : rect.width / 2
      : 0;
    const anchorY = rect
      ? typeof clientY === 'number'
        ? clientY - rect.top
        : rect.height / 2
      : 0;
    const worldX = (anchorX - board.view.panX) / board.view.zoom;
    const worldY = (anchorY - board.view.panY) / board.view.zoom;

    setGraphBoardView(board.id, {
      zoom: clampedZoom,
      panX: anchorX - worldX * clampedZoom,
      panY: anchorY - worldY * clampedZoom,
    });
  };

  const focusBounds = (nodes: GraphNode[]) => {
    if (!board || !canvasRef.current) return;
    const bounds = getNodeBounds(nodes);
    const rect = canvasRef.current.getBoundingClientRect();
    const padding = 120;
    const zoom = clamp(
      Math.min(
        (rect.width - padding * 2) / Math.max(bounds.maxX - bounds.minX, 320),
        (rect.height - padding * 2) / Math.max(bounds.maxY - bounds.minY, 240),
      ),
      MIN_ZOOM,
      MAX_ZOOM,
    );
    setGraphBoardView(board.id, {
      zoom,
      panX: (rect.width - (bounds.maxX - bounds.minX) * zoom) / 2 - bounds.minX * zoom,
      panY: (rect.height - (bounds.maxY - bounds.minY) * zoom) / 2 - bounds.minY * zoom,
    });
  };

  useEffect(() => {
    const node = canvasRef.current;
    if (!node || !board) return;
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      applyZoom(board.view.zoom - event.deltaY * 0.0012, event.clientX, event.clientY);
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, [board]);

  if (!board) return null;

  const compactNode = board.view.zoom < 0.82;
  const selectedNode = board.nodes.find((node) => board.selectedNodeIds.includes(node.id)) || null;

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      {nodeDraft && (
        <NodeEditorModal
          node={nodeDraft.node}
          mode={nodeDraft.mode}
          onClose={() => setNodeDraft(null)}
          onSave={(nextNode, mode) => {
            if (mode === 'create') {
              addGraphNode(board.id, nextNode);
              updateGraphBoard({ ...board, selectedNodeIds: [nextNode.id] });
              setLastActionStatus('Node created');
            } else {
              updateGraphNode(board.id, nextNode);
              setLastActionStatus('Node updated');
            }
            setNodeDraft(null);
          }}
        />
      )}
      <aside className="w-72 border-r border-border bg-bg-elev-1">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Boards</div>
              <div className="text-sm font-black text-text">Graph Navigator</div>
            </div>
            <button
              type="button"
              className="rounded-xl border border-border p-2 text-brand hover:border-brand"
              data-testid="graph-create-board-btn"
              onClick={() => {
                const newBoard: GraphBoard = {
                  id: `board_${Date.now()}`,
                  name: 'Untitled Board',
                  description: 'New mixed-mode board.',
                  nodes: [],
                  edges: [],
                  view: { zoom: 1, panX: 0, panY: 0 },
                  selectedNodeIds: [],
                  sortOrder: graphBoards.length,
                };
                addGraphBoard(newBoard);
                setLastActionStatus('Board created');
              }}
            >
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {graphBoards
            .slice()
            .sort((a, b) => a.sortOrder - b.sortOrder)
            .map((entry) => (
              <button
                type="button"
                key={entry.id}
                className={cn(
                  'mb-2 w-full rounded-2xl border px-4 py-3 text-left',
                  entry.id === board.id ? 'border-brand bg-active text-text' : 'border-transparent text-text-2 hover:bg-hover',
                )}
                onClick={() => setActiveGraphBoard(entry.id)}
                onContextMenu={(event) => {
                  event.preventDefault();
                  openContextMenu({
                    x: event.clientX,
                    y: event.clientY,
                    items: [
                      { id: 'rename-board', label: 'Rename Board', action: () => updateGraphBoard({ ...entry, name: `${entry.name}*` }) },
                      { id: 'delete-board', label: 'Delete Board', action: () => deleteGraphBoard(entry.id), destructive: graphBoards.length > 1 },
                    ],
                  });
                }}
              >
                <div className="text-sm font-black">{entry.name}</div>
                <div className="mt-1 text-xs text-text-3">
                  {entry.nodes.length} nodes / {entry.edges.length} edges
                </div>
              </button>
            ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-4 border-b border-border bg-bg-elev-1 px-6 py-3" data-testid="graph-toolbar">
          <button
            type="button"
            data-testid="graph-add-node-btn"
            className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white"
            onClick={() => {
              setNodeDraft({ mode: 'create', node: {
                id: `graph_node_${Date.now()}`,
                kind: 'free_note',
                label: 'New Note',
                description: 'Context note',
                x: 140 + board.nodes.length * 24,
                y: 140 + board.nodes.length * 18,
                width: 220,
                height: 150,
                linkedEntityId: null,
                linkedEntityType: null,
                imageAssetId: null,
              } });
            }}
          >
            <Plus size={13} className="mr-2 inline" />
            {t('graph.addNode')}
          </button>
          <button
            type="button"
            data-testid="graph-edit-node-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => selectedNode && setNodeDraft({ mode: 'update', node: { ...selectedNode } })}
            disabled={!selectedNode}
          >
            <Edit3 size={13} className="mr-2 inline" />
            Edit Node
          </button>
          <button
            type="button"
            data-testid="graph-add-edge-btn"
            className={cn(
              'rounded-xl border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em]',
              edgeDraftSource ? 'border-brand text-brand' : 'border-border text-text-2 hover:border-brand',
            )}
            onClick={() => setEdgeDraftSource(edgeDraftSource ? null : board.nodes[0]?.id || null)}
          >
            <LinkIcon size={13} className="mr-2 inline" />
            {t('graph.addEdge')}
          </button>
          <button
            type="button"
            data-testid="graph-auto-layout-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
            onClick={() => {
              setIsAutoLayoutRunning(true);
              const nextNodes = board.nodes.map((node, index) => ({
                ...node,
                x: 160 + (index % 3) * 300,
                y: 140 + Math.floor(index / 3) * 240,
              }));
              updateGraphBoard({ ...board, nodes: nextNodes });
              setLastActionStatus('Layout updated');
              setTimeout(() => setIsAutoLayoutRunning(false), 500);
            }}
          >
            <RefreshCw size={13} className={cn('mr-2 inline', isAutoLayoutRunning && 'animate-spin')} />
            {t('graph.autoLayout')}
          </button>
          <button
            type="button"
            data-testid="graph-fit-board-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
            onClick={() => {
              focusBounds(board.nodes);
              setLastActionStatus('Board fit');
            }}
          >
            <ScanSearch size={13} className="mr-2 inline" />
            {t('graph.fitBoard')}
          </button>
          <button
            type="button"
            data-testid="graph-fit-selection-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
            onClick={() => {
              const selection = board.nodes.filter((node) => board.selectedNodeIds.includes(node.id));
              if (!selection.length) {
                setLastActionStatus('No selected nodes');
                return;
              }
              focusBounds(selection);
              setLastActionStatus('Selection fit');
            }}
          >
            <Crosshair size={13} className="mr-2 inline" />
            {t('graph.fitSelection')}
          </button>
          <button
            type="button"
            data-testid="graph-reset-layout-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
            onClick={() => {
              setGraphBoardView(board.id, { zoom: 1, panX: 0, panY: 0 });
              setLastActionStatus('Layout reset');
            }}
          >
            <Move size={13} className="mr-2 inline" />
            {t('graph.reset')}
          </button>
          <button
            type="button"
            data-testid="graph-sync-selection-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand"
            onClick={() => {
              const selectedNode =
                board.nodes.find((node) => node.linkedEntityId === selectedEntity.id || node.id === selectedEntity.id) ||
                board.nodes[0];
              addGraphSyncProposal(
                'Graph sync batch',
                selectedNode
                  ? `Queue sync for ${selectedNode.label} and convert it into reviewed project updates.`
                  : 'Queue sync for the current graph selection and send it into Workbench Inbox.',
              );
              setLastActionStatus('Proposal queued');
            }}
          >
            <Database size={13} className="mr-2 inline" />
            {t('graph.queueSync')}
          </button>
          <div className="ml-auto flex items-center gap-3 rounded-full border border-border bg-bg px-4 py-2">
            <button
              type="button"
              className="text-text-3 hover:text-brand"
              onClick={() => applyZoom(board.view.zoom - 0.1)}
            >
              <Minimize2 size={14} />
            </button>
            <input
              type="range"
              min={MIN_ZOOM}
              max={MAX_ZOOM}
              step="0.05"
              value={board.view.zoom}
              onChange={(event) => applyZoom(Number(event.target.value))}
              className="w-24 accent-brand"
            />
            <div className="min-w-[72px] text-center text-[10px] font-black uppercase tracking-[0.2em] text-text-3" data-testid="graph-zoom-label">
              {t('graph.zoom')} {Math.round(board.view.zoom * 100)}%
            </div>
            <button
              type="button"
              className="text-text-3 hover:text-brand"
              onClick={() => applyZoom(board.view.zoom + 0.1)}
            >
              <Maximize2 size={14} />
            </button>
          </div>
        </div>

        <div
          ref={canvasRef}
          className="relative min-w-0 flex-1 overflow-hidden bg-bg"
          data-testid="graph-canvas"
          onMouseDown={(event) => {
            if ((event.target as HTMLElement).closest('[data-graph-node="true"]')) return;
            const startX = event.clientX;
            const startY = event.clientY;
            const initial = board.view;
            const onMove = (moveEvent: MouseEvent) =>
              setGraphBoardView(board.id, {
                ...initial,
                panX: initial.panX + (moveEvent.clientX - startX),
                panY: initial.panY + (moveEvent.clientY - startY),
              });
            const onUp = () => {
              window.removeEventListener('mousemove', onMove);
              window.removeEventListener('mouseup', onUp);
            };
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
          }}
        >
          <div className="absolute left-6 top-5 z-20 rounded-full border border-border bg-slate-950/80 px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-text-3">
            {t('graph.panHint')}
          </div>
          <div
            className="absolute left-0 top-0"
            style={{
              width: sceneBounds.width,
              height: sceneBounds.height,
              transform: `translate(${board.view.panX}px, ${board.view.panY}px) scale(${board.view.zoom})`,
              transformOrigin: '0 0',
            }}
            data-testid="graph-scene"
          >
            <div
              className="absolute inset-0 opacity-[0.05]"
              style={{
                backgroundImage:
                  'linear-gradient(rgba(255,255,255,0.75) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.75) 1px, transparent 1px)',
                backgroundSize: '48px 48px',
              }}
            />
            <svg
              className="absolute inset-0 h-full w-full overflow-visible"
              viewBox={`0 0 ${sceneBounds.width} ${sceneBounds.height}`}
            >
              {board.edges.map((edge) => {
                const source = board.nodes.find((node) => node.id === edge.sourceId);
                const target = board.nodes.find((node) => node.id === edge.targetId);
                if (!source || !target) return null;
                const x1 = source.x + source.width / 2 - sceneBounds.minX;
                const y1 = source.y + source.height / 2 - sceneBounds.minY;
                const x2 = target.x + target.width / 2 - sceneBounds.minX;
                const y2 = target.y + target.height / 2 - sceneBounds.minY;
                const delta = Math.max(90, Math.abs(x2 - x1) * 0.32);
                return (
                  <path
                    key={edge.id}
                    d={`M ${x1} ${y1} C ${x1 + delta} ${y1}, ${x2 - delta} ${y2}, ${x2} ${y2}`}
                    fill="none"
                    stroke="rgba(242,200,121,0.45)"
                    strokeWidth="2.5"
                  />
                );
              })}
            </svg>

            <div className="absolute inset-0">
              {board.nodes.map((node) => {
                const isSelected =
                  selectedEntity.id === node.linkedEntityId ||
                  selectedEntity.id === node.id ||
                  board.selectedNodeIds.includes(node.id);
                return (
                  <button
                    type="button"
                    key={node.id}
                    data-testid={`graph-node-${node.linkedEntityId || node.id}`}
                    data-graph-node="true"
                    className={cn(
                      'absolute rounded-3xl border-2 text-left shadow-2 transition-transform',
                      kindStyles[node.kind],
                      compactNode ? 'p-3' : 'p-4',
                      isSelected && 'ring-2 ring-brand/40',
                    )}
                    style={{
                      left: node.x - sceneBounds.minX,
                      top: node.y - sceneBounds.minY,
                      width: node.width,
                      minHeight: node.height,
                    }}
                    onClick={() => {
                      setSelectedEntity((node.linkedEntityType || 'graph_node') as never, node.linkedEntityId || node.id);
                      updateGraphBoard({ ...board, selectedNodeIds: [node.id] });
                      if (edgeDraftSource && edgeDraftSource !== node.id) {
                        addGraphEdge(board.id, {
                          id: `edge_${Date.now()}`,
                          sourceId: edgeDraftSource,
                          targetId: node.id,
                          label: 'linked',
                        });
                        setEdgeDraftSource(null);
                      }
                    }}
                    onMouseDown={(event) => {
                      event.stopPropagation();
                      const startX = event.clientX;
                      const startY = event.clientY;
                      const initialX = node.x;
                      const initialY = node.y;
                      const onMove = (moveEvent: MouseEvent) =>
                        updateGraphNode(board.id, {
                          ...node,
                          x: initialX + (moveEvent.clientX - startX) / board.view.zoom,
                          y: initialY + (moveEvent.clientY - startY) / board.view.zoom,
                        });
                      const onUp = () => {
                        window.removeEventListener('mousemove', onMove);
                        window.removeEventListener('mouseup', onUp);
                      };
                      window.addEventListener('mousemove', onMove);
                      window.addEventListener('mouseup', onUp);
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      openContextMenu({
                        x: event.clientX,
                        y: event.clientY,
                        items: [
                          {
                            id: 'edit-node',
                            label: 'Edit Node',
                            action: () => setNodeDraft({ mode: 'update', node: { ...node } }),
                          },
                          {
                            id: 'duplicate-node',
                            label: 'Duplicate Node',
                            action: () =>
                              addGraphNode(board.id, {
                                ...node,
                                id: `${node.id}_copy_${Date.now()}`,
                                x: node.x + 32,
                                y: node.y + 32,
                              }),
                          },
                          {
                            id: 'delete-node',
                            label: 'Delete Node',
                            action: () =>
                              updateGraphBoard({
                                ...board,
                                nodes: board.nodes.filter((entry) => entry.id !== node.id),
                                edges: board.edges.filter((edge) => edge.sourceId !== node.id && edge.targetId !== node.id),
                              }),
                            destructive: true,
                          },
                        ],
                      });
                    }}
                  >
                    {node.kind === 'image_card' && node.imageAssetId ? (
                      <img src={node.imageAssetId} alt={node.label} className="mb-3 h-24 w-full rounded-2xl object-cover" />
                    ) : null}
                    <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.25em] opacity-80">
                      {node.kind === 'image_card' ? <PanelTopOpen size={16} /> : <Network size={16} />}
                      <span>{node.kind}</span>
                    </div>
                    <div className={cn('font-black text-text', compactNode ? 'text-xs' : 'text-sm')}>{node.label}</div>
                    {!compactNode && <div className="mt-2 text-xs leading-relaxed text-text-2">{node.description}</div>}
                  </button>
                );
              })}
            </div>
          </div>

          {!board.nodes.length && (
            <div className="absolute inset-0 flex items-center justify-center text-text-3">
              <div className="text-center opacity-30">
                <Network size={72} className="mx-auto mb-4" />
                <div className="text-sm font-black uppercase tracking-[0.35em]">{t('graph.empty')}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const getNodeBounds = (nodes: GraphNode[]) => {
  if (!nodes.length) {
    return { minX: 0, minY: 0, maxX: 1200, maxY: 800 };
  }

  return nodes.reduce(
    (acc, node) => ({
      minX: Math.min(acc.minX, node.x),
      minY: Math.min(acc.minY, node.y),
      maxX: Math.max(acc.maxX, node.x + node.width),
      maxY: Math.max(acc.maxY, node.y + node.height),
    }),
    {
      minX: Number.POSITIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
    },
  );
};

const NodeEditorModal = ({
  node,
  mode,
  onClose,
  onSave,
}: {
  node: GraphNode;
  mode: 'create' | 'update';
  onClose: () => void;
  onSave: (node: GraphNode, mode: 'create' | 'update') => void;
}) => {
  const [draft, setDraft] = useState(node);

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/60 p-6" onClick={onClose} data-testid="graph-node-modal">
      <div className="w-full max-w-2xl rounded-[32px] border border-border bg-bg-elev-1 shadow-2" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border bg-bg-elev-2 px-6 py-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Graph Node</div>
            <div className="text-sm font-black text-text">{mode === 'create' ? 'Create node' : 'Edit node'}</div>
          </div>
          <button type="button" className="rounded p-2 text-text-3 hover:bg-hover hover:text-text" onClick={onClose}>
            <Trash2 size={16} />
          </button>
        </div>
        <div className="grid gap-5 p-6 md:grid-cols-2">
          <label className="block md:col-span-2">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Type</div>
            <select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as GraphNode['kind'] })} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" data-testid="graph-node-kind-input">
              {Object.keys(kindStyles).map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label className="block md:col-span-2">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Label</div>
            <input value={draft.label} onChange={(event) => setDraft({ ...draft, label: event.target.value })} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" data-testid="graph-node-label-input" />
          </label>
          <label className="block md:col-span-2">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Description</div>
            <textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="h-32 w-full rounded-3xl border border-border bg-bg px-4 py-4 text-sm leading-relaxed text-text-2 outline-none" data-testid="graph-node-description-input" />
          </label>
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Width</div>
            <input type="number" value={draft.width} onChange={(event) => setDraft({ ...draft, width: Number(event.target.value) || draft.width })} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
          </label>
          <label className="block">
            <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-text-3">Height</div>
            <input type="number" value={draft.height} onChange={(event) => setDraft({ ...draft, height: Number(event.target.value) || draft.height })} className="w-full rounded-2xl border border-border bg-bg px-4 py-3 outline-none" />
          </label>
        </div>
        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <button type="button" className="rounded-xl border border-border px-4 py-2 text-sm text-text-2" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="rounded-xl bg-brand px-4 py-2 text-sm font-black text-white" onClick={() => onSave(draft, mode)} data-testid="graph-node-save-btn">
            Save Node
          </button>
        </div>
      </div>
    </div>
  );
};
