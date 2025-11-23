-- =====================================================
-- SEC Filings Database Schema
-- =====================================================
-- Sistema de almacenamiento para filings de la SEC
-- Soporta real-time (Stream API) e histórico (Query API)
-- =====================================================

-- Tabla principal de SEC filings
CREATE TABLE IF NOT EXISTS sec_filings (
    -- ==========================================
    -- IDENTIFICADORES
    -- ==========================================
    id TEXT PRIMARY KEY,                    -- UUID del sistema SEC (único por filing + entity)
    accession_no TEXT NOT NULL,             -- Número de acceso SEC (e.g., 0001628280-24-041816)
    
    -- ==========================================
    -- METADATA BÁSICA
    -- ==========================================
    form_type TEXT NOT NULL,                -- Tipo de formulario (e.g., "8-K", "10-K", "4", "13F")
    filed_at TIMESTAMPTZ NOT NULL,          -- Fecha y hora de filing (ISO 8601)
    ticker TEXT,                            -- Símbolo del ticker (puede ser NULL para no-públicas)
    cik TEXT NOT NULL,                      -- Central Index Key (sin leading zeros)
    company_name TEXT,                      -- Nombre de la empresa
    company_name_long TEXT,                 -- Nombre largo con tipo de filer
    period_of_report DATE,                  -- Período del reporte (fiscal period end)
    description TEXT,                       -- Descripción del formulario
    
    -- ==========================================
    -- ITEMS Y CLASIFICACIONES
    -- ==========================================
    items TEXT[],                           -- Array de items (e.g., ["Item 1.03", "Item 9.01"])
    group_members TEXT[],                   -- Miembros del grupo (para 13D/13G)
    
    -- ==========================================
    -- ENLACES A DOCUMENTOS
    -- ==========================================
    link_to_filing_details TEXT,            -- URL al contenido del filing en SEC.gov
    link_to_txt TEXT,                       -- URL al archivo .TXT completo
    link_to_html TEXT,                      -- URL a la página índice del filing
    link_to_xbrl TEXT,                      -- URL a archivos XBRL (si aplica)
    
    -- ==========================================
    -- FECHAS ESPECIALES (para ciertos form types)
    -- ==========================================
    effectiveness_date DATE,                -- Fecha de efectividad (EFFECT, 18-K, TA-1)
    effectiveness_time TIME,                -- Hora de efectividad (EFFECT)
    registration_form TEXT,                 -- Tipo de formulario de registro (EFFECT)
    reference_accession_no TEXT,            -- Número de acceso de referencia (EFFECT)
    
    -- ==========================================
    -- DATOS COMPLEJOS (JSON/JSONB)
    -- ==========================================
    entities JSONB,                         -- Array de entidades referenciadas en el filing
    document_format_files JSONB,            -- Array de archivos del filing (primarios + exhibits)
    data_files JSONB,                       -- Array de archivos XBRL
    series_and_classes_contracts JSONB,     -- Series y clases/contratos (fondos)
    
    -- ==========================================
    -- TIMESTAMPS DEL SISTEMA
    -- ==========================================
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================================================
-- ÍNDICES PARA PERFORMANCE
-- =====================================================

-- Índice único por accession_no para evitar duplicados
CREATE UNIQUE INDEX IF NOT EXISTS idx_sec_filings_accession_no 
ON sec_filings(accession_no);

-- Índice por ticker (más común en búsquedas)
CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker 
ON sec_filings(ticker) 
WHERE ticker IS NOT NULL;

-- Índice por form_type
CREATE INDEX IF NOT EXISTS idx_sec_filings_form_type 
ON sec_filings(form_type);

-- Índice por fecha de filing (DESC para últimos primero)
CREATE INDEX IF NOT EXISTS idx_sec_filings_filed_at 
ON sec_filings(filed_at DESC);

-- Índice por CIK
CREATE INDEX IF NOT EXISTS idx_sec_filings_cik 
ON sec_filings(cik);

-- Índice GIN para búsquedas en array de items
CREATE INDEX IF NOT EXISTS idx_sec_filings_items 
ON sec_filings USING GIN(items);

-- Índice compuesto para búsquedas por ticker + fecha
CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker_date 
ON sec_filings(ticker, filed_at DESC) 
WHERE ticker IS NOT NULL;

-- Índice compuesto para búsquedas por form_type + fecha
CREATE INDEX IF NOT EXISTS idx_sec_filings_form_date 
ON sec_filings(form_type, filed_at DESC);

-- Índice para búsquedas por ticker + form_type + fecha
CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker_form_date 
ON sec_filings(ticker, form_type, filed_at DESC) 
WHERE ticker IS NOT NULL;

-- =====================================================
-- TRIGGER PARA UPDATED_AT
-- =====================================================

CREATE OR REPLACE FUNCTION update_sec_filings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_sec_filings_updated_at ON sec_filings;

CREATE TRIGGER trigger_update_sec_filings_updated_at
    BEFORE UPDATE ON sec_filings
    FOR EACH ROW
    EXECUTE FUNCTION update_sec_filings_updated_at();

-- =====================================================
-- VISTAS ÚTILES
-- =====================================================

-- Vista de últimos filings (más comunes)
CREATE OR REPLACE VIEW sec_filings_recent AS
SELECT 
    id,
    accession_no,
    form_type,
    filed_at,
    ticker,
    cik,
    company_name,
    items,
    link_to_filing_details,
    period_of_report
FROM sec_filings
WHERE filed_at >= NOW() - INTERVAL '30 days'
ORDER BY filed_at DESC;

-- Vista de filings 8-K con bancarrota (Item 1.03)
CREATE OR REPLACE VIEW sec_filings_bankruptcies AS
SELECT 
    id,
    accession_no,
    filed_at,
    ticker,
    company_name,
    items,
    link_to_filing_details
FROM sec_filings
WHERE form_type LIKE '8-K%'
  AND '1.03' = ANY(items)
ORDER BY filed_at DESC;

-- Vista de filings Form 4 (insider trading)
CREATE OR REPLACE VIEW sec_filings_insider_trading AS
SELECT 
    id,
    accession_no,
    filed_at,
    ticker,
    company_name,
    period_of_report,
    link_to_filing_details,
    entities
FROM sec_filings
WHERE form_type = '4'
ORDER BY filed_at DESC;

-- =====================================================
-- COMENTARIOS DE DOCUMENTACIÓN
-- =====================================================

COMMENT ON TABLE sec_filings IS 'Almacena metadata de todos los filings de la SEC (real-time + histórico)';
COMMENT ON COLUMN sec_filings.id IS 'UUID único del sistema SEC (puede haber múltiples IDs por accession_no si hay múltiples entidades)';
COMMENT ON COLUMN sec_filings.accession_no IS 'Número de acceso único del filing en SEC EDGAR';
COMMENT ON COLUMN sec_filings.form_type IS 'Tipo de formulario SEC (8-K, 10-K, 4, 13F, etc.)';
COMMENT ON COLUMN sec_filings.filed_at IS 'Fecha y hora en que el filing fue aceptado por EDGAR (Eastern Time)';
COMMENT ON COLUMN sec_filings.ticker IS 'Símbolo del ticker (NULL para empresas no-públicas)';
COMMENT ON COLUMN sec_filings.cik IS 'Central Index Key sin leading zeros';
COMMENT ON COLUMN sec_filings.items IS 'Array de items reportados (e.g., Item 1.03, Item 9.01 para 8-K)';
COMMENT ON COLUMN sec_filings.entities IS 'JSONB array de entidades referenciadas en el filing';
COMMENT ON COLUMN sec_filings.document_format_files IS 'JSONB array de archivos primarios y exhibits del filing';
COMMENT ON COLUMN sec_filings.data_files IS 'JSONB array de archivos XBRL (.XSD, .XML, etc.)';

-- =====================================================
-- ESTADÍSTICAS INICIALES
-- =====================================================

-- Actualizar estadísticas para el optimizer
ANALYZE sec_filings;

-- =====================================================
-- GRANTS DE PERMISOS
-- =====================================================

-- Los permisos se manejan con el usuario principal tradeul_user

-- =====================================================
-- FIN DEL SCRIPT
-- =====================================================

\echo '✅ Tabla sec_filings creada con éxito'
\echo '📊 Índices creados: 9'
\echo '👁️ Vistas creadas: 3'
\echo '🔧 Triggers creados: 1'

