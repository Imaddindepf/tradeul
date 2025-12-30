/**
 * Notes Window Injector
 * 
 * Standalone window for personal notes
 */

import { getUserTimezoneForWindow, getUserFontForWindow, getFontConfig, WindowConfig } from './base';

// ============================================================
// NOTES WINDOW
// ============================================================

export interface NotesNote {
  id: string;
  title: string;
  content: string;
  createdAt: number;
  updatedAt: number;
}

export interface NotesWindowData {
  notes: NotesNote[];
  activeNoteId: string | null;
}

export function openNotesWindow(
  data: NotesWindowData,
  config: WindowConfig
): Window | null {
  const {
    width = 600,
    height = 550,
    centered = true,
  } = config;

  const left = centered ? (window.screen.width - width) / 2 : 100;
  const top = centered ? (window.screen.height - height) / 2 : 100;

  const windowFeatures = [
    `width=${width}`,
    `height=${height}`,
    `left=${left}`,
    `top=${top}`,
    'resizable=yes',
    'scrollbars=yes',
    'status=yes',
  ].join(',');

  const newWindow = window.open('about:blank', '_blank', windowFeatures);

  if (!newWindow) {
    console.error('❌ Notes window blocked');
    return null;
  }

  injectNotesContent(newWindow, data, config);

  return newWindow;
}

