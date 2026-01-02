'use client';

/**
 * WorkspaceTabs - Barra inferior de workspaces estilo GODEL/IBKR
 * 
 * Diseño compacto que se adapta al texto
 * - Usa la fuente configurada por el usuario
 * - Sin iconos, solo texto
 * - Ancho de tabs adaptable al contenido
 * - Double-click para renombrar
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { Z_INDEX } from '@/lib/z-index';

interface WorkspaceTabsProps {
  /** Función para obtener el contenido de una ventana por título */
  getWindowContent: (title: string) => React.ReactNode;
}

// Mapeo de fuentes a font-family CSS
const FONT_FAMILIES: Record<string, string> = {
  'oxygen-mono': '"Oxygen Mono", monospace',
  'ibm-plex-mono': '"IBM Plex Mono", monospace',
  'jetbrains-mono': '"JetBrains Mono", monospace',
  'fira-code': '"Fira Code", monospace',
};

export function WorkspaceTabs({ getWindowContent }: WorkspaceTabsProps) {
  const { t } = useTranslation();
  const {
    workspaces,
    activeWorkspaceId,
    createWorkspace,
    deleteWorkspace,
    renameWorkspace,
    switchWorkspace,
    isMainWorkspace,
  } = useWorkspaces();

  // Obtener la fuente del usuario
  const userFont = useUserPreferencesStore((s) => s.theme.font);
  const fontFamily = FONT_FAMILIES[userFont] || FONT_FAMILIES['jetbrains-mono'];

  // Estado para edición de nombre
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input cuando entramos en modo edición
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  /**
   * Iniciar edición de nombre (double-click)
   */
  const handleStartEdit = useCallback((workspaceId: string, currentName: string) => {
    // No permitir editar Main
    if (isMainWorkspace(workspaceId)) return;
    setEditingId(workspaceId);
    setEditValue(currentName);
  }, [isMainWorkspace]);

  /**
   * Confirmar edición de nombre
   */
  const handleConfirmEdit = useCallback(() => {
    if (editingId && editValue.trim()) {
      renameWorkspace(editingId, editValue.trim());
    }
    setEditingId(null);
    setEditValue('');
  }, [editingId, editValue, renameWorkspace]);

  /**
   * Cancelar edición
   */
  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    setEditValue('');
  }, []);

  /**
   * Crear nuevo workspace
   */
  const handleCreateWorkspace = useCallback(() => {
    const baseName = t('workspace.newWorkspace', 'New Workspace');
    // Encontrar número disponible
    let counter = 1;
    let name = baseName;
    while (workspaces.some(w => w.name === name)) {
      counter++;
      name = `${baseName} ${counter}`;
    }
    const newId = createWorkspace(name);
    // Cambiar al nuevo workspace
    switchWorkspace(newId, getWindowContent);
  }, [t, workspaces, createWorkspace, switchWorkspace, getWindowContent]);

  /**
   * Eliminar workspace
   */
  const handleDeleteWorkspace = useCallback((e: React.MouseEvent, workspaceId: string) => {
    e.stopPropagation();
    if (isMainWorkspace(workspaceId)) return;
    
    // Si estamos eliminando el workspace activo, cambiar a Main primero
    if (workspaceId === activeWorkspaceId) {
      switchWorkspace('main', getWindowContent);
    }
    
    // Pequeño delay para que el switch termine
    setTimeout(() => {
      deleteWorkspace(workspaceId);
    }, 100);
  }, [isMainWorkspace, activeWorkspaceId, switchWorkspace, deleteWorkspace, getWindowContent]);

  /**
   * Cambiar workspace
   */
  const handleSwitchWorkspace = useCallback((workspaceId: string) => {
    if (editingId) return; // No cambiar mientras editamos
    switchWorkspace(workspaceId, getWindowContent);
  }, [editingId, switchWorkspace, getWindowContent]);

  return (
    <div 
      className="fixed bottom-0 left-0 right-0 h-7 bg-white border-t border-slate-200 flex items-center select-none"
      style={{ zIndex: Z_INDEX.WORKSPACE_TABS, fontFamily }}
    >
      {/* Tabs */}
      <div className="flex items-center h-full overflow-x-auto scrollbar-hide">
        {workspaces.map((workspace) => {
          const isActive = workspace.id === activeWorkspaceId;
          const isMain = workspace.isMain;
          const isEditing = editingId === workspace.id;

          return (
            <div
              key={workspace.id}
              onClick={() => handleSwitchWorkspace(workspace.id)}
              onDoubleClick={() => handleStartEdit(workspace.id, workspace.name)}
              className={`
                group relative flex items-center h-full cursor-pointer
                border-r border-slate-200 transition-colors duration-100
                ${isActive 
                  ? 'bg-blue-50 text-blue-700' 
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
                }
              `}
              style={{ padding: '0 10px' }}
            >
              {/* Indicador de activo */}
              {isActive && (
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-blue-500" />
              )}

              {/* Nombre del workspace */}
              {isEditing ? (
                <input
                  ref={inputRef}
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={handleConfirmEdit}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleConfirmEdit();
                    if (e.key === 'Escape') handleCancelEdit();
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="px-1 py-0.5 text-xs bg-white text-slate-800 
                           border border-blue-500 rounded outline-none"
                  style={{ fontFamily, width: `${Math.max(editValue.length, 5) * 8}px` }}
                  maxLength={30}
                />
              ) : (
                <span 
                  className="text-xs whitespace-nowrap"
                  style={{ fontFamily }}
                >
                  {workspace.name}
                </span>
              )}

              {/* Botón cerrar (solo para no-Main) - texto x */}
              {!isMain && !isEditing && (
                <button
                  onClick={(e) => handleDeleteWorkspace(e, workspace.id)}
                  className="ml-2 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 
                           transition-opacity text-xs leading-none"
                  title={t('workspace.close', 'Close workspace')}
                  style={{ fontFamily }}
                >
                  ×
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Botón crear nuevo workspace - texto + */}
      <button
        onClick={handleCreateWorkspace}
        className="flex items-center justify-center px-3 h-full 
                 text-slate-400 hover:text-blue-600 hover:bg-slate-50
                 transition-colors border-l border-slate-200 text-sm"
        title={t('workspace.create', 'Create new workspace')}
        style={{ fontFamily }}
      >
        +
      </button>

      {/* Spacer derecho */}
      <div className="flex-1" />
    </div>
  );
}
