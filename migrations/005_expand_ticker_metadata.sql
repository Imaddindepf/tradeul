-- =============================================
-- MIGRACIÓN: Expandir ticker_metadata con campos completos de Polygon
-- =============================================
-- Versión: 005
-- Fecha: 2025-11-12
-- Descripción: Agregar campos adicionales de Polygon API para metadata rica
-- =============================================

-- =============================================
-- AGREGAR NUEVAS COLUMNAS
-- =============================================

-- Información de la Compañía
ALTER TABLE ticker_metadata 
ADD COLUMN IF NOT EXISTS description TEXT,
ADD COLUMN IF NOT EXISTS homepage_url VARCHAR(500),
ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50),
ADD COLUMN IF NOT EXISTS address JSONB,
ADD COLUMN IF NOT EXISTS total_employees INTEGER,
ADD COLUMN IF NOT EXISTS list_date DATE;

-- Branding
ALTER TABLE ticker_metadata
ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500),
ADD COLUMN IF NOT EXISTS icon_url VARCHAR(500);

-- Identificadores
ALTER TABLE ticker_metadata
ADD COLUMN IF NOT EXISTS cik VARCHAR(20),
ADD COLUMN IF NOT EXISTS composite_figi VARCHAR(20),
ADD COLUMN IF NOT EXISTS share_class_figi VARCHAR(20),
ADD COLUMN IF NOT EXISTS ticker_root VARCHAR(10),
ADD COLUMN IF NOT EXISTS ticker_suffix VARCHAR(10);

-- Detalles del Activo
ALTER TABLE ticker_metadata
ADD COLUMN IF NOT EXISTS type VARCHAR(10),
ADD COLUMN IF NOT EXISTS currency_name VARCHAR(10),
ADD COLUMN IF NOT EXISTS locale VARCHAR(10),
ADD COLUMN IF NOT EXISTS market VARCHAR(20),
ADD COLUMN IF NOT EXISTS round_lot INTEGER,
ADD COLUMN IF NOT EXISTS delisted_utc TIMESTAMPTZ;

-- =============================================
-- CREAR ÍNDICES PARA NUEVOS CAMPOS
-- =============================================

-- Índice para búsqueda por tipo
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_type 
ON ticker_metadata (type);

-- Índice para búsqueda por locale
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_locale 
ON ticker_metadata (locale);

-- Índice para búsqueda por market
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_market 
ON ticker_metadata (market);

-- Índice para búsqueda de delisted (solo activos)
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_delisted 
ON ticker_metadata (delisted_utc) 
WHERE delisted_utc IS NULL;

-- Índice GIN para búsqueda de texto completo en descripción
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_description_fts
ON ticker_metadata USING GIN (to_tsvector('english', COALESCE(description, '')));

-- Índice para address JSONB (búsqueda por ciudad, estado)
CREATE INDEX IF NOT EXISTS idx_ticker_metadata_address_gin
ON ticker_metadata USING GIN (address);

-- =============================================
-- COMENTARIOS EN COLUMNAS
-- =============================================

COMMENT ON COLUMN ticker_metadata.description IS 'Descripción larga de la compañía y sus operaciones';
COMMENT ON COLUMN ticker_metadata.homepage_url IS 'URL del sitio web oficial';
COMMENT ON COLUMN ticker_metadata.phone_number IS 'Número de teléfono de la compañía';
COMMENT ON COLUMN ticker_metadata.address IS 'Dirección de la sede central (JSONB: address1, city, state, postal_code)';
COMMENT ON COLUMN ticker_metadata.total_employees IS 'Número aproximado de empleados';
COMMENT ON COLUMN ticker_metadata.list_date IS 'Fecha de salida a bolsa (IPO)';
COMMENT ON COLUMN ticker_metadata.logo_url IS 'URL del logo de la compañía';
COMMENT ON COLUMN ticker_metadata.icon_url IS 'URL del icono de la compañía';
COMMENT ON COLUMN ticker_metadata.cik IS 'Central Index Key (SEC)';
COMMENT ON COLUMN ticker_metadata.composite_figi IS 'Composite OpenFIGI identifier';
COMMENT ON COLUMN ticker_metadata.share_class_figi IS 'Share Class OpenFIGI identifier';
COMMENT ON COLUMN ticker_metadata.ticker_root IS 'Raíz del ticker (ej: BRK de BRK.A)';
COMMENT ON COLUMN ticker_metadata.ticker_suffix IS 'Sufijo del ticker (ej: A de BRK.A)';
COMMENT ON COLUMN ticker_metadata.type IS 'Tipo de activo (CS, ETF, ADRC, etc)';
COMMENT ON COLUMN ticker_metadata.currency_name IS 'Moneda de cotización';
COMMENT ON COLUMN ticker_metadata.locale IS 'Localización del activo (us, global)';
COMMENT ON COLUMN ticker_metadata.market IS 'Tipo de mercado (stocks, crypto, fx, otc, indices)';
COMMENT ON COLUMN ticker_metadata.round_lot IS 'Tamaño del lote estándar';
COMMENT ON COLUMN ticker_metadata.delisted_utc IS 'Fecha de exclusión de cotización (NULL si activo)';

-- =============================================
-- ESTADÍSTICAS DE TABLA
-- =============================================

-- Forzar análisis de tabla para actualizar estadísticas
ANALYZE ticker_metadata;

-- =============================================
-- VERIFICACIÓN
-- =============================================

-- Mostrar esquema completo de la tabla
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'ticker_metadata'
ORDER BY ordinal_position;

