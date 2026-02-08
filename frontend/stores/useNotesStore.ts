'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// ProseMirror/TipTap document type
export interface TipTapContent {
  type: 'doc';
  content: any[];
}

export interface Note {
  id: string;
  user_id?: string;
  title: string;
  content: TipTapContent;
  content_text?: string;
  position: number;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

interface NotesState {
  notes: Note[];
  activeNoteId: string | null;
  isLoading: boolean;
  isSynced: boolean;
  error: string | null;

  // Actions
  fetchNotes: (userId: string) => Promise<void>;
  createNote: (userId: string) => Promise<string | null>;
  updateNote: (noteId: string, updates: Partial<Pick<Note, 'title' | 'content'>>, userId: string) => Promise<void>;
  deleteNote: (noteId: string, userId: string) => Promise<void>;
  setActiveNote: (id: string | null) => void;
  getActiveNote: () => Note | null;

  // Local fallback actions (when not logged in)
  createLocalNote: () => string;
  updateLocalNote: (id: string, updates: Partial<Pick<Note, 'title' | 'content'>>) => void;
  deleteLocalNote: (id: string) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

const generateNoteId = () => `local-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

const emptyContent: TipTapContent = { type: 'doc', content: [] };

export const useNotesStore = create<NotesState>()(
  persist(
    (set, get) => ({
      notes: [],
      activeNoteId: null,
      isLoading: false,
      isSynced: false,
      error: null,

      fetchNotes: async (userId: string) => {
        set({ isLoading: true, error: null });

        try {
          const res = await fetch(`${API_BASE}/api/v1/notes?user_id=${encodeURIComponent(userId)}`);

          if (!res.ok) {
            throw new Error(`Failed to fetch notes: ${res.status}`);
          }

          const notes: Note[] = await res.json();

          set({
            notes,
            isLoading: false,
            isSynced: true,
            activeNoteId: notes.length > 0 ? (get().activeNoteId || notes[0].id) : null
          });
        } catch (error) {
          console.error('Failed to fetch notes:', error);
          set({ isLoading: false, error: (error as Error).message });
        }
      },

      createNote: async (userId: string) => {
        const existingNotes = get().notes;
        let titleNumber = existingNotes.length + 1;
        let title = `Note ${titleNumber}`;
        while (existingNotes.some(n => n.title === title)) {
          titleNumber++;
          title = `Note ${titleNumber}`;
        }

        try {
          const res = await fetch(`${API_BASE}/api/v1/notes?user_id=${encodeURIComponent(userId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, content: emptyContent })
          });

          if (!res.ok) {
            throw new Error(`Failed to create note: ${res.status}`);
          }

          const newNote: Note = await res.json();

          set((state) => ({
            notes: [...state.notes, newNote],
            activeNoteId: newNote.id
          }));

          return newNote.id;
        } catch (error) {
          console.error('Failed to create note:', error);
          // Fallback to local
          return get().createLocalNote();
        }
      },

      updateNote: async (noteId: string, updates: Partial<Pick<Note, 'title' | 'content'>>, userId: string) => {
        // Optimistic update
        set((state) => ({
          notes: state.notes.map((note) =>
            note.id === noteId
              ? { ...note, ...updates, updated_at: new Date().toISOString() }
              : note
          )
        }));

        // If local note, don't sync
        if (noteId.startsWith('local-')) {
          return;
        }

        try {
          const res = await fetch(`${API_BASE}/api/v1/notes/${noteId}?user_id=${encodeURIComponent(userId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
          });

          if (!res.ok) {
            throw new Error(`Failed to update note: ${res.status}`);
          }
        } catch (error) {
          console.error('Failed to update note:', error);
        }
      },

      deleteNote: async (noteId: string, userId: string) => {
        const state = get();
        const newNotes = state.notes.filter((note) => note.id !== noteId);
        const wasActive = state.activeNoteId === noteId;

        set({
          notes: newNotes,
          activeNoteId: wasActive
            ? (newNotes.length > 0 ? newNotes[0].id : null)
            : state.activeNoteId
        });

        // If local note, don't sync
        if (noteId.startsWith('local-')) {
          return;
        }

        try {
          await fetch(`${API_BASE}/api/v1/notes/${noteId}?user_id=${encodeURIComponent(userId)}`, {
            method: 'DELETE'
          });
        } catch (error) {
          console.error('Failed to delete note:', error);
        }
      },

      setActiveNote: (id) => {
        set({ activeNoteId: id });
      },

      getActiveNote: () => {
        const state = get();
        return state.notes.find((note) => note.id === state.activeNoteId) || null;
      },

      // Local fallback methods
      createLocalNote: () => {
        const id = generateNoteId();
        const now = new Date().toISOString();
        const existingNotes = get().notes;

        let titleNumber = existingNotes.length + 1;
        let title = `Note ${titleNumber}`;
        while (existingNotes.some(n => n.title === title)) {
          titleNumber++;
          title = `Note ${titleNumber}`;
        }

        const newNote: Note = {
          id,
          title,
          content: emptyContent,
          position: existingNotes.length,
          is_pinned: false,
          created_at: now,
          updated_at: now
        };

        set((state) => ({
          notes: [...state.notes, newNote],
          activeNoteId: id
        }));

        return id;
      },

      updateLocalNote: (id, updates) => {
        set((state) => ({
          notes: state.notes.map((note) =>
            note.id === id
              ? { ...note, ...updates, updated_at: new Date().toISOString() }
              : note
          )
        }));
      },

      deleteLocalNote: (id) => {
        set((state) => {
          const newNotes = state.notes.filter((note) => note.id !== id);
          const wasActive = state.activeNoteId === id;

          return {
            notes: newNotes,
            activeNoteId: wasActive
              ? (newNotes.length > 0 ? newNotes[0].id : null)
              : state.activeNoteId
          };
        });
      }
    }),
    {
      name: 'tradeul-notes-storage',
      version: 2,
      partialize: (state) => ({
        notes: state.notes.filter(n => n.id.startsWith('local-')), // Only persist local notes
        activeNoteId: state.activeNoteId
      })
    }
  )
);
