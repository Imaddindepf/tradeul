'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNotesStore, Note, TipTapContent } from '@/stores/useNotesStore';
import { useUser } from '@clerk/nextjs';
import { getUserTimezone } from '@/lib/date-utils';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Placeholder from '@tiptap/extension-placeholder';
import { List, ListOrdered, Plus, Link2 } from 'lucide-react';

// Toolbar button - minimal, no icons
function ToolbarButton({
  onClick,
  active,
  children,
  title,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`px-1.5 py-0.5 rounded text-[10px] font-medium transition-all duration-150 ${active
          ? 'bg-slate-700 text-white'
          : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
        }`}
    >
      {children}
    </button>
  );
}

// Note Tab component - minimal
function NoteTab({
  note,
  isActive,
  onSelect,
  onClose,
  onRename,
}: {
  note: Note;
  isActive: boolean;
  onSelect: () => void;
  onClose: () => void;
  onRename: (newTitle: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(note.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSubmit = () => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== note.title) {
      onRename(trimmed);
    } else {
      setEditTitle(note.title);
    }
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSubmit();
    } else if (e.key === 'Escape') {
      setEditTitle(note.title);
      setIsEditing(false);
    }
  };

  return (
    <div
      className={`group flex items-center gap-1 px-2 py-1 rounded-t border-b-2 transition-all duration-150 cursor-pointer min-w-0 max-w-[120px] ${isActive
          ? 'bg-white border-slate-700 text-slate-800'
          : 'bg-slate-50 border-transparent text-slate-400 hover:bg-slate-100 hover:text-slate-600'
        }`}
      onClick={onSelect}
    >
      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={handleSubmit}
          onKeyDown={handleKeyDown}
          onClick={(e) => e.stopPropagation()}
          className="w-full text-[10px] font-medium bg-transparent border-none outline-none px-0"
        />
      ) : (
        <span
          className="text-[10px] font-medium truncate"
          onDoubleClick={(e) => {
            e.stopPropagation();
            setIsEditing(true);
          }}
        >
          {note.title}
        </span>
      )}

      <button
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        className="ml-auto opacity-0 group-hover:opacity-100 text-[10px] text-slate-400 hover:text-red-500 transition-all duration-150"
      >
        ×
      </button>
    </div>
  );
}

// TipTap Editor component
function TipTapEditor({
  content,
  onChange,
  placeholder,
}: {
  content: TipTapContent;
  onChange: (content: TipTapContent) => void;
  placeholder: string;
}) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: 'text-blue-600 underline cursor-pointer' },
      }),
      Placeholder.configure({ placeholder }),
    ],
    content,
    editorProps: {
      attributes: {
        class: 'h-full outline-none prose prose-sm max-w-none p-3 text-slate-800 ' +
          '[&_h1]:text-base [&_h1]:font-bold [&_h1]:mb-2 [&_h1]:mt-2 ' +
          '[&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mb-1 [&_h2]:mt-2 ' +
          '[&_h3]:text-xs [&_h3]:font-semibold [&_h3]:mb-1 [&_h3]:mt-1 ' +
          '[&_ul]:list-disc [&_ul]:pl-4 [&_ul]:my-1 ' +
          '[&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:my-1 ' +
          '[&_li]:my-0.5 [&_p]:my-1 ' +
          '[&_.is-editor-empty:first-child::before]:text-slate-400 ' +
          '[&_.is-editor-empty:first-child::before]:content-[attr(data-placeholder)] ' +
          '[&_.is-editor-empty:first-child::before]:float-left [&_.is-editor-empty:first-child::before]:h-0 ' +
          '[&_.is-editor-empty:first-child::before]:pointer-events-none',
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getJSON() as TipTapContent);
    },
  });

  // Update content when it changes externally
  useEffect(() => {
    if (editor && content) {
      const currentContent = JSON.stringify(editor.getJSON());
      const newContent = JSON.stringify(content);
      if (currentContent !== newContent) {
        editor.commands.setContent(content);
      }
    }
  }, [editor, content]);

  if (!editor) return null;

  const insertLink = () => {
    const url = prompt('Enter URL:');
    if (url) {
      editor.chain().focus().setLink({ href: url }).run();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-slate-200 bg-slate-50/50">
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBold().run()}
          active={editor.isActive('bold')}
          title="Bold"
        >
          B
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleItalic().run()}
          active={editor.isActive('italic')}
          title="Italic"
        >
          I
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleStrike().run()}
          active={editor.isActive('strike')}
          title="Strikethrough"
        >
          S̶
        </ToolbarButton>

        <div className="w-px h-4 bg-slate-200 mx-1" />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          active={editor.isActive('heading', { level: 1 })}
          title="Heading 1"
        >
          H1
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          active={editor.isActive('heading', { level: 2 })}
          title="Heading 2"
        >
          H2
        </ToolbarButton>

        <div className="w-px h-4 bg-slate-200 mx-1" />

        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          active={editor.isActive('bulletList')}
          title="Bullet List"
        >
          <List className="w-3.5 h-3.5" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          active={editor.isActive('orderedList')}
          title="Numbered List"
        >
          <ListOrdered className="w-3.5 h-3.5" />
        </ToolbarButton>

        <div className="w-px h-4 bg-slate-200 mx-1" />

        <ToolbarButton
          onClick={insertLink}
          active={editor.isActive('link')}
          title="Insert Link"
        >
          <Link2 className="w-3.5 h-3.5" />
        </ToolbarButton>
      </div>

      {/* Editor area */}
      <div className="flex-1 overflow-y-auto">
        <EditorContent editor={editor} className="h-full" />
      </div>
    </div>
  );
}

