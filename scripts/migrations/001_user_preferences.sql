-- ============================================================================
-- User Preferences Migration
-- Tabla para almacenar preferencias de usuario (colores, fuentes, layouts)
-- ============================================================================

-- Crear tabla de preferencias de usuario
CREATE TABLE IF NOT EXISTS user_preferences (
    -- ID único (UUID de Clerk)
    user_id VARCHAR(255) PRIMARY KEY,
    
    -- Preferencias de colores (JSONB para flexibilidad)
    colors JSONB DEFAULT '{
        "tickUp": "#10b981",
        "tickDown": "#ef4444",
        "background": "#ffffff",
        "primary": "#3b82f6"
    }'::jsonb,
    
    -- Preferencias de tema
    theme JSONB DEFAULT '{
        "font": "jetbrains-mono",
        "colorScheme": "light"
    }'::jsonb,
    
    -- Layout de ventanas (posiciones, tamaños)
    window_layouts JSONB DEFAULT '[]'::jsonb,
    
    -- Filtros guardados por lista
    saved_filters JSONB DEFAULT '{}'::jsonb,
    
    -- Visibilidad de columnas por lista
    column_visibility JSONB DEFAULT '{}'::jsonb,
    
    -- Orden de columnas por lista  
    column_order JSONB DEFAULT '{}'::jsonb,
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para búsquedas rápidas por user_id (ya es PK, pero explícito)
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);

-- Función para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_user_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para auto-actualizar updated_at
DROP TRIGGER IF EXISTS trigger_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER trigger_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_user_preferences_updated_at();

-- Comentarios para documentación
COMMENT ON TABLE user_preferences IS 'Preferencias de usuario persistentes (colores, fuentes, layouts)';
COMMENT ON COLUMN user_preferences.user_id IS 'ID del usuario de Clerk';
COMMENT ON COLUMN user_preferences.colors IS 'Colores personalizados (tickUp, tickDown, background, primary)';
COMMENT ON COLUMN user_preferences.theme IS 'Configuración de tema (font, colorScheme)';
COMMENT ON COLUMN user_preferences.window_layouts IS 'Posiciones y tamaños de ventanas flotantes';
COMMENT ON COLUMN user_preferences.saved_filters IS 'Filtros guardados por lista del scanner';
COMMENT ON COLUMN user_preferences.column_visibility IS 'Visibilidad de columnas por lista';
COMMENT ON COLUMN user_preferences.column_order IS 'Orden de columnas por lista';


