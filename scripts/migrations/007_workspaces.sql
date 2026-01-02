-- ============================================================================
-- WORKSPACES Migration
-- Añade soporte para múltiples workspaces (estilo GODEL/IBKR)
-- Migration: 007_workspaces.sql
-- ============================================================================

-- Agregar columna workspaces a user_preferences
ALTER TABLE user_preferences 
ADD COLUMN IF NOT EXISTS workspaces JSONB DEFAULT '[{
    "id": "main",
    "name": "Main",
    "isMain": true,
    "windowLayouts": [],
    "createdAt": 0
}]'::jsonb;

-- Agregar columna active_workspace_id
ALTER TABLE user_preferences 
ADD COLUMN IF NOT EXISTS active_workspace_id VARCHAR(100) DEFAULT 'main';

-- Comentarios
COMMENT ON COLUMN user_preferences.workspaces IS 'Array de workspaces, cada uno con su propio layout de ventanas';
COMMENT ON COLUMN user_preferences.active_workspace_id IS 'ID del workspace activo actualmente';

-- Migrar datos existentes: Si hay window_layouts, moverlos al workspace Main
UPDATE user_preferences
SET workspaces = jsonb_build_array(
    jsonb_build_object(
        'id', 'main',
        'name', 'Main',
        'isMain', true,
        'windowLayouts', COALESCE(window_layouts, '[]'::jsonb),
        'createdAt', EXTRACT(EPOCH FROM created_at) * 1000
    )
)
WHERE window_layouts IS NOT NULL 
  AND jsonb_array_length(window_layouts) > 0
  AND (workspaces IS NULL OR workspaces = '[{"id":"main","name":"Main","isMain":true,"windowLayouts":[],"createdAt":0}]'::jsonb);

-- Índice para búsqueda por active_workspace_id (opcional)
CREATE INDEX IF NOT EXISTS idx_user_preferences_active_workspace ON user_preferences(active_workspace_id);

-- ============================================================================
-- Verificación
-- ============================================================================
-- SELECT user_id, active_workspace_id, jsonb_array_length(workspaces) as workspace_count 
-- FROM user_preferences LIMIT 10;