// Empty state
function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation();

  return (
    <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3 p-6">
      <p className="text-xs text-slate-500">{t('notes.noNotes', 'No notes yet')}</p>
      <button
        onClick={onCreate}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded transition-colors"
      >
        <Plus className="w-3.5 h-3.5" />
        {t('notes.newNote', 'New note')}
      </button>
    </div>
  );
}

// Main Notes Content component
export function NotesContent() {
  const { t } = useTranslation();
  const { user, isLoaded } = useUser();
  const {
    notes,
    activeNoteId,
    isLoading,
    fetchNotes,
    createNote,
    updateNote,
    deleteNote,
    setActiveNote,
    createLocalNote,
    updateLocalNote,
    deleteLocalNote,
  } = useNotesStore();

  const activeNote = notes.find((n) => n.id === activeNoteId);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | null>(null);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const currentContentRef = useRef<TipTapContent | null>(null);

  // Fetch notes on mount if user is logged in
  useEffect(() => {
    if (isLoaded && user?.id) {
      fetchNotes(user.id);
    }
  }, [isLoaded, user?.id, fetchNotes]);

  // Set first note as active if none selected
  useEffect(() => {
    if (!activeNoteId && notes.length > 0) {
      setActiveNote(notes[0].id);
    }
  }, [activeNoteId, notes, setActiveNote]);

  const handleContentChange = useCallback(
    (content: TipTapContent) => {
      currentContentRef.current = content;

      if (activeNoteId) {
        setSaveStatus('saving');

        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
        }

        saveTimeoutRef.current = setTimeout(() => {
          if (user?.id) {
            updateNote(activeNoteId, { content }, user.id);
          } else {
            updateLocalNote(activeNoteId, { content });
          }
          setSaveStatus('saved');
          setTimeout(() => setSaveStatus(null), 1500);
        }, 500);
      }
    },
    [activeNoteId, user?.id, updateNote, updateLocalNote]
  );

  const forceSave = useCallback(() => {
    if (activeNoteId && currentContentRef.current) {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      if (user?.id) {
        updateNote(activeNoteId, { content: currentContentRef.current }, user.id);
      } else {
        updateLocalNote(activeNoteId, { content: currentContentRef.current });
      }
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus(null), 1500);
    }
  }, [activeNoteId, user?.id, updateNote, updateLocalNote]);

  // Ctrl+S handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        e.stopPropagation();
        forceSave();
      }
    };

    document.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => document.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, [forceSave]);

  const handleCreateNote = async () => {
    if (user?.id) {
      await createNote(user.id);
    } else {
      createLocalNote();
    }
  };

  const handleDeleteNote = async (id: string) => {
    if (notes.length === 1) {
      // Last note - just clear it
      const emptyContent: TipTapContent = { type: 'doc', content: [] };
      if (user?.id) {
        await updateNote(id, { content: emptyContent, title: 'Note 1' }, user.id);
      } else {
        updateLocalNote(id, { content: emptyContent, title: 'Note 1' });
      }
    } else {
      if (user?.id) {
        await deleteNote(id, user.id);
      } else {
        deleteLocalNote(id);
      }
    }
  };

  const handleRenameNote = async (id: string, newTitle: string) => {
    if (user?.id) {
      await updateNote(id, { title: newTitle }, user.id);
    } else {
      updateLocalNote(id, { title: newTitle });
    }
  };

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 text-xs">
        Loading...
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white text-slate-900">
      {/* Header with tabs */}
      <div className="flex items-center border-b border-slate-200 bg-slate-50/50">
        {/* Tabs */}
        <div className="flex-1 flex items-end gap-0.5 px-1 pt-1 overflow-x-auto scrollbar-thin">
          {notes.map((note) => (
            <NoteTab
              key={note.id}
              note={note}
              isActive={note.id === activeNoteId}
              onSelect={() => setActiveNote(note.id)}
              onClose={() => handleDeleteNote(note.id)}
              onRename={(title) => handleRenameNote(note.id, title)}
            />
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 px-2 py-1">
          {saveStatus && (
            <span className={`text-[9px] ${saveStatus === 'saved' ? 'text-green-600' : 'text-slate-400'}`}>
              {saveStatus === 'saved' ? '✓' : '...'}
            </span>
          )}

          <button
            onClick={handleCreateNote}
            className="p-1 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
            title={t('notes.newNote', 'New note')}
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {notes.length === 0 ? (
          <EmptyState onCreate={handleCreateNote} />
        ) : activeNote ? (
          <TipTapEditor
            content={activeNote.content}
            onChange={handleContentChange}
            placeholder={t('notes.placeholder', 'Start writing...')}
          />
        ) : (
          <EmptyState onCreate={handleCreateNote} />
        )}
      </div>

      {/* Footer - minimal */}
      <div className="flex items-center justify-between px-2 py-1 border-t border-slate-100 bg-slate-50/30 text-[9px] text-slate-400">
        <span>{user?.id ? 'synced' : 'local'}</span>
        {activeNote && (
          <span>
            {new Date(activeNote.updated_at).toLocaleString('en-US', {
              timeZone: getUserTimezone(),
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        )}
      </div>
    </div>
  );
}

export default NotesContent;
