-- ============================================================================
-- News Alerts Preferences Migration
-- Añade preferencias de alertas de noticias a user_preferences
-- ============================================================================

-- Añadir columna news_alerts para guardar las preferencias de alertas
ALTER TABLE user_preferences 
ADD COLUMN IF NOT EXISTS news_alerts JSONB DEFAULT '{
    "enabled": false,
    "criteria": {
        "priceChange": {
            "enabled": true,
            "minPercent": 3,
            "timeWindow": 5
        },
        "rvol": {
            "enabled": false,
            "minValue": 2.5
        },
        "filters": {
            "onlyScanner": false,
            "onlyWatchlist": false
        }
    },
    "notifications": {
        "popup": true,
        "sound": true,
        "squawk": false
    }
}'::jsonb;

-- Comentario
COMMENT ON COLUMN user_preferences.news_alerts IS 'Preferencias de alertas de noticias (criterios, squawk, etc.)';

-- ============================================================================
-- Verificar que se aplicó correctamente
-- ============================================================================
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'user_preferences' AND column_name = 'news_alerts';


