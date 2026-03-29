import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { ChevronRight, ChevronDown, Plus, FileText } from 'lucide-react';
import { useProjectStore, useUIStore } from '../store';
import { useI18n } from '../i18n';
import { cn } from '../utils';
import { NarrativeEditor } from './editor';
import type { ManuscriptNode, ManuscriptNodeType } from '../models/project';

const NODE_TYPE_COLORS: Record<ManuscriptNodeType, string> = {
  act: 'bg-purple-100 text-purple-700',
  part: 'bg-blue-100 text-blue-700',
  chapter_outline: 'bg-amber-100 text-amber-700',
  scene_outline: 'bg-green-100 text-green-700',
  note: 'bg-gray-100 text-gray-600',
};

const NODE_TYPE_ORDER: ManuscriptNodeType[] = [
  'act',
  'part',
  'chapter_outline',
  'scene_outline',
  'note',
];

function buildTree(nodes: ManuscriptNode[]): ManuscriptNode[] {
  return [...nodes].sort((a, b) => {
    if (a.parentId === b.parentId) return a.orderIndex - b.orderIndex;
    return 0;
  });
}

function getChildren(nodes: ManuscriptNode[], parentId: string | null): ManuscriptNode[] {
  return nodes
    .filter((n) => n.parentId === parentId)
    .sort((a, b) => a.orderIndex - b.orderIndex);
}

interface AddNodeFormState {
  parentId: string | null;
  title: string;
  type: ManuscriptNodeType;
}

