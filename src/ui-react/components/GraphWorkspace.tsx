import React, { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Database,
  Network,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';
import type { GraphBoard } from '../models/project';
import { GraphBoardFlow } from './graph';

export const GraphWorkspace = () => {
  const location = useLocation();
  const {
    graphBoards,
    activeGraphBoardId,
    selectedEntity,
    addGraphBoard,
    updateGraphBoard,
    deleteGraphBoard,
    setActiveGraphBoard,
    addGraphNode,
    addGraphSyncProposal,
  } = useProjectStore();
  const { setLastActionStatus, openContextMenu } = useUIStore();
  const { t } = useI18n();
  const [isAutoLayoutRunning, setIsAutoLayoutRunning] = useState(false);

  const activeBoard = useMemo(
    () => graphBoards.find((entry) => entry.id === activeGraphBoardId) || graphBoards[0] || null,
    [activeGraphBoardId, graphBoards],
  );

  useEffect(() => {
    if (location.pathname.endsWith('/relationships')) {
      const boardId = graphBoards.find((entry) => entry.id === 'board_relationships')?.id || graphBoards[0]?.id;
      if (boardId && boardId !== activeGraphBoardId) setActiveGraphBoard(boardId);
    }
  }, [activeGraphBoardId, graphBoards, location.pathname, setActiveGraphBoard]);

  return (
    <div className="flex h-full overflow-hidden bg-bg">
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
                  entry.id === activeBoard?.id ? 'border-brand bg-active text-text' : 'border-transparent text-text-2 hover:bg-hover',
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
            className="rounded-xl bg-brand px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-white disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!activeBoard}
            onClick={() => {
              if (!activeBoard) return;
              addGraphNode(activeBoard.id, {
                id: `node_${Date.now()}`,
                kind: 'free_note',
                label: 'New Note',
                description: '',
                x: 100 + Math.random() * 200,
                y: 100 + Math.random() * 200,
                width: 180,
                height: 80,
                linkedEntityId: null,
                linkedEntityType: null,
                imageAssetId: null,
              });
              setLastActionStatus('Node created');
            }}
          >
            <Plus size={13} className="mr-2 inline" />
            {t('graph.addNode')}
          </button>
          <button
            type="button"
            data-testid="graph-auto-layout-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!activeBoard}
            onClick={() => {
              if (!activeBoard) return;
              setIsAutoLayoutRunning(true);
              const nextNodes = activeBoard.nodes.map((node, index) => ({
                ...node,
                x: 160 + (index % 3) * 300,
                y: 140 + Math.floor(index / 3) * 240,
              }));
              updateGraphBoard({ ...activeBoard, nodes: nextNodes });
              setLastActionStatus('Layout updated');
              setTimeout(() => setIsAutoLayoutRunning(false), 500);
            }}
          >
            <RefreshCw size={13} className={cn('mr-2 inline', isAutoLayoutRunning && 'animate-spin')} />
            {t('graph.autoLayout')}
          </button>
          <button
            type="button"
            data-testid="graph-sync-selection-btn"
            className="rounded-xl border border-border px-4 py-2 text-[11px] font-black uppercase tracking-[0.25em] text-text-2 hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
            disabled={!activeBoard}
            onClick={() => {
              if (!activeBoard) return;
              const selectedNode =
                activeBoard.nodes.find((node) => node.linkedEntityId === selectedEntity.id || node.id === selectedEntity.id) ||
                activeBoard.nodes[0];
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
        </div>

        {activeBoard ? (
          <div className="flex-1 overflow-hidden">
            <GraphBoardFlow board={activeBoard} />
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center text-text-3">
            <div className="text-center">
              <Network size={72} className="mx-auto mb-4 opacity-30" />
              <div className="text-lg font-black">No board selected</div>
              <div className="mt-2 text-sm">Create a new board to start.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

