import React, { useEffect } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import CharacterCount from '@tiptap/extension-character-count';
import Placeholder from '@tiptap/extension-placeholder';
import { Bold, Italic, Strikethrough, List, ListOrdered, Heading1, Heading2, Heading3, Minus } from 'lucide-react';
import { cn } from '../../utils';

interface NarrativeEditorProps {
  content: string;
  onUpdate: (html: string) => void;
  placeholder?: string;
  className?: string;
  mono?: boolean; // for script editor
  testId?: string;
}

export const NarrativeEditor: React.FC<NarrativeEditorProps> = ({
  content,
  onUpdate,
  placeholder = 'Start writing...',
  className,
  mono = false,
  testId,
}) => {
  const editor = useEditor({
    extensions: [
      StarterKit,
      CharacterCount,
      Placeholder.configure({ placeholder }),
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
          title="Bold"
        >
          <Bold size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleItalic().run()}
          active={editor.isActive('italic')}
          title="Italic"
        >
          <Italic size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleStrike().run()}
          active={editor.isActive('strike')}
          title="Strike"
        >
          <Strikethrough size={13} />
        </ToolbarBtn>
        <div className="mx-1 h-4 w-px bg-border" />
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          active={editor.isActive('heading', { level: 1 })}
          title="H1"
        >
          <Heading1 size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          active={editor.isActive('heading', { level: 2 })}
          title="H2"
        >
          <Heading2 size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          active={editor.isActive('heading', { level: 3 })}
          title="H3"
        >
          <Heading3 size={13} />
        </ToolbarBtn>
        <div className="mx-1 h-4 w-px bg-border" />
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          active={editor.isActive('bulletList')}
          title="Bullet List"
        >
          <List size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          active={editor.isActive('orderedList')}
          title="Ordered List"
        >
          <ListOrdered size={13} />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().setHorizontalRule().run()}
          active={false}
          title="Divider"
        >
          <Minus size={13} />
        </ToolbarBtn>
        <div className="ml-auto text-[10px] font-medium text-text-3">
          {wordCount} words · {charCount} chars
        </div>
      </div>
      {/* Editor */}
      <EditorContent editor={editor} />
    </div>
  );
};

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
