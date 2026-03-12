import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Database, Link as LinkIcon, Maximize2, Minimize2, Move, Network, PanelTopOpen, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';

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
  const board = useMemo(() => graphBoards.find((entry) => entry.id === activeGraphBoardId) || graphBoards[0], [activeGraphBoardId, graphBoards]);
  const [isAutoLayoutRunning, setIsAutoLayoutRunning] = useState(false);
  const [edgeDraftSource, setEdgeDraftSource] = useState<string | null>(null);

  useEffect(() => {
    if (location.pathname.endsWith('/relationships')) {
      const boardId = graphBoards.find((entry) => entry.id === 'board_relationships')?.id || graphBoards[0]?.id;
      if (boardId && boardId !== activeGraphBoardId) setActiveGraphBoard(boardId);
    }
  }, [activeGraphBoardId, graphBoards, location.pathname, setActiveGraphBoard]);

  useEffect(() => {
    const node = canvasRef.current;
    if (!node || !board) return;
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const nextZoom = Math.min(1.8, Math.max(0.6, board.view.zoom - event.deltaY * 0.001));
      setGraphBoardView(board.id, { ...board.view, zoom: nextZoom });
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, [board, setGraphBoardView]);

  if (!board) return null;

  return (
    <div className="flex h-full overflow-hidden bg-bg">
      <aside className="w-72 border-r border-border bg-bg-elev-1">
        <div className="border-b border-border bg-bg-elev-2 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">Boards</div>
              <div className="text-sm font-black text-text">Graph Navigator</div>
            </div>
            <button type="button" className="rounded-xl border border-border p-2 text-brand hover:border-brand" data-testid="graph-create-board-btn" onClick={() => {
              const newBoard = { id: `board_${Date.now()}`, name: 'Untitled Board', description: 'New mixed-mode board.', nodes: [], edges: [], view: { zoom: 1, panX: 0, panY: 0 }, selectedNodeIds: [], sortOrder: graphBoards.length };
              addGraphBoard(newBoard);
              setLastActionStatus('Board created');
            }}>
              <Plus size={16} />
            </button>
          </div>
        </div>
        <div className="h-full overflow-y-auto custom-scrollbar p-2">
          {graphBoards.slice().sort((a, b) => a.sortOrder - b.sortOrder).map((entry) => (
            <button
              type="button"
              key={entry.id}
              className={cn('mb-2 w-full rounded-2xl border px-4 py-3 text-left', entry.id === board.id ? 'border-brand bg-active text-text' : 'border-transparent text-text-2 hover:bg-hover')}
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
              <div className="mt-1 text-xs text-text-3">{entry.nodes.length} nodes / {entry.edges.length} edges</div>
            </button>
          ))}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-4 border-b border-border bg-bg-elev-1 px-6 py-3" data-testid="graph-toolbar">
          <button type="button" data-testid="graph-add-node-btn" className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white" onClick={() => {
            addGraphNode(board.id, { id: `graph_node_${Date.now()}`, kind: 'free_note', label: 'New Note', description: 'Context note', x: 140 + board.nodes.length * 20, y: 140 + board.nodes.length * 18, width: 220, height: 150, linkedEntityId: null, linkedEntityType: null, imageAssetId: null });
            setLastActionStatus('Node created');
          }}>
            <Plus size={13} className="mr-2 inline" />{t('graph.addNode')}
          </button>
          <button type="button" data-testid="graph-add-edge-btn" className={cn('rounded-xl border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em]', edgeDraftSource ? 'border-brand text-brand' : 'border-border text-text-2 hover:border-brand')} onClick={() => setEdgeDraftSource(edgeDraftSource ? null : board.nodes[0]?.id || null)}>
            <LinkIcon size={13} className="mr-2 inline" />{t('graph.addEdge')}
          </button>
          <button type="button" data-testid="graph-auto-layout-btn" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" onClick={() => {
            setIsAutoLayoutRunning(true);
            const nextNodes = board.nodes.map((node, index) => ({ ...node, x: 140 + (index % 3) * 280, y: 120 + Math.floor(index / 3) * 220 }));
            updateGraphBoard({ ...board, nodes: nextNodes });
            setLastActionStatus('Layout updated');
            setTimeout(() => setIsAutoLayoutRunning(false), 500);
          }}>
            <RefreshCw size={13} className={cn('mr-2 inline', isAutoLayoutRunning && 'animate-spin')} />{t('graph.autoLayout')}
          </button>
          <button type="button" data-testid="graph-reset-layout-btn" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" onClick={() => {
            setGraphBoardView(board.id, { zoom: 1, panX: 0, panY: 0 });
            setLastActionStatus('Layout reset');
          }}>
            <Move size={13} className="mr-2 inline" />{t('graph.reset')}
          </button>
          <button type="button" data-testid="graph-sync-selection-btn" className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand" onClick={() => {
            const selectedNode = board.nodes.find((node) => node.linkedEntityId === selectedEntity.id || node.id === selectedEntity.id) || board.nodes[0];
            addGraphSyncProposal('Graph sync batch', selectedNode ? `Queue sync for ${selectedNode.label} and convert it into reviewed project updates.` : 'Queue sync for the current graph selection and send it into Workbench Inbox.');
            setLastActionStatus('Proposal queued');
          }}>
            <Database size={13} className="mr-2 inline" />{t('graph.queueSync')}
          </button>
          <div className="ml-auto flex items-center gap-3 rounded-full border border-border bg-bg px-4 py-2">
            <button type="button" className="text-text-3 hover:text-brand" onClick={() => setGraphBoardView(board.id, { ...board.view, zoom: Math.max(0.6, board.view.zoom - 0.1) })}><Minimize2 size={14} /></button>
            <input type="range" min="0.6" max="1.8" step="0.1" value={board.view.zoom} onChange={(event) => setGraphBoardView(board.id, { ...board.view, zoom: Number(event.target.value) })} className="w-24 accent-brand" />
            <button type="button" className="text-text-3 hover:text-brand" onClick={() => setGraphBoardView(board.id, { ...board.view, zoom: Math.min(1.8, board.view.zoom + 0.1) })}><Maximize2 size={14} /></button>
          </div>
        </div>

        <div ref={canvasRef} className="relative min-w-0 flex-1 overflow-hidden bg-bg" data-testid="graph-canvas" onMouseDown={(event) => {
          if ((event.target as HTMLElement).dataset.graphNode) return;
          const startX = event.clientX;
          const startY = event.clientY;
          const initial = board.view;
          const onMove = (moveEvent: MouseEvent) => setGraphBoardView(board.id, { ...initial, panX: initial.panX + (moveEvent.clientX - startX), panY: initial.panY + (moveEvent.clientY - startY) });
          const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
          };
          window.addEventListener('mousemove', onMove);
          window.addEventListener('mouseup', onUp);
        }}>
          <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.85) 1px, transparent 1px)', backgroundSize: `${48 * board.view.zoom}px ${48 * board.view.zoom}px` }} />
          <svg className="absolute inset-0 h-full w-full overflow-visible">
            {board.edges.map((edge) => {
              const source = board.nodes.find((node) => node.id === edge.sourceId);
              const target = board.nodes.find((node) => node.id === edge.targetId);
              if (!source || !target) return null;
              const x1 = (source.x + source.width / 2) * board.view.zoom + board.view.panX;
              const y1 = (source.y + source.height / 2) * board.view.zoom + board.view.panY;
              const x2 = (target.x + target.width / 2) * board.view.zoom + board.view.panX;
              const y2 = (target.y + target.height / 2) * board.view.zoom + board.view.panY;
              return <path key={edge.id} d={`M ${x1} ${y1} C ${x1 + 100} ${y1}, ${x2 - 100} ${y2}, ${x2} ${y2}`} fill="none" stroke="rgba(242,200,121,0.45)" strokeWidth="2" />;
            })}
          </svg>
          <div className="absolute inset-0">
            {board.nodes.map((node) => {
              const isSelected = selectedEntity.id === node.linkedEntityId || selectedEntity.id === node.id;
              return (
                <button
                  type="button"
                  key={node.id}
                  data-testid={`graph-node-${node.linkedEntityId || node.id}`}
                  data-graph-node="true"
                  className={cn('absolute rounded-3xl border-2 p-4 text-left shadow-2 transition-transform', kindStyles[node.kind], isSelected && 'ring-2 ring-brand/40')}
                  style={{ left: node.x * board.view.zoom + board.view.panX, top: node.y * board.view.zoom + board.view.panY, width: node.width * board.view.zoom, minHeight: node.height * board.view.zoom }}
                  onClick={() => {
                    setSelectedEntity((node.linkedEntityType || 'graph_node') as never, node.linkedEntityId || node.id);
                    if (edgeDraftSource && edgeDraftSource !== node.id) {
                      addGraphEdge(board.id, { id: `edge_${Date.now()}`, sourceId: edgeDraftSource, targetId: node.id, label: 'linked' });
                      setEdgeDraftSource(null);
                    }
                  }}
                  onMouseDown={(event) => {
                    event.stopPropagation();
                    const startX = event.clientX;
                    const startY = event.clientY;
                    const initialX = node.x;
                    const initialY = node.y;
                    const onMove = (moveEvent: MouseEvent) => updateGraphNode(board.id, { ...node, x: initialX + (moveEvent.clientX - startX) / board.view.zoom, y: initialY + (moveEvent.clientY - startY) / board.view.zoom });
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
                        { id: 'duplicate-node', label: 'Duplicate Node', action: () => addGraphNode(board.id, { ...node, id: `${node.id}_copy_${Date.now()}`, x: node.x + 32, y: node.y + 32 }) },
                        { id: 'delete-node', label: 'Delete Node', action: () => updateGraphBoard({ ...board, nodes: board.nodes.filter((entry) => entry.id !== node.id), edges: board.edges.filter((edge) => edge.sourceId !== node.id && edge.targetId !== node.id) }), destructive: true },
                      ],
                    });
                  }}
                >
                  {node.kind === 'image_card' && node.imageAssetId ? <img src={node.imageAssetId} alt={node.label} className="mb-3 h-24 w-full rounded-2xl object-cover" /> : null}
                  <div className="mb-2 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.25em] opacity-80">{node.kind === 'image_card' ? <PanelTopOpen size={16} /> : <Network size={16} />}<span>{node.kind}</span></div>
                  <div className="text-sm font-black text-text">{node.label}</div>
                  <div className="mt-2 text-xs leading-relaxed text-text-2">{node.description}</div>
                </button>
              );
            })}
          </div>
          {!board.nodes.length && (
            <div className="absolute inset-0 flex items-center justify-center text-text-3">
              <div className="text-center opacity-30"><Network size={72} className="mx-auto mb-4" /><div className="text-sm font-black uppercase tracking-[0.35em]">{t('graph.empty')}</div></div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
