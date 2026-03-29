import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  Node,
  Edge,
  NodeChange,
  useNodesState,
  useEdgesState,
  NodeTypes,
  EdgeTypes,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useProjectStore, useUIStore } from '../../store';
import { useI18n } from '../../i18n';
import type { TimelineEvent, TimelineBranch } from '../../models/project';
import { TimelineEventNode } from './TimelineEventNode';
import { BranchEdge } from './BranchEdge';
import { EventEditDrawer } from './EventEditDrawer';

const GRID_SIZE = 20;

const nodeTypes: NodeTypes = { timelineEvent: TimelineEventNode };
const edgeTypes: EdgeTypes = { branchEdge: BranchEdge };

interface TimelineCanvasProps {
  events: TimelineEvent[];
  branches: TimelineBranch[];
}

function snapToGrid(value: number, grid: number): number {
  return Math.round(value / grid) * grid;
}

function toRFNodes(events: TimelineEvent[], onEdit: (id: string) => void): Node[] {
  return events.map((event, idx) => {
    const pos = event.position ?? { x: idx * 220, y: 0 };
    return {
      id: event.id,
      type: 'timelineEvent',
      position: pos,
      data: {
        label: event.title,
        importance: event.importance,
        summary: event.summary,
        timeText: event.time,
        eventId: event.id,
        onEdit: () => onEdit(event.id),
      },
    };
  });
}

function toRFEdges(branches: TimelineBranch[], events: TimelineEvent[]): Edge[] {
  const edges: Edge[] = [];
  branches.forEach((branch) => {
    const branchEvents = events
      .filter((e) => e.branchId === branch.id)
      .sort((a, b) => a.orderIndex - b.orderIndex);

    // Connect sequential events on the same branch
    for (let i = 0; i < branchEvents.length - 1; i++) {
      edges.push({
        id: `edge_${branch.id}_${branchEvents[i].id}_${branchEvents[i + 1].id}`,
        source: branchEvents[i].id,
        target: branchEvents[i + 1].id,
        type: 'branchEdge',
        sourceHandle: null,
        targetHandle: null,
        data: { label: branch.name },
        style: { stroke: branch.color || '#38bdf8' },
      });
    }

    // Fork connection: connect forkEventId to first event on this branch
    if (branch.forkEventId && branchEvents.length > 0) {
      const forkEdgeId = `fork_${branch.id}_${branch.forkEventId}`;
      if (!edges.find((e) => e.id === forkEdgeId)) {
        edges.push({
          id: forkEdgeId,
          source: branch.forkEventId,
          target: branchEvents[0].id,
          type: 'branchEdge',
          data: { label: '' },
          style: { stroke: branch.color || '#38bdf8', strokeDasharray: '4 2' },
        });
      }
    }

    // Merge connection: connect last event on this branch to mergeEventId
    if (branch.mergeEventId && branchEvents.length > 0) {
      const lastEvent = branchEvents[branchEvents.length - 1];
      const mergeEdgeId = `merge_${branch.id}_${branch.mergeEventId}`;
      if (!edges.find((e) => e.id === mergeEdgeId)) {
        edges.push({
          id: mergeEdgeId,
          source: lastEvent.id,
          target: branch.mergeEventId,
          type: 'branchEdge',
          data: { label: '' },
          style: { stroke: branch.color || '#38bdf8', strokeDasharray: '4 2' },
        });
      }
    }
  });
  return edges;
}

function TimelineCanvasInner({ events, branches }: TimelineCanvasProps) {
  const { updateTimelineEventPosition, deleteTimelineEvent } = useProjectStore();
  const { openContextMenu } = useUIStore();
  const { t } = useI18n();
  const [editingEventId, setEditingEventId] = useState<string | null>(null);
  const editingEventIdRef = useRef<string | null>(null);
  useEffect(() => { editingEventIdRef.current = editingEventId; }, [editingEventId]);
  const [snapEnabled, setSnapEnabled] = useState(true);

  const initialNodes = useMemo(
    () => toRFNodes(events, setEditingEventId),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [events.map((e) => e.id).join(',')]
  );
  const initialEdges = useMemo(
    () => toRFEdges(branches, events),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [branches.map((b) => b.id).join(','), events.map((e) => e.id).join(',')]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Sync when external data changes
  React.useEffect(() => {
    setNodes(toRFNodes(events, setEditingEventId));
  }, [events]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChange(changes);
      changes.forEach((change) => {
        if (change.type === 'position' && change.position && !change.dragging) {
          const pos = snapEnabled
            ? { x: snapToGrid(change.position.x, GRID_SIZE), y: snapToGrid(change.position.y, GRID_SIZE) }
            : change.position;
          // Get fresh state to avoid stale closure
          const freshEvents = useProjectStore.getState().timelineEvents;
          if (freshEvents.find((e) => e.id === change.id)) {
            updateTimelineEventPosition(change.id, pos);
          }
        }
      });
    },
    [snapEnabled, updateTimelineEventPosition, onNodesChange]
  );

  const onNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    setEditingEventId(node.id);
  }, []);

  const onNodeContextMenu = useCallback(
    (e: React.MouseEvent, node: Node) => {
      e.preventDefault();
      const nodeId = node.id;
      openContextMenu({
        x: e.clientX,
        y: e.clientY,
        items: [
          {
            id: 'edit',
            label: t('timeline.editEvent'),
            action: () => setEditingEventId(nodeId),
          },
          {
            id: 'delete',
            label: t('timeline.deleteEvent'),
            action: () => {
              deleteTimelineEvent(nodeId);
              if (editingEventIdRef.current === nodeId) setEditingEventId(null);
            },
            destructive: true,
          },
        ],
      });
    },
    [openContextMenu, t, deleteTimelineEvent]
  );

  const editingEvent = events.find((e) => e.id === editingEventId) ?? null;

  return (
    <div className="relative h-full w-full" data-testid="timeline-canvas">
      <div className="absolute top-3 right-4 z-10 flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-text-3 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={snapEnabled}
            onChange={(e) => setSnapEnabled(e.target.checked)}
            className="accent-brand"
          />
          {t('timeline.snapToGrid')}
        </label>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        snapToGrid={snapEnabled}
        snapGrid={[GRID_SIZE, GRID_SIZE]}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        defaultEdgeOptions={{ type: 'branchEdge' }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} />
        <Controls />
      </ReactFlow>
      {editingEvent && (
        <EventEditDrawer
          event={editingEvent}
          onClose={() => setEditingEventId(null)}
        />
      )}
    </div>
  );
}

export function TimelineCanvas(props: TimelineCanvasProps) {
  return (
    <ReactFlowProvider>
      <TimelineCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
