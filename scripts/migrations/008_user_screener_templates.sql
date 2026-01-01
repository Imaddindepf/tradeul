-- ============================================================================
-- User Screener Templates Migration
-- Plantillas personalizadas del Screener por usuario
-- ============================================================================

-- Crear tabla de plantillas del screener
CREATE TABLE IF NOT EXISTS user_screener_templates (
    -- ID único
    id SERIAL PRIMARY KEY,
    
    -- ID del usuario (UUID de Clerk)
    user_id VARCHAR(255) NOT NULL,
    
    -- Nombre de la plantilla (único por usuario)
    name VARCHAR(100) NOT NULL,
    
    -- Descripción opcional
    description TEXT,
    
    -- ========== CONFIGURACIÓN DEL SCREENER ==========
    
    -- Filtros con parámetros dinámicos
    -- Ejemplo: [{"field": "sma", "params": {"period": 10}, "operator": ">", "value": null, "compare_field": "sma", "compare_params": {"period": 50}}]
    filters JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Ordenación
    sort_by VARCHAR(50) DEFAULT 'relative_volume',
    sort_order VARCHAR(10) DEFAULT 'desc',
    
    -- Límite de resultados
    limit_results INTEGER DEFAULT 50,
    
    -- ========== METADATA ==========
    
    -- Favorito (aparece primero)
    is_favorite BOOLEAN DEFAULT false,
    
    -- Color/icono para identificación visual
    color VARCHAR(20),
    icon VARCHAR(50),
    
    -- Estadísticas de uso
    use_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    
    -- Compartir
    is_shared BOOLEAN DEFAULT false,
    is_public BOOLEAN DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraint: nombre único por usuario
    CONSTRAINT unique_user_template_name UNIQUE(user_id, name)
);

-- Índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_user_screener_templates_user_id 
    ON user_screener_templates(user_id);

CREATE INDEX IF NOT EXISTS idx_user_screener_templates_favorite 
    ON user_screener_templates(user_id, is_favorite) 
    WHERE is_favorite = true;

CREATE INDEX IF NOT EXISTS idx_user_screener_templates_public 
    ON user_screener_templates(is_public) 
    WHERE is_public = true;

CREATE INDEX IF NOT EXISTS idx_user_screener_templates_last_used 
    ON user_screener_templates(user_id, last_used_at DESC);

-- Función para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_user_screener_templates_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para auto-actualizar updated_at
DROP TRIGGER IF EXISTS trigger_user_screener_templates_updated_at ON user_screener_templates;
CREATE TRIGGER trigger_user_screener_templates_updated_at
    BEFORE UPDATE ON user_screener_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_user_screener_templates_updated_at();

-- ============================================================================
-- Tabla de Indicadores Personalizados (para referencia rápida)
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_custom_indicators (
    -- ID único
    id SERIAL PRIMARY KEY,
    
    -- ID del usuario
    user_id VARCHAR(255) NOT NULL,
    
    -- Nombre del indicador personalizado
    name VARCHAR(100) NOT NULL,
    
    -- Tipo base del indicador
    indicator_type VARCHAR(50) NOT NULL,  -- sma, ema, rsi, atr, bb, keltner, macd, etc.
    
    -- Parámetros del indicador
    -- Ejemplo: {"period": 10} o {"fast": 12, "slow": 26, "signal": 9}
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Alias para usar en filtros (ej: "sma_10", "rsi_7")
    alias VARCHAR(50) NOT NULL,
    
    -- Descripción
    description TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_user_indicator_alias UNIQUE(user_id, alias),
    CONSTRAINT unique_user_indicator_name UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_user_custom_indicators_user_id 
    ON user_custom_indicators(user_id);

-- ============================================================================
-- Comentarios de documentación
-- ============================================================================

COMMENT ON TABLE user_screener_templates IS 'Plantillas completas del Screener guardadas por usuario';
COMMENT ON COLUMN user_screener_templates.filters IS 'Array de filtros con parámetros dinámicos en formato JSONB';
COMMENT ON COLUMN user_screener_templates.sort_by IS 'Campo por el cual ordenar resultados';
COMMENT ON COLUMN user_screener_templates.is_favorite IS 'Plantillas favoritas aparecen primero';

COMMENT ON TABLE user_custom_indicators IS 'Indicadores personalizados definidos por usuario';
COMMENT ON COLUMN user_custom_indicators.indicator_type IS 'Tipo base: sma, ema, rsi, atr, bb, keltner, macd, stoch, vol_avg';
COMMENT ON COLUMN user_custom_indicators.params IS 'Parámetros del indicador (period, multiplier, etc.)';
COMMENT ON COLUMN user_custom_indicators.alias IS 'Alias único para usar en filtros (ej: sma_10)';

