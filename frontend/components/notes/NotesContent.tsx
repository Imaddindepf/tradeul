'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNotesStore, Note } from '@/stores/useNotesStore';
import {
  Plus,
  X,
  Bold,
  Italic,
  Underline,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Link2,
  Save,
  Trash2,
  FileText,
  Edit3,
  Check,
} from 'lucide-react';

// Toolbar button component
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
      className={`p-1.5 rounded transition-all duration-150 ${
        active
          ? 'bg-blue-500 text-white shadow-sm'
          : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
      }`}
    >
      {children}
    </button>
  );
}

// Note Tab component
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
      className={`group flex items-center gap-1 px-2 py-1 rounded-t-md border-b-2 transition-all duration-150 cursor-pointer min-w-0 max-w-[140px] ${
        isActive
          ? 'bg-white border-blue-500 text-slate-800'
          : 'bg-slate-50 border-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-700'
      }`}
      onClick={onSelect}
    >
      <FileText className="w-3 h-3 flex-shrink-0" />
      
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
        className="ml-auto opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 hover:text-red-600 transition-all duration-150"
      >
        <X className="w-2.5 h-2.5" />
      </button>
    </div>
  );
}

// Rich text editor using contentEditable
function RichTextEditor({
  content,
  onChange,
  placeholder,
}: {
  content: string;
  onChange: (content: string) => void;
  placeholder: string;
}) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [isEmpty, setIsEmpty] = useState(!content);

  // Initialize content
  useEffect(() => {
    if (editorRef.current && editorRef.current.innerHTML !== content) {
      editorRef.current.innerHTML = content;
      setIsEmpty(!content);
    }
  }, [content]);

  const handleInput = () => {
    if (editorRef.current) {
      const newContent = editorRef.current.innerHTML;
      const textContent = editorRef.current.textContent || '';
      setIsEmpty(!textContent.trim());
      onChange(newContent);
    }
  };

  const execCommand = useCallback((command: string, value?: string) => {
    document.execCommand(command, false, value);
    editorRef.current?.focus();
  }, []);

  const formatBlock = useCallback((tag: string) => {
    document.execCommand('formatBlock', false, tag);
    editorRef.current?.focus();
  }, []);

  const insertLink = useCallback(() => {
    const url = prompt('Enter URL:');
    if (url) {
      document.execCommand('createLink', false, url);
      editorRef.current?.focus();
    }
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-slate-200 bg-slate-50/80">
        <ToolbarButton onClick={() => execCommand('bold')} title="Bold (Ctrl+B)">
          <Bold className="w-3.5 h-3.5" />
        </ToolbarButton>
        <ToolbarButton onClick={() => execCommand('italic')} title="Italic (Ctrl+I)">
          <Italic className="w-3.5 h-3.5" />
        </ToolbarButton>
        <ToolbarButton onClick={() => execCommand('underline')} title="Underline (Ctrl+U)">
          <Underline className="w-3.5 h-3.5" />
        </ToolbarButton>
        
        <div className="w-px h-4 bg-slate-200 mx-1" />
        
        <ToolbarButton onClick={() => formatBlock('h1')} title="Heading 1">
          <Heading1 className="w-3.5 h-3.5" />
        </ToolbarButton>
        <ToolbarButton onClick={() => formatBlock('h2')} title="Heading 2">
          <Heading2 className="w-3.5 h-3.5" />
        </ToolbarButton>
        <ToolbarButton onClick={() => formatBlock('h3')} title="Heading 3">
          <Heading3 className="w-3.5 h-3.5" />
        </ToolbarButton>
        
        <div className="w-px h-4 bg-slate-200 mx-1" />
        
        <ToolbarButton onClick={() => execCommand('insertUnorderedList')} title="Bullet List">
          <List className="w-3.5 h-3.5" />
        </ToolbarButton>
        <ToolbarButton onClick={() => execCommand('insertOrderedList')} title="Numbered List">
          <ListOrdered className="w-3.5 h-3.5" />
        </ToolbarButton>
        
        <div className="w-px h-4 bg-slate-200 mx-1" />
        
        <ToolbarButton onClick={insertLink} title="Insert Link">
          <Link2 className="w-3.5 h-3.5" />
        </ToolbarButton>
      </div>

      {/* Editor */}
      <div className="flex-1 relative overflow-hidden">
        {isEmpty && (
          <div className="absolute inset-0 pointer-events-none p-3 text-slate-400 text-sm">
            {placeholder}
          </div>
        )}
        <div
          ref={editorRef}
          contentEditable
          onInput={handleInput}
          className="h-full overflow-y-auto p-3 text-sm text-slate-800 outline-none prose prose-sm max-w-none
                     [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mb-2 [&_h1]:mt-3
                     [&_h2]:text-base [&_h2]:font-semibold [&_h2]:mb-2 [&_h2]:mt-2
                     [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mb-1 [&_h3]:mt-2
                     [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1
                     [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1
                     [&_li]:my-0.5
                     [&_a]:text-blue-600 [&_a]:underline
                     [&_p]:my-1"
          suppressContentEditableWarning
        />
      </div>
    </div>
  );
}

// Empty state component
function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation();
  
  return (
    <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3 p-6">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 flex items-center justify-center">
        <FileText className="w-8 h-8 text-slate-400" />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-slate-600">{t('notes.noNotes')}</p>
        <p className="text-xs text-slate-400 mt-1">{t('notes.createFirst')}</p>
      </div>
      <button
        onClick={onCreate}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 text-white rounded-md text-xs font-medium hover:bg-blue-600 transition-colors shadow-sm"
      >
        <Plus className="w-3.5 h-3.5" />
        {t('notes.newNote')}
      </button>
    </div>
  );
}

// Main Notes Content component
export function NotesContent() {
  const { t } = useTranslation();
  const {
    notes,
    activeNoteId,
    createNote,
    updateNote,
    deleteNote,
    setActiveNote,
  } = useNotesStore();

  const activeNote = notes.find((n) => n.id === activeNoteId);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | null>(null);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Ref para el contenido actual (para guardar con Ctrl+S)
  const currentContentRef = useRef<string>('');

  // Auto-save with debounce
  const handleContentChange = useCallback(
    (content: string) => {
      currentContentRef.current = content;
      
      if (activeNoteId) {
        setSaveStatus('saving');
        
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
        }
        
        saveTimeoutRef.current = setTimeout(() => {
          updateNote(activeNoteId, { content });
          setSaveStatus('saved');
          
          setTimeout(() => setSaveStatus(null), 1500);
        }, 500);
      }
    },
    [activeNoteId, updateNote]
  );

  // Forzar guardado inmediato
  const forceSave = useCallback(() => {
    if (activeNoteId && currentContentRef.current) {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      updateNote(activeNoteId, { content: currentContentRef.current });
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus(null), 1500);
    }
  }, [activeNoteId, updateNote]);

  // Capturar Ctrl+S para prevenir el comportamiento del navegador
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        e.stopPropagation();
        forceSave();
      }
    };

    // Usar capture para interceptar antes que el navegador
    document.addEventListener('keydown', handleKeyDown, { capture: true });
    
    return () => {
      document.removeEventListener('keydown', handleKeyDown, { capture: true });
    };
  }, [forceSave]);

  const handleCreateNote = () => {
    createNote();
  };

  const handleDeleteNote = (id: string) => {
    if (notes.length === 1) {
      // Last note - just clear it
      updateNote(id, { content: '', title: 'Note 1' });
    } else {
      deleteNote(id);
    }
  };

  const handleRenameNote = (id: string, newTitle: string) => {
    updateNote(id, { title: newTitle });
  };

  // Set first note as active if none selected
  useEffect(() => {
    if (!activeNoteId && notes.length > 0) {
      setActiveNote(notes[0].id);
    }
  }, [activeNoteId, notes, setActiveNote]);

  return (
    <div className="h-full flex flex-col bg-white text-slate-900">
      {/* Header with tabs */}
      <div className="flex items-center border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
        {/* Tabs */}
        <div className="flex-1 flex items-end gap-0.5 px-2 pt-1.5 overflow-x-auto scrollbar-thin">
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
        <div className="flex items-center gap-1 px-2 py-1.5">
          {/* Save status indicator */}
          {saveStatus && (
            <div className={`flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded ${
              saveStatus === 'saved' 
                ? 'text-green-600 bg-green-50' 
                : 'text-slate-500 bg-slate-100'
            }`}>
              {saveStatus === 'saved' ? (
                <>
                  <Check className="w-2.5 h-2.5" />
                  <span>{t('notes.saved')}</span>
                </>
              ) : (
                <>
                  <Save className="w-2.5 h-2.5 animate-pulse" />
                  <span>{t('notes.saving')}</span>
                </>
              )}
            </div>
          )}
          
          {/* New note button */}
          <button
            onClick={handleCreateNote}
            className="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
            title={t('notes.newNote')}
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
          <RichTextEditor
            content={activeNote.content}
            onChange={handleContentChange}
            placeholder={t('notes.placeholder')}
          />
        ) : (
          <EmptyState onCreate={handleCreateNote} />
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-slate-100 bg-slate-50/50 text-[9px] text-slate-400">
        <span className="text-slate-400">{t('notes.autoSave')}</span>
        
        {activeNote && (
          <span className="text-slate-400">
            {new Date(activeNote.updatedAt).toLocaleString(undefined, {
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

