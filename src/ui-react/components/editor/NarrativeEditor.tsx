import React, { useEffect, useImperativeHandle } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import CharacterCount from '@tiptap/extension-character-count';
import Placeholder from '@tiptap/extension-placeholder';
import { Mark, mergeAttributes } from '@tiptap/core';
import { Plugin } from 'prosemirror-state';
import { Bold, Italic, Strikethrough, List, ListOrdered, Heading1, Heading2, Heading3, Minus } from 'lucide-react';
import { cn } from '../../utils';
import { useProjectStore } from '../../store';
import { useI18n } from '../../i18n';

// ── Narrative annotation marks ─────────────────────────────────────────────────

interface NarrativeMarkAttrs {
  entityId: string;
  entityType: 'character' | 'location' | 'item' | 'todo';
  conflictDetail?: string;
}

function makeNarrativeMark(
  name: string,
  colorClass: string,
  extraAttrs?: Record<string, { default: string | null }>,
) {
  return Mark.create({
    name,
    addAttributes() {
      return {
        entityId: { default: null },
        entityType: { default: null },
        conflictDetail: { default: null },
        ...extraAttrs,
      };
    },
    parseHTML() {
      return [{ tag: `span[data-mark-type="${name}"]` }];
    },
    renderHTML({ HTMLAttributes }) {
      return [
        'span',
        mergeAttributes(HTMLAttributes, {
          'data-mark-type': name,
          class: colorClass,
          ...(HTMLAttributes.conflictDetail ? { title: HTMLAttributes.conflictDetail } : {}),
        }),
        0,
      ];
    },
    addProseMirrorPlugins() {
      return [
        new Plugin({
          props: {
            handleClick(view, pos) {
              const { state } = view;
              const $pos = state.doc.resolve(pos);
              const marks = $pos.marks();
              for (const mark of marks) {
                if (mark.type.name === name) {
                  const { entityType, entityId } = mark.attrs as NarrativeMarkAttrs;
                  if (entityType && entityId) {
                    useProjectStore.getState().focusEntity(entityType, entityId);
                    return true;
                  }
                }
              }
              return false;
            },
          },
        }),
      ];
    },
  });
}

const CharacterKnownMark = makeNarrativeMark(
  'character_known',
  'underline decoration-blue-400 cursor-pointer',
);

const LocationKnownMark = makeNarrativeMark(
  'location_known',
  'underline decoration-green-400 cursor-pointer',
);

const TodoMarkerMark = makeNarrativeMark(
  'todo_marker',
  'underline decoration-orange-400 cursor-pointer',
);

const ConflictMarkerMark = makeNarrativeMark(
  'conflict_marker',
  'underline decoration-red-400 cursor-pointer',
);

export interface NarrativeEditorHandle {
  insertAtCursor: (text: string) => void;
}

interface NarrativeEditorProps {
  content: string;
  onUpdate: (html: string) => void;
  placeholder?: string;
  className?: string;
  mono?: boolean; // for script editor
  testId?: string;
}

export const NarrativeEditor = React.forwardRef<NarrativeEditorHandle, NarrativeEditorProps>(({
  content,
  onUpdate,
  placeholder: placeholderProp = 'Start writing...',
  className,
  mono = false,
  testId,
}, ref) => {
  const { t } = useI18n();
  const editor = useEditor({
    extensions: [
      StarterKit,
      CharacterCount,
      Placeholder.configure({ placeholder: placeholderProp }),
      CharacterKnownMark,
      LocationKnownMark,
      TodoMarkerMark,
      ConflictMarkerMark,
    ],
    content: content.startsWith('<') ? content : content ? `<p>${content.replace(/\n/g, '</p><p>')}</p>` : '',
    onUpdate: ({ editor }) => {
      onUpdate(editor.getHTML());
    },
    editorProps: {
      attributes: {
        class: cn(
          'min-h-[640px] w-full outline-none leading-[1.95] text-text-2',
          mono ? 'font-mono text-sm' : 'font-serif text-xl',
        ),
        ...(testId ? { 'data-testid': testId } : {}),
      },
    },
  });

  useImperativeHandle(ref, () => ({
    insertAtCursor: (text: string) => {
      if (!editor) return;
      editor.chain().focus().insertContent(text).run();
    },
  }), [editor]);

  // Sync external content changes (e.g., when switching scenes)
  useEffect(() => {
    if (!editor) return;
    const newContent = content.startsWith('<') ? content : content ? `<p>${content.replace(/\n/g, '</p><p>')}</p>` : '';
    if (editor.getHTML() !== newContent) {
      editor.commands.setContent(newContent, { emitUpdate: false });
    }
  }, [content]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!editor) return null;

  const wordCount = editor.storage.characterCount?.words() ?? 0;
  const charCount = editor.storage.characterCount?.characters() ?? 0;

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Toolbar */}
      <div className="mb-3 flex flex-wrap items-center gap-1 rounded-2xl border border-border bg-bg-elev-1 px-3 py-2">
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleBold().run()}
          active={editor.isActive('bold')}
          title={t('editor.bold', 'Bold')}
        >
          <Bold size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleItalic().run()}
          active={editor.isActive('italic')}
          title={t('editor.italic', 'Italic')}
        >
          <Italic size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleStrike().run()}
          active={editor.isActive('strike')}
          title={t('editor.strike', 'Strike')}
        >
          <Strikethrough size={13} />
        </ToolbarBtn>
        <div className="mx-1 h-4 w-px bg-border" />
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          active={editor.isActive('heading', { level: 1 })}
          title={t('editor.h1', 'H1')}
        >
          <Heading1 size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          active={editor.isActive('heading', { level: 2 })}
          title={t('editor.h2', 'H2')}
        >
          <Heading2 size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          active={editor.isActive('heading', { level: 3 })}
          title={t('editor.h3', 'H3')}
        >
          <Heading3 size={13} />
        </ToolbarBtn>
        <div className="mx-1 h-4 w-px bg-border" />
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          active={editor.isActive('bulletList')}
          title={t('editor.bulletList', 'Bullet List')}
        >
          <List size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          active={editor.isActive('orderedList')}
          title={t('editor.orderedList', 'Ordered List')}
        >
          <ListOrdered size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().setHorizontalRule().run()}
          active={false}
          title={t('editor.divider', 'Divider')}
        >
          <Minus size={13} />
        </ToolbarBtn>
        <div className="ml-auto text-[10px] font-medium text-text-3">
          {t('editor.wordCount', `${wordCount} words · ${charCount} chars`).replace('{words}', String(wordCount)).replace('{chars}', String(charCount))}
        </div>
      </div>
      {/* Editor */}
      <EditorContent editor={editor} />
    </div>
  );
});

NarrativeEditor.displayName = 'NarrativeEditor';

const ToolbarBtn: React.FC<{ onClick: () => void; active: boolean; title: string; children: React.ReactNode }> = ({
  onClick, active, title, children,
}) => (
  <button
    type="button"
    title={title}
    onClick={onClick}
    className={cn(
      'rounded-lg p-1.5 text-text-2 transition-colors hover:bg-hover',
      active ? 'bg-selected text-text' : '',
    )}
  >
    {children}
  </button>
);
