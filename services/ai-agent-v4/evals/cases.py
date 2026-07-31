"""
Casos curados de routing — aserciones "must-pass".

Cada caso fija expectativas mínimas sobre la decisión del planner:
  - `intent_in`: el intent clasificado debe estar en este conjunto.
  - `agents_any`: al menos uno de estos agentes debe activarse.
  - `agents_all`: todos estos agentes deben activarse (⊆ active_agents).

Filosofía: no sobre-especificar (el planner puede añadir agentes de más), sino
codificar el comportamiento que NO debe romperse. El caso estrella es el híbrido
"movers de hoy relacionados con una noticia" — el que originó la auditoría: una
pregunta de datos live SIEMPRE debe activar market_data, nunca quedarse solo en
research/prensa.
"""

CURATED = [
    {
        "id": "greeting_es",
        "query": "hola, qué tal?",
        "intent_in": {"GREETING"},
    },
    {
        "id": "data_lookup_price",
        "query": "¿a cuánto cotiza NVDA ahora mismo?",
        "intent_in": {"DATA_LOOKUP"},
        "agents_any": ["market_data"],
    },
    {
        "id": "causal_single",
        "query": "por qué sube SMCI hoy?",
        "intent_in": {"CAUSAL", "COMPLETE_ANALYSIS"},
        "agents_any": ["research", "news_events", "market_data"],
    },
    {
        "id": "ranking_gappers",
        "query": "dame el top 10 de gappers de hoy",
        "intent_in": {"RANKING"},
        "agents_any": ["market_data"],
    },
    {
        "id": "screening_numeric",
        "query": "acciones con RSI por debajo de 30 y volumen mayor a 1 millón",
        "intent_in": {"SCREENING", "RANKING"},
        "agents_any": ["screener", "market_data"],
    },
    {
        "id": "dilution_focus",
        "query": "cuántos warrants y qué shelf tiene GNS?",
        "intent_in": {"DILUTION_ANALYSIS", "DILUTION", "COMPLETE_ANALYSIS"},
        "agents_any": ["dilution"],
    },
    {
        # Market-wide sin ticker: debe ir al agente dilution (trending), no a
        # un ranking de market_data/screener.
        "id": "dilution_trending_market",
        "query": "¿Qué tickers tienen más actividad de dilución esta semana?",
        "intent_in": {"DILUTION_ANALYSIS", "DILUTION"},
        "agents_any": ["dilution"],
    },
    {
        "id": "alert_create",
        "query": "avísame cuando una acción cruce el VWAP al alza con RVOL mayor a 1.5",
        "intent_in": {"ALERT_CREATE"},
        "agents_any": ["alert_compiler"],
    },
    {
        "id": "strategy_scan",
        "query": "qué acciones cayeron fuerte en el opening y luego recuperaron el VWAP ayer?",
        "intent_in": {"STRATEGY_SCAN", "SCREENING", "RANKING"},
        "agents_any": ["strategy_scanner", "market_data", "screener"],
    },
    {
        "id": "backtest",
        "query": "backtest de comprar cuando RSI < 30 con stop del 5% y target del 10%",
        "intent_in": {"BACKTEST"},
        "agents_any": ["backtest"],
    },
    {
        # EL CASO ESTRELLA — híbrido noticia + movers live. La lección de fondo
        # es que DEBE tocar datos live (market_data/screener), no quedarse en
        # research/prensa. Solo se asegura eso: el `intent` exacto es
        # secundario y además hoy es inestable porque el planner cae a FALLBACK
        # cuando su JSON se trunca (parseo frágil — objetivo de la Fase 3, con
        # constrained decoding). FALLBACK igualmente enruta a market_data, así
        # que la garantía de datos-live se mantiene.
        "id": "hybrid_news_movers",
        "query": "qué stocks suben hoy que tengan que ver con el catalizador de aranceles a farmacéuticas?",
        "agents_any": ["market_data", "screener"],
    },
    {
        "id": "thematic_theme",
        "query": "cuál es la temática dominante hoy en el pre-market?",
        "intent_in": {"THEMATIC", "MARKET_PULSE", "RANKING"},
        "agents_any": ["market_data", "screener"],
    },
    {
        "id": "financials",
        "query": "enséñame el income statement y el balance de AAPL",
        "intent_in": {"FUNDAMENTALS", "FINANCIALS", "COMPLETE_ANALYSIS", "DATA_LOOKUP"},
        "agents_any": ["financial"],
    },
]

