import React, { useRef, useState } from 'react';
import { DndContext, DragEndEvent, DragOverlay, DragStartEvent, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { useDraggable, useDroppable } from '@dnd-kit/core';

// Generic tree node shape accepted by TagTreePanel.
export interface TagTreeNode {
  id: string;
  name: string;
  parentId?: string | null;
  parentTagId?: string | null;
  sortOrder?: number;
  collapsed?: boolean;
}

interface TagTreePanelProps<T extends TagTreeNode> {
  nodes: T[];
  renderNodeContent: (node: T, depth: number) => React.ReactNode;
  onMove: (dragId: string, newParentId: string | null, insertBeforeSiblingId?: string | null) => void;
  onToggleCollapse: (nodeId: string) => void;
  testIdPrefix: string;
}

// Returns depth by walking the parentId chain.
function getDepth(nodeId: string, nodes: TagTreeNode[]): number {
  let depth = 0;
  let current: string | null | undefined = nodeId;
  const visited = new Set<string>();
  while (current) {
    if (visited.has(current)) break;
    visited.add(current);
    const node = nodes.find((n) => n.id === current);
    const parentId = node?.parentTagId ?? node?.parentId ?? null;
    if (!parentId) break;
    current = parentId;
    depth++;
  }
  return depth;
}

// Returns ids of all descendants.
function getDescendantIds(nodeId: string, nodes: TagTreeNode[]): Set<string> {
  const result = new Set<string>();
  const queue = [nodeId];
  while (queue.length) {
    const id = queue.shift()!;
    for (const n of nodes) {
      const pId = n.parentTagId ?? n.parentId ?? null;
      if (pId === id && !result.has(n.id)) {
        result.add(n.id);
        queue.push(n.id);
      }
    }
  }
  return result;
}

// Resolve canonical parentId handling both CharacterTag and WorldCategoryNode shapes.
function resolveParentId(node: TagTreeNode): string | null {
  return node.parentTagId !== undefined ? (node.parentTagId ?? null) : (node.parentId ?? null);
}

// Flatten tree in display order, skipping children of collapsed nodes.
function flattenTree<T extends TagTreeNode>(nodes: T[]): T[] {
  const roots = nodes
    .filter((n) => !resolveParentId(n))
    .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0));

  const result: T[] = [];
  const collapsedAncestors = new Set<string>();

  function visit(n: T) {
    result.push(n);
    if (n.collapsed) {
      collapsedAncestors.add(n.id);
      return;
    }
    const children = nodes
      .filter((c) => resolveParentId(c) === n.id)
      .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0));
    for (const child of children) {
      if (!collapsedAncestors.has(resolveParentId(child) ?? '')) visit(child);
    }
  }

  for (const root of roots) visit(root);
  return result;
}

// Drop zone: thin "before" indicator above a row.
function DropBefore({ id, testIdPrefix }: { id: string; testIdPrefix: string }) {
  const { setNodeRef, isOver } = useDroppable({ id: `drop-before-${id}` });
  return (
    <div
      ref={setNodeRef}
      data-testid={`${testIdPrefix}-drop-before-${id}`}
      style={{ height: 6, marginBottom: -6, position: 'relative', zIndex: 10 }}
      className={isOver ? 'bg-brand/40 rounded' : ''}
    />
  );
}

// Drop zone: inside (becomes a child of this node).
function DropInside({ id, testIdPrefix, children }: { id: string; testIdPrefix: string; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: `drop-inside-${id}` });
  return (
    <div
      ref={setNodeRef}
      data-testid={`${testIdPrefix}-drop-inside-${id}`}
      className={isOver ? 'outline outline-2 outline-brand/50 rounded' : ''}
    >
      {children}
    </div>
  );
}

interface TreeRowProps<T extends TagTreeNode> {
  node: T;
  depth: number;
  testIdPrefix: string;
  renderNodeContent: (node: T, depth: number) => React.ReactNode;
  onToggleCollapse: (nodeId: string) => void;
  hasChildren: boolean;
}

