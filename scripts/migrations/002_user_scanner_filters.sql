-- ============================================================================
-- User Scanner Filters Migration
-- Tabla para almacenar filtros personalizados del scanner por usuario
-- ============================================================================

-- Crear tabla de filtros de usuario para el scanner
CREATE TABLE IF NOT EXISTS user_scanner_filters (
    -- ID único
    id SERIAL PRIMARY KEY,
    
    -- ID del usuario (UUID de Clerk)
    user_id VARCHAR(255) NOT NULL,
    
    -- Nombre del filtro (único por usuario)
    name VARCHAR(100) NOT NULL,
    
    -- Descripción opcional
    description TEXT,
    
    -- Estado del filtro
    enabled BOOLEAN DEFAULT true,
    
    -- Tipo de filtro (rvol, price, volume, custom, etc.)
    filter_type VARCHAR(50) NOT NULL,
    
    -- Parámetros del filtro (JSONB - mismo formato que FilterParameters)
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Prioridad (mayor = se aplica primero)
    priority INTEGER DEFAULT 0,
    
    -- Compartir con otros usuarios (opcional, futuro)
    is_shared BOOLEAN DEFAULT false,
    
    -- Filtro público en marketplace (opcional, futuro)
    is_public BOOLEAN DEFAULT false,
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraint: nombre único por usuario
    CONSTRAINT unique_user_filter_name UNIQUE(user_id, name)
);

-- Índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_user_scanner_filters_user_id ON user_scanner_filters(user_id);
CREATE INDEX IF NOT EXISTS idx_user_scanner_filters_enabled ON user_scanner_filters(user_id, enabled) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS idx_user_scanner_filters_shared ON user_scanner_filters(is_shared, is_public) WHERE is_shared = true OR is_public = true;
CREATE INDEX IF NOT EXISTS idx_user_scanner_filters_type ON user_scanner_filters(filter_type);

-- Función para actualizar updated_at automáticamente (reutilizar si existe)
CREATE OR REPLACE FUNCTION update_user_scanner_filters_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para auto-actualizar updated_at
DROP TRIGGER IF EXISTS trigger_user_scanner_filters_updated_at ON user_scanner_filters;
CREATE TRIGGER trigger_user_scanner_filters_updated_at
    BEFORE UPDATE ON user_scanner_filters
    FOR EACH ROW
    EXECUTE FUNCTION update_user_scanner_filters_updated_at();

-- Comentarios para documentación
COMMENT ON TABLE user_scanner_filters IS 'Filtros personalizados del scanner por usuario';
COMMENT ON COLUMN user_scanner_filters.user_id IS 'ID del usuario de Clerk';
COMMENT ON COLUMN user_scanner_filters.name IS 'Nombre del filtro (único por usuario)';
COMMENT ON COLUMN user_scanner_filters.filter_type IS 'Tipo de filtro: rvol, price, volume, custom, etc.';
COMMENT ON COLUMN user_scanner_filters.parameters IS 'Parámetros del filtro en formato JSONB (FilterParameters)';
COMMENT ON COLUMN user_scanner_filters.priority IS 'Prioridad de aplicación (mayor = primero)';
COMMENT ON COLUMN user_scanner_filters.is_shared IS 'Si el filtro está compartido con otros usuarios';
COMMENT ON COLUMN user_scanner_filters.is_public IS 'Si el filtro es público en marketplace';