# ── Fase 3b: brief threads (news_brief como nodo del grafo) ──────────────────
# El planner solo ve el agente news_brief cuando el estado trae news_context.
# Estos casos fijan las tres rutas: conversacional → news_brief; datos live →
# agentes live; híbrido → ambos en paralelo.

_BRIEF_STATE = {
    "news_context": {
        "headline": "Pfizer anuncia aranceles del 200% a farmacéuticas importadas",
        "text": (
            "La administración anuncia aranceles de hasta el 200% a productos "
            "farmacéuticos importados; PFE, MRK y las genéricas con producción "
            "en el extranjero serían las más expuestas."
        ),
        "tickers": ["PFE", "MRK"],
    },
    "brief_history": [
        {"role": "user", "content": "/contexto"},
        {"role": "assistant", "content": "## Brief: aranceles a farmacéuticas…"},
    ],
    "memory_context": [
        {"source": "thread", "query": "/contexto aranceles farmacéuticas", "intent": "NEWS", "tickers": ["PFE"]},
    ],
}

CURATED += [
    {
        # Follow-up conversacional/analítico → se queda en el motor de briefs.
        "id": "brief_followup_chat",
        "query": "y esto qué implica para las farmacéuticas europeas a medio plazo?",
        "state": _BRIEF_STATE,
        "agents_all": ["news_brief"],
        "agents_none": ["market_data", "screener", "research"],
    },
    {
        # Follow-up de datos live → agentes live (con o sin news_brief, pero
        # los datos live son obligatorios). El caso que el router binario
        # LIVE/CHAT resolvía perdiendo el motor de briefs.
        "id": "brief_followup_live",
        "query": "qué stocks del sector están subiendo ahora mismo con más volumen?",
        "state": _BRIEF_STATE,
        "agents_any": ["market_data", "screener"],
    },
    {
        # Híbrido: análisis de la noticia + movers live → ambos en paralelo.
        "id": "brief_followup_hybrid",
        "query": "qué stocks suben hoy con este catalizador y qué implica para el sector?",
        "state": _BRIEF_STATE,
        "agents_all": ["news_brief"],
        "agents_any": ["market_data", "screener"],
    },
    {
        # Sin news_context el agente news_brief NO existe para el planner:
        # una query normal jamás debe enrutarse a él.
        "id": "no_brief_leak",
        "query": "qué implicaciones tiene la última noticia de PFE?",
        "agents_none": ["news_brief"],
    },
    {
        # Caso real (2026-07-22): en un hilo cuyo único turno era "top 50
        # gainers", el usuario preguntó por "este catalizador" — que solo
        # existía en el recall de OTRA conversación (aranceles). El planner
        # lo adoptó como sujeto con confianza 0.95 en vez de pedir aclaración.
        # Regla 6 de conversation_awareness: referente fuera de este hilo →
        # clarification, y el plan no debe asumir los aranceles.
        "id": "recall_not_subject",
        "query": "qué sube hoy con este catalizador y qué implica",
        "state": {
            "memory_context": [
                {"source": "thread", "query": "top 50 gainers today",
                 "intent": "RANKING", "tickers": []},
                {"source": "memory:conversation",
                 "content": "que stocks suben hoy que tengan que ver con este catalizador de aranceles a farmacéuticas?"},
            ],
        },
        "expect_clarification": True,
        "plan_not_contains": ["arancel", "tariff", "farmac", "pharma"],
    },
    {
        # Caso real (2026-07-27): "grafica el cierre de X en julio y dame el
        # retorno" se enrutaba a market_data (DATA_LOOKUP), que no puede ni
        # graficar rangos históricos ni calcular retornos de periodo. Serie
        # histórica + métrica de rango → code_exec (único con rango + charts).
        "id": "chart_range_to_code_exec",
        "query": "grafica el cierre de AAPL en julio y dame el retorno del periodo",
        "agents_all": ["code_exec"],
    },
    {
        # Caso real (2026-07-24): "top 13 pharma by enterprise value" se
        # aproximó con la unión de 14 temáticas nicho → JNJ ($615B) quedó
        # fuera y EW (equipamiento) se coló. Regla 7 de universe_screen:
        # industria amplia → filtro por campo industry/sector del universo
        # completo, no temáticas.
        "id": "broad_industry_screen",
        "query": "Give me top 13 pharma enterprises by enterprise value",
        "intent_in": {"RANKING", "THEMATIC", "SCREENING"},
        "agents_any": ["market_data", "screener"],
        "screen_fields_any": ["industry", "sector"],
        "themes_max": 0,
    },
    {
        # La contraparte: las temáticas nicho siguen siendo la vía correcta
        # para verticales que la clasificación GICS/SIC no captura.
        "id": "niche_theme_still_themes",
        "query": "dame acciones de computación cuántica",
        "intent_in": {"THEMATIC"},
        "agents_any": ["market_data"],
    },
]