function TreeRow<T extends TagTreeNode>({ node, depth, testIdPrefix, renderNodeContent, onToggleCollapse, hasChildren }: TreeRowProps<T>) {
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({ id: node.id });

  return (
    <div
      ref={setDragRef}
      data-testid={`${testIdPrefix}-row-${node.id}`}
      style={{ paddingLeft: depth * 16, opacity: isDragging ? 0.4 : 1 }}
      className="flex items-center gap-1 py-0.5 group"
    >
      <button
        data-testid={`${testIdPrefix}-row-${node.id}-expand`}
        className="w-4 h-4 flex items-center justify-center text-text-muted flex-shrink-0"
        onClick={() => hasChildren && onToggleCollapse(node.id)}
        style={{ visibility: hasChildren ? 'visible' : 'hidden' }}
        aria-label={node.collapsed ? 'Expand' : 'Collapse'}
      >
        <svg viewBox="0 0 8 8" width="8" height="8" fill="currentColor">
          {node.collapsed
            ? <polygon points="2,1 6,4 2,7" />
            : <polygon points="1,2 7,2 4,6" />
          }
        </svg>
      </button>

      <button
        data-testid={`${testIdPrefix}-row-${node.id}-drag-handle`}
        className="w-4 h-4 flex items-center justify-center text-text-muted opacity-0 group-hover:opacity-100 cursor-grab flex-shrink-0"
        {...attributes}
        {...listeners}
        aria-label="Drag to reorder"
      >
        <svg viewBox="0 0 8 8" width="8" height="8" fill="currentColor">
          <circle cx="2.5" cy="2.5" r="1" /><circle cx="5.5" cy="2.5" r="1" />
          <circle cx="2.5" cy="5.5" r="1" /><circle cx="5.5" cy="5.5" r="1" />
        </svg>
      </button>

      <div className="flex-1 min-w-0">
        {renderNodeContent(node, depth)}
      </div>
    </div>
  );
}

export function TagTreePanel<T extends TagTreeNode>({
  nodes,
  renderNodeContent,
  onMove,
  onToggleCollapse,
  testIdPrefix,
}: TagTreePanelProps<T>) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [activeId, setActiveId] = useState<string | null>(null);
  const activeNode = activeId ? nodes.find((n) => n.id === activeId) ?? null : null;

  const visibleNodes = flattenTree(nodes);
  const childrenMap = new Map<string, boolean>();
  for (const n of nodes) {
    const pId = resolveParentId(n);
    if (pId) childrenMap.set(pId, true);
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const dragId = String(event.active.id);
    const overId = event.over ? String(event.over.id) : null;
    if (!overId || overId === dragId) return;

    const descendantIds = getDescendantIds(dragId, nodes);

    if (overId.startsWith('drop-before-')) {
      const targetId = overId.replace('drop-before-', '');
      if (descendantIds.has(targetId)) return;
      const target = nodes.find((n) => n.id === targetId);
      if (!target) return;
      const targetParentId = resolveParentId(target);
      onMove(dragId, targetParentId, targetId);
    } else if (overId.startsWith('drop-inside-')) {
      const targetId = overId.replace('drop-inside-', '');
      if (targetId === dragId || descendantIds.has(targetId)) return;
      onMove(dragId, targetId, null);
    }
  }

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div data-testid={`tag-tree-panel-${testIdPrefix}`} className="select-none">
        {visibleNodes.map((node) => {
          const depth = getDepth(node.id, nodes);
          const hasChildren = !!childrenMap.get(node.id);
          return (
            <div key={node.id}>
              <DropBefore id={node.id} testIdPrefix={testIdPrefix} />
              <DropInside id={node.id} testIdPrefix={testIdPrefix}>
                <TreeRow
                  node={node}
                  depth={depth}
                  testIdPrefix={testIdPrefix}
                  renderNodeContent={renderNodeContent}
                  onToggleCollapse={onToggleCollapse}
                  hasChildren={hasChildren}
                />
              </DropInside>
            </div>
          );
        })}
      </div>

      <DragOverlay>
        {activeNode && (
          <div className="bg-bg-elev-2 border border-brand/40 rounded px-3 py-1.5 text-sm shadow-lg opacity-90">
            {activeNode.name}
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