export const ManuscriptWorkspace: React.FC = () => {
  const { t } = useI18n();
  const {
    manuscriptNodes,
    addManuscriptNode,
    updateManuscriptNode,
    deleteManuscriptNode,
    loadManuscriptNodeContent,
    saveManuscriptNodeContent,
    projectRoot,
  } = useProjectStore();
  const { openContextMenu, closeContextMenu } = useUIStore();

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [editorContent, setEditorContent] = useState('');
  const [wordCount, setWordCount] = useState(0);
  const [addNodeForm, setAddNodeForm] = useState<AddNodeFormState | null>(null);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sortedNodes = useMemo(() => buildTree(manuscriptNodes), [manuscriptNodes]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  // Load content when selected node changes
  useEffect(() => {
    if (!selectedNodeId) {
      setEditorContent('');
      setWordCount(0);
      return;
    }
    let cancelled = false;
    loadManuscriptNodeContent(projectRoot, selectedNodeId).then((content) => {
      if (!cancelled) {
        setEditorContent(content);
        setWordCount(countWords(content));
      }
    });
    return () => { cancelled = true; };
  }, [selectedNodeId, projectRoot, loadManuscriptNodeContent]);

  const handleEditorUpdate = useCallback(
    (html: string) => {
      setEditorContent(html);
      setWordCount(countWords(html));
      if (!selectedNodeId) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        saveManuscriptNodeContent(projectRoot, selectedNodeId, html);
        updateManuscriptNode(selectedNodeId, { wordCount: countWords(html) });
      }, 1000);
    },
    [selectedNodeId, projectRoot, saveManuscriptNodeContent, updateManuscriptNode]
  );

  const toggleCollapse = (id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleNodeClick = (id: string) => {
    setSelectedNodeId(id);
  };

  const handleAddNodeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!addNodeForm || !addNodeForm.title.trim()) return;
    const siblings = sortedNodes.filter((n) => n.parentId === addNodeForm.parentId);
    const depth = addNodeForm.parentId
      ? (sortedNodes.find((n) => n.id === addNodeForm.parentId)?.depth ?? 0) + 1
      : 0;
    addManuscriptNode({
      title: addNodeForm.title.trim(),
      type: addNodeForm.type,
      parentId: addNodeForm.parentId,
      orderIndex: siblings.length,
      linkedChapterId: null,
      linkedSceneId: null,
      depth,
      collapsed: false,
      wordCount: 0,
    });
    setAddNodeForm(null);
  };

  const startEditTitle = (node: ManuscriptNode) => {
    setEditingNodeId(node.id);
    setEditingTitle(node.title);
    closeContextMenu();
  };

  const commitEditTitle = (id: string) => {
    if (editingTitle.trim()) {
      updateManuscriptNode(id, { title: editingTitle.trim() });
    }
    setEditingNodeId(null);
    setEditingTitle('');
  };

  const handleContextMenu = (e: React.MouseEvent, node: ManuscriptNode) => {
    e.preventDefault();
    openContextMenu({
      x: e.clientX,
      y: e.clientY,
      items: [
        {
          id: 'add-child',
          label: t('manuscript.addChild'),
          action: () => {
            setAddNodeForm({ parentId: node.id, title: '', type: 'scene_outline' });
            closeContextMenu();
          },
        },
        {
          id: 'edit-title',
          label: t('manuscript.editTitle'),
          action: () => startEditTitle(node),
        },
        {
          id: 'delete',
          label: t('manuscript.delete'),
          destructive: true,
          action: () => {
            deleteManuscriptNode(node.id);
            if (selectedNodeId === node.id) setSelectedNodeId(null);
            closeContextMenu();
          },
        },
      ],
    });
  };

  const renderNode = (node: ManuscriptNode): React.ReactNode => {
    const children = getChildren(sortedNodes, node.id);
    const hasChildren = children.length > 0;
    const isCollapsed = collapsedIds.has(node.id);
    const isSelected = selectedNodeId === node.id;
    const isEditing = editingNodeId === node.id;

    return (
      <div key={node.id}>
        <div
          className={cn(
            'group flex items-center gap-1 px-2 py-1.5 rounded-md cursor-pointer select-none',
            isSelected ? 'bg-active text-text' : 'text-text-2 hover:bg-hover'
          )}
          style={{ paddingLeft: `${node.depth * 16 + 8}px` }}
          data-testid={`manuscript-node-${node.id}`}
          onClick={() => handleNodeClick(node.id)}
          onContextMenu={(e) => handleContextMenu(e, node)}
        >
          {/* Collapse toggle */}
          <button
            type="button"
            data-testid={`manuscript-node-toggle-${node.id}`}
            className="shrink-0 p-0.5 rounded hover:bg-hover"
            onClick={(e) => {
              e.stopPropagation();
              if (hasChildren) toggleCollapse(node.id);
            }}
            aria-label="toggle"
          >
            {hasChildren ? (
              isCollapsed ? (
                <ChevronRight size={12} className="text-text-2" />
              ) : (
                <ChevronDown size={12} className="text-text-2" />
              )
            ) : (
              <span className="inline-block w-3 h-3" />
            )}
          </button>

          {/* Title */}
          {isEditing ? (
            <input
              autoFocus
              className="flex-1 bg-transparent border-b border-brand text-[12px] outline-none"
              value={editingTitle}
              onChange={(e) => setEditingTitle(e.target.value)}
              onBlur={() => commitEditTitle(node.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitEditTitle(node.id);
                if (e.key === 'Escape') { setEditingNodeId(null); setEditingTitle(''); }
              }}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="flex-1 truncate text-[12px] font-medium">{node.title}</span>
          )}

          {/* Type badge */}
          <span
            className={cn(
              'shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold uppercase',
              NODE_TYPE_COLORS[node.type]
            )}
          >
            {t(`manuscript.nodeType.${node.type}`)}
          </span>

          {/* Word count badge */}
          {node.wordCount > 0 && (
            <span className="shrink-0 text-[10px] text-text-2 ml-1">
              {node.wordCount.toLocaleString()}
            </span>
          )}
        </div>

        {/* Children */}
        {hasChildren && !isCollapsed && (
          <div>
            {children.map((child) => renderNode(child))}
          </div>
        )}
      </div>
    );
  };

  const rootNodes = getChildren(sortedNodes, null);

  return (
    <div className="flex h-full overflow-hidden bg-bg" data-testid="manuscript-workspace">
      {/* Left pane — Outline tree */}
      <aside className="w-72 border-r border-border bg-bg-elev-1 flex flex-col overflow-hidden shrink-0">
        {/* Toolbar */}
        <div className="border-b border-border bg-bg-elev-2 px-4 py-3 flex items-center justify-between shrink-0">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.25em] text-brand-2">
              {t('manuscript.title')}
            </div>
            <div className="text-sm font-black text-text">{t('manuscript.outline')}</div>
          </div>
          <button
            type="button"
            data-testid="manuscript-add-node-btn"
            className="rounded-xl border border-border p-2 text-brand hover:border-brand"
            onClick={() => setAddNodeForm({ parentId: null, title: '', type: 'act' })}
            title={t('manuscript.addNode')}
          >
            <Plus size={14} />
          </button>
        </div>

        {/* Add node inline form */}
        {addNodeForm && (
          <form
            onSubmit={handleAddNodeSubmit}
            className="border-b border-border bg-bg-elev-2 px-3 py-2 flex flex-col gap-2 shrink-0"
          >
            <input
              autoFocus
              className="w-full rounded border border-border bg-bg px-2 py-1 text-[12px] text-text outline-none focus:border-brand"
              placeholder={t('manuscript.addNode')}
              value={addNodeForm.title}
              onChange={(e) => setAddNodeForm({ ...addNodeForm, title: e.target.value })}
            />
            <div className="flex items-center gap-2">
              <select
                className="flex-1 rounded border border-border bg-bg px-1 py-1 text-[11px] text-text outline-none"
                value={addNodeForm.type}
                onChange={(e) =>
                  setAddNodeForm({ ...addNodeForm, type: e.target.value as ManuscriptNodeType })
                }
              >
                {NODE_TYPE_ORDER.map((type) => (
                  <option key={type} value={type}>
                    {t(`manuscript.nodeType.${type}`)}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="rounded border border-brand px-2 py-1 text-[11px] text-brand hover:bg-brand hover:text-white"
              >
                {t('manuscript.addNode')}
              </button>
              <button
                type="button"
                className="rounded border border-border px-2 py-1 text-[11px] text-text-2 hover:bg-hover"
                onClick={() => setAddNodeForm(null)}
              >
                ✕
              </button>
            </div>
          </form>
        )}

        {/* Tree */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          {rootNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-4 py-12 text-center">
              <FileText size={28} className="text-text-2 mb-2 opacity-40" />
              <p className="text-[12px] text-text-2">{t('manuscript.empty')}</p>
            </div>
          ) : (
            rootNodes.map((node) => renderNode(node))
          )}
        </div>
      </aside>

      {/* Right pane — Editor */}
      <div className="flex-1 flex flex-col overflow-hidden" data-testid="manuscript-editor">
        {selectedNodeId ? (
          <>
            {/* Editor header */}
            <div className="border-b border-border bg-bg-elev-2 px-6 py-3 flex items-center justify-between shrink-0">
              <span className="text-[13px] font-semibold text-text truncate">
                {sortedNodes.find((n) => n.id === selectedNodeId)?.title || ''}
              </span>
              <span
                data-testid="manuscript-editor-wordcount"
                className="text-[11px] text-text-2 shrink-0 ml-4"
              >
                {wordCount.toLocaleString()} {t('manuscript.wordCount')}
              </span>
            </div>
            {/* Editor body */}
            <div className="flex-1 overflow-y-auto px-8 py-6">
              <NarrativeEditor
                key={selectedNodeId}
                content={editorContent}
                onUpdate={handleEditorUpdate}
                placeholder={t('manuscript.emptyEditor')}
              />
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full px-8 text-center">
            <FileText size={40} className="text-text-2 mb-3 opacity-30" />
            <p className="text-[14px] text-text-2">{t('manuscript.emptyEditor')}</p>
          </div>
        )}
      </div>
    </div>
  );
};

function stripHtml(content: string): string {
  if (content.includes('<')) {
    return content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  }
  return content;
}

function countWords(content: string): number {
  const text = stripHtml(content);
  if (!text) return 0;
  return text.split(/\s+/).filter(Boolean).length;
}