# ── Contrato screen multi-lista (2026-07-27) ─────────────────────────────────
# Caso real: "top 10 up after hours solo, y top 10 down after hours solo" —
# el planner emitía UN solo screen desc y la lista "down" salía de un re-corte
# del top-N. El contrato ahora admite un array de screens con label; la
# dirección down es el MISMO campo de sort con sort_order asc.

CURATED += [
    {
        # La query real del incidente: dos listas rankeadas → array de screens.
        "id": "ah_dual_lists",
        "query": "dame top acciones after hours por encima de 100m de capitalización! top 10 up after hours solo, y top 10 down after hours solo",
        "intent_in": {"RANKING"},
        "agents_any": ["market_data"],
        "screens_min": 2,
        "screen_fields_any": ["market_cap"],
        "screen_sorts_any": ["postmarket_change_percent"],
    },
    {
        # Una sola lista con constraint → sigue bastando un único screen.
        "id": "ah_single_list",
        "query": "top 10 acciones que más suben en after hours con market cap mayor a 300m",
        "agents_any": ["market_data"],
        "screens_min": 1,
        "screen_fields_any": ["market_cap"],
        "screen_sorts_any": ["postmarket_change_percent"],
    },
    {
        # Dirección "down" sola con constraint expresado como "por encima de
        # 100m de capitalización" — lo mínimo es que emita el screen.
        "id": "ah_cap_direction",
        "query": "top 10 down after hours por encima de 100m de capitalización",
        "agents_any": ["market_data"],
        "screens_min": 1,
    },
    {
        # Dual premarket: gainers + losers con floor de volumen premarket.
        "id": "premarket_dual",
        "query": "top 5 premarket gainers y top 5 premarket losers con volumen premarket por encima de 500k",
        "agents_any": ["market_data"],
        "screens_min": 2,
        "screen_sorts_any": ["premarket_change_percent"],
    },
    {
        # Sort custom de sesión sin constraints: la regla 6 no aplica porque
        # postmarket_volume no existe como categoría del scanner.
        "id": "ah_volume_sort",
        "query": "top 10 por volumen en after hours",
        "agents_any": ["market_data"],
        "screens_min": 1,
        "screen_sorts_any": ["postmarket_volume"],
    },
    {
        # Guardia scanner-vs-screener: wording de "filtrar" con campo de
        # SESIÓN jamás debe caer en SCREENING (el screener EOD no tiene
        # campos de sesión) — va a RANKING/market_data con screen.
        "id": "ah_filter_not_screening",
        "query": "filtra las acciones que suben más de un 3% en after hours",
        "intent_in": {"RANKING"},
        "agents_any": ["market_data"],
        "screens_min": 1,
        "screen_sorts_any": ["postmarket_change_percent"],
    },
]
