'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Note {
  id: string;
  title: string;
  content: string;
  createdAt: number;
  updatedAt: number;
}

interface NotesState {
  notes: Note[];
  activeNoteId: string | null;
  
  // Actions
  createNote: () => string;
  updateNote: (id: string, updates: Partial<Pick<Note, 'title' | 'content'>>) => void;
  deleteNote: (id: string) => void;
  setActiveNote: (id: string | null) => void;
  getActiveNote: () => Note | null;
}

const generateNoteId = () => `note-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

export const useNotesStore = create<NotesState>()(
  persist(
    (set, get) => ({
      notes: [],
      activeNoteId: null,

      createNote: () => {
        const id = generateNoteId();
        const now = Date.now();
        const existingNotes = get().notes;
        
        // Generate a unique title
        let titleNumber = existingNotes.length + 1;
        let title = `Note ${titleNumber}`;
        while (existingNotes.some(n => n.title === title)) {
          titleNumber++;
          title = `Note ${titleNumber}`;
        }

        const newNote: Note = {
          id,
          title,
          content: '',
          createdAt: now,
          updatedAt: now,
        };

        set((state) => ({
          notes: [...state.notes, newNote],
          activeNoteId: id,
        }));

        return id;
      },

      updateNote: (id, updates) => {
        set((state) => ({
          notes: state.notes.map((note) =>
            note.id === id
              ? { ...note, ...updates, updatedAt: Date.now() }
              : note
          ),
        }));
      },

      deleteNote: (id) => {
        set((state) => {
          const newNotes = state.notes.filter((note) => note.id !== id);
          const wasActive = state.activeNoteId === id;
          
          return {
            notes: newNotes,
            activeNoteId: wasActive
              ? (newNotes.length > 0 ? newNotes[0].id : null)
              : state.activeNoteId,
          };
        });
      },

      setActiveNote: (id) => {
        set({ activeNoteId: id });
      },

      getActiveNote: () => {
        const state = get();
        return state.notes.find((note) => note.id === state.activeNoteId) || null;
      },
    }),
    {
      name: 'tradeul-notes-storage',
      version: 1,
    }
  )
);