function injectNotesContent(
  targetWindow: Window,
  data: NotesWindowData,
  config: WindowConfig
): void {
  const { title } = config;
  const userTimezone = getUserTimezoneForWindow();
  const userFont = getUserFontForWindow();
  const fontConfig = getFontConfig(userFont);

  const htmlContent = `
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=${fontConfig.googleFont}&display=swap" rel="stylesheet">
  
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: [${fontConfig.cssFamily}]
          },
          colors: {
            background: '#FFFFFF',
            foreground: '#0F172A',
            primary: { DEFAULT: '#2563EB', hover: '#1D4ED8' },
            border: '#E2E8F0',
            muted: '#F8FAFC',
            success: '#10B981',
            danger: '#EF4444'
          }
        }
      }
    }
  </script>
  
  <style>
    * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; box-sizing: border-box; }
    body { font-family: 'Inter', sans-serif; color: #0F172A; background: #ffffff; margin: 0; font-size: 14px; }
    .font-mono { font-family: ${fontConfig.cssFamily} !important; }
    *::-webkit-scrollbar { width: 6px; height: 6px; }
    *::-webkit-scrollbar-track { background: #F8FAFC; }
    *::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
    *::-webkit-scrollbar-thumb:hover { background: #2563EB; }
    
    .note-tab { transition: all 0.15s; }
    .note-tab:hover { background-color: #F1F5F9; }
    .note-tab.active { background-color: white; border-bottom-color: #2563EB; color: #1E293B; }
    
    .toolbar-btn { transition: all 0.15s; }
    .toolbar-btn:hover { background-color: #F1F5F9; color: #1E293B; }
    .toolbar-btn.active { background-color: #2563EB; color: white; }
    
    #editor { outline: none; min-height: 100%; }
    #editor h1 { font-size: 1.125rem; font-weight: 700; margin: 0.75rem 0 0.5rem; }
    #editor h2 { font-size: 1rem; font-weight: 600; margin: 0.5rem 0 0.5rem; }
    #editor h3 { font-size: 0.875rem; font-weight: 600; margin: 0.5rem 0 0.25rem; }
    #editor ul { list-style-type: disc; padding-left: 1.25rem; margin: 0.25rem 0; }
    #editor ol { list-style-type: decimal; padding-left: 1.25rem; margin: 0.25rem 0; }
    #editor li { margin: 0.125rem 0; }
    #editor a { color: #2563EB; text-decoration: underline; }
    #editor p { margin: 0.25rem 0; }
  </style>
</head>
<body class="bg-white overflow-hidden">
  <div id="root" class="h-screen flex flex-col">
    <!-- Header with tabs -->
    <div class="flex items-center border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
      <!-- Tabs container -->
      <div id="tabs-container" class="flex-1 flex items-end gap-0.5 px-2 pt-1.5 overflow-x-auto">
        <!-- Tabs will be rendered here -->
      </div>
      
      <!-- Actions -->
      <div class="flex items-center gap-1 px-2 py-1.5">
        <!-- Save status -->
        <div id="save-status" class="hidden items-center gap-1 text-[9px] px-1.5 py-0.5 rounded"></div>
        
        <!-- New note button -->
        <button id="btn-new-note" class="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors" title="Nueva Nota">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
          </svg>
        </button>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-0.5 px-2 py-1.5 border-b border-slate-200 bg-slate-50/80">
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="bold" title="Bold (Ctrl+B)">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
          <path d="M6 4h8a4 4 0 014 4 4 4 0 01-4 4H6V4zM6 12h9a4 4 0 014 4 4 4 0 01-4 4H6v-8z"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="italic" title="Italic (Ctrl+I)">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M19 4h-9M14 20H5M15 4L9 20"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="underline" title="Underline (Ctrl+U)">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M6 3v7a6 6 0 006 6 6 6 0 006-6V3M4 21h16"></path>
        </svg>
      </button>
      
      <div class="w-px h-4 bg-slate-200 mx-1"></div>
      
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-block="h1" title="Heading 1">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M4 12h8M4 6v12M12 6v12M17 12l3-2v8"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-block="h2" title="Heading 2">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M4 12h8M4 6v12M12 6v12M17 10c.7-.5 1.5-.8 2.3-.8 1 0 2 .5 2.5 1.3.5.8.5 1.7 0 2.5s-1.5 1.3-2.5 1.3H17v2h5"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-block="h3" title="Heading 3">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M4 12h8M4 6v12M12 6v12M17.5 10.5c1-.7 2.5-.5 3.3.5s.5 2.5-.5 3.3M17.5 17.5c1 .7 2.5.5 3.3-.5s.5-2.5-.5-3.3"></path>
        </svg>
      </button>
      
      <div class="w-px h-4 bg-slate-200 mx-1"></div>
      
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="insertUnorderedList" title="Bullet List">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"></path>
        </svg>
      </button>
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-cmd="insertOrderedList" title="Numbered List">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M10 6h11M10 12h11M10 18h11M4 6h1v4M4 10h2M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"></path>
        </svg>
      </button>
      
      <div class="w-px h-4 bg-slate-200 mx-1"></div>
      
      <button class="toolbar-btn p-1.5 rounded text-slate-500" data-action="link" title="Insert Link">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
          <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"></path>
        </svg>
      </button>
    </div>

    <!-- Editor container -->
    <div class="flex-1 relative overflow-hidden">
      <div id="placeholder" class="absolute inset-0 pointer-events-none p-3 text-slate-400 text-sm">
        Escribe algo...
      </div>
      <div id="editor" contenteditable="true" class="h-full overflow-y-auto p-3 text-sm text-slate-800"></div>
    </div>

    <!-- Footer -->
    <div class="flex items-center justify-between px-3 py-1.5 border-t border-slate-100 bg-slate-50/50 text-[9px] text-slate-400">
      <span>Auto-guardado activo</span>
      <span id="last-updated"></span>
    </div>
  </div>

  <script>
    // ============================================================
    // STATE
    // ============================================================
    const STORAGE_KEY = 'tradeul-notes-storage';
    const USER_TIMEZONE = '${userTimezone}';
    let notes = ${JSON.stringify(data.notes)};
    let activeNoteId = ${JSON.stringify(data.activeNoteId)};
    let saveTimeout = null;
    
    console.log('📝 [Notes] Init with', notes.length, 'notes');
    
    // ============================================================
    // PERSISTENCE
    // ============================================================
    function loadFromStorage() {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed.state) {
            notes = parsed.state.notes || [];
            activeNoteId = parsed.state.activeNoteId || null;
          }
        }
      } catch (e) {
        console.error('[Notes] Load error:', e);
      }
    }
    
    function saveToStorage() {
      try {
        const data = {
          state: { notes, activeNoteId },
          version: 1
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      } catch (e) {
        console.error('[Notes] Save error:', e);
      }
    }
    
    // ============================================================
    // NOTES MANAGEMENT
    // ============================================================
    function generateId() {
      return 'note-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }
    
    function getActiveNote() {
      return notes.find(n => n.id === activeNoteId) || null;
    }
    
    function createNote() {
      const id = generateId();
      const now = Date.now();
      let titleNum = notes.length + 1;
      let title = 'Note ' + titleNum;
      while (notes.some(n => n.title === title)) {
        titleNum++;
        title = 'Note ' + titleNum;
      }
      
      const newNote = { id, title, content: '', createdAt: now, updatedAt: now };
      notes.push(newNote);
      activeNoteId = id;
      saveToStorage();
      render();
    }
    
    function deleteNote(id) {
      if (notes.length === 1) {
        // Last note - just clear it
        notes[0].content = '';
        notes[0].title = 'Note 1';
        notes[0].updatedAt = Date.now();
      } else {
        const idx = notes.findIndex(n => n.id === id);
        notes.splice(idx, 1);
        if (activeNoteId === id) {
          activeNoteId = notes[0]?.id || null;
        }
      }
      saveToStorage();
      render();
    }
    
    function selectNote(id) {
      activeNoteId = id;
      saveToStorage();
      render();
    }
    
    function updateNoteContent(content) {
      const note = getActiveNote();
      if (note) {
        note.content = content;
        note.updatedAt = Date.now();
        showSaveStatus('saving');
        
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
          saveToStorage();
          showSaveStatus('saved');
          updateLastModified();
        }, 500);
      }
    }
    
    function renameNote(id, newTitle) {
      const note = notes.find(n => n.id === id);
      if (note && newTitle.trim()) {
        note.title = newTitle.trim();
        note.updatedAt = Date.now();
        saveToStorage();
        render();
      }
    }
    
    // ============================================================
    // UI HELPERS
    // ============================================================
    function showSaveStatus(status) {
      const el = document.getElementById('save-status');
      el.classList.remove('hidden');
      el.classList.add('flex');
      
      if (status === 'saved') {
        el.className = 'flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded text-green-600 bg-green-50';
        el.innerHTML = '<svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg><span>Guardado</span>';
        setTimeout(() => { el.classList.add('hidden'); el.classList.remove('flex'); }, 1500);
      } else {
        el.className = 'flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded text-slate-500 bg-slate-100';
        el.innerHTML = '<svg class="w-2.5 h-2.5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path></svg><span>Guardando...</span>';
      }
    }
    
    function updateLastModified() {
      const note = getActiveNote();
      if (note) {
        const date = new Date(note.updatedAt);
        document.getElementById('last-updated').textContent = date.toLocaleString('en-US', {
          timeZone: USER_TIMEZONE, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
      }
    }
    
    function updatePlaceholder() {
      const editor = document.getElementById('editor');
      const placeholder = document.getElementById('placeholder');
      const isEmpty = !editor.textContent.trim();
      placeholder.style.display = isEmpty ? 'block' : 'none';
    }
    
    // ============================================================
    // RENDER
    // ============================================================
    function renderTabs() {
      const container = document.getElementById('tabs-container');
      container.innerHTML = notes.map(note => {
        const isActive = note.id === activeNoteId;
        return \`
          <div class="note-tab group flex items-center gap-1 px-2 py-1 rounded-t-md border-b-2 cursor-pointer min-w-0 max-w-[140px] \${isActive ? 'active bg-white border-blue-500 text-slate-800' : 'bg-slate-50 border-transparent text-slate-500 hover:text-slate-700'}" data-id="\${note.id}">
            <svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            <span class="tab-title text-[10px] font-medium truncate">\${escapeHtml(note.title)}</span>
            <button class="btn-close ml-auto opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 hover:text-red-600 transition-all" data-delete="\${note.id}">
              <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
          </div>
        \`;
      }).join('');
      
      // Add click handlers
      container.querySelectorAll('.note-tab').forEach(tab => {
        const id = tab.dataset.id;
        tab.addEventListener('click', (e) => {
          if (!e.target.closest('.btn-close')) {
            selectNote(id);
          }
        });
        
        // Double click to rename
        const titleEl = tab.querySelector('.tab-title');
        titleEl.addEventListener('dblclick', (e) => {
          e.stopPropagation();
          const note = notes.find(n => n.id === id);
          if (note) {
            const input = document.createElement('input');
            input.type = 'text';
            input.value = note.title;
            input.className = 'w-full text-[10px] font-medium bg-transparent border-none outline-none px-0';
            titleEl.replaceWith(input);
            input.focus();
            input.select();
            
            const finish = () => {
              renameNote(id, input.value);
            };
            input.addEventListener('blur', finish);
            input.addEventListener('keydown', (e) => {
              if (e.key === 'Enter') finish();
              if (e.key === 'Escape') { input.value = note.title; finish(); }
            });
          }
        });
      });
      
      container.querySelectorAll('.btn-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          deleteNote(btn.dataset.delete);
        });
      });
    }
    
    function renderEditor() {
      const editor = document.getElementById('editor');
      const note = getActiveNote();
      
      if (note) {
        editor.innerHTML = note.content;
      } else {
        editor.innerHTML = '';
      }
      updatePlaceholder();
      updateLastModified();
    }
    
    function render() {
      renderTabs();
      renderEditor();
    }
    
    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
    
    // ============================================================
    // EVENT HANDLERS
    // ============================================================
    function setupEventHandlers() {
      const editor = document.getElementById('editor');
      
      // Editor input
      editor.addEventListener('input', () => {
        updateNoteContent(editor.innerHTML);
        updatePlaceholder();
      });
      
      // New note button
      document.getElementById('btn-new-note').addEventListener('click', createNote);
      
      // Toolbar buttons
      document.querySelectorAll('.toolbar-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const cmd = btn.dataset.cmd;
          const block = btn.dataset.block;
          const action = btn.dataset.action;
          
          if (cmd) {
            document.execCommand(cmd, false);
            editor.focus();
          } else if (block) {
            document.execCommand('formatBlock', false, block);
            editor.focus();
          } else if (action === 'link') {
            const url = prompt('Introduce la URL:');
            if (url) {
              document.execCommand('createLink', false, url);
              editor.focus();
            }
          }
        });
      });
      
      // Keyboard shortcuts
      document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          // Force save
          const note = getActiveNote();
          if (note) {
            clearTimeout(saveTimeout);
            saveToStorage();
            showSaveStatus('saved');
            updateLastModified();
          }
        }
      });
    }
    
    // ============================================================
    // INIT
    // ============================================================
    function init() {
      // Load fresh from storage (in case it was updated)
      loadFromStorage();
      
      // Create first note if none exist
      if (notes.length === 0) {
        const id = generateId();
        const now = Date.now();
        notes.push({ id, title: 'Note 1', content: '', createdAt: now, updatedAt: now });
        activeNoteId = id;
        saveToStorage();
      }
      
      // Set active note if not set
      if (!activeNoteId && notes.length > 0) {
        activeNoteId = notes[0].id;
      }
      
      render();
      setupEventHandlers();
    }
    
    init();
    console.log('✅ [Notes] Initialized');
  </script>
</body>
</html>
  `;

  targetWindow.document.open();
  targetWindow.document.write(htmlContent);
  targetWindow.document.close();

  console.log('✅ [WindowInjector] Notes injected');
}

