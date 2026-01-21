"""
=============================================================================
EXTRACTOR UNIVERSAL DE FUNDAMENTALES SEC XBRL
=============================================================================

Integrado en API Gateway para FAN (Financial Analyst).

Extrae datos financieros oficiales directamente de SEC filings:
  - EPS, Revenue, Book Value, Net Income
  - Assets, Liabilities, Debt, Cash
  - Calcula: P/E, P/B, P/S, EV/EBITDA, D/E

Soporta:
  - US-GAAP (empresas americanas)
  - IFRS (ADRs internacionales)

Cache: 7 días (datos de 10-K/10-Q no cambian frecuentemente)
"""

import httpx
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SEC_API_KEY = "9166556ea56cfff44756201f7ddaa6c1bb3cc5778c72c735c37955418c0203d9"
QUERY_API = "https://api.sec-api.io"
XBRL_API = "https://api.sec-api.io/xbrl-to-json"
FLOAT_API = "https://api.sec-api.io/float"

CACHE_TTL = 7 * 24 * 60 * 60  # 7 días - datos de 10-K son estables

# =============================================================================
# TAGS US-GAAP
# =============================================================================

USGAAP = {
    "income_sections": [
        # Variantes US-GAAP (con y sin "Consolidated")
        "StatementsOfIncome",
        "ConsolidatedStatementsOfIncome",
        "StatementsOfOperations",
        "ConsolidatedStatementsOfOperations",
        "StatementsOfComprehensiveIncome",  # ONON, NU style
        "ConsolidatedStatementsOfComprehensiveIncome",
    ],
    "balance_sections": [
        "BalanceSheets",
        "ConsolidatedBalanceSheets",
        "StatementsOfFinancialPosition",
        "ConsolidatedStatementsOfFinancialPosition",
    ],
    "cashflow_sections": [
        "StatementsOfCashFlows",
        "ConsolidatedStatementsOfCashFlows",
    ],
    "eps": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
        # Tags IFRS usados por ADRs (ONON, NU, etc.)
        "DilutedEarningsLossPerShare",
        "BasicEarningsLossPerShare",
        "DilutedEarningsPerShare",
        "BasicEarningsPerShare",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenueFromContractsWithCustomers",  # ADRs (ONON, NU)
        "Revenue",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "TotalRevenuesAndOtherIncome",
    ],
    "net_income": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
        "ProfitLossAttributableToOwnersOfParent",  # IFRS-style usado por ADRs
    ],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "TotalEquity",
        "Equity",  # Simple, usado por ADRs como ONON
    ],
    "assets": ["Assets", "TotalAssets"],
    "liabilities": ["Liabilities", "TotalLiabilities"],
    "debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "debt_current": ["LongTermDebtCurrent", "ShortTermBorrowings"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "shares": [
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "operating_income": ["OperatingIncomeLoss", "IncomeLossFromOperations"],
}

# =============================================================================
# TAGS IFRS
# =============================================================================

IFRS = {
    "income_sections": [
        # Variantes comunes IFRS (con y sin espacios/guiones)
        "IncomestatementandStatementofcomprehensiveincome",  # Novo Nordisk style
        "ConsolidatedStatementsOfProfitOrLossAndOtherComprehensiveIncome",
        "ConsolidatedStatementsOfComprehensiveIncome",
        "StatementsOfComprehensiveIncome",
        "StatementsOfProfitOrLoss",
        "ConsolidatedIncomeStatements",
        "IncomeStatement",
    ],
    "balance_sections": [
        "BalanceSheets",
        "ConsolidatedBalanceSheets",
        "StatementsOfFinancialPosition",
        "ConsolidatedStatementsOfFinancialPosition",
    ],
    "cashflow_sections": [
        "StatementsOfCashFlows", 
        "ConsolidatedStatementsOfCashFlows",
        "CashFlowStatement",
    ],
    "eps_sections": [
        "EarningsPerShare", 
        "EarningsPerShareDetails",
        "IncomestatementandStatementofcomprehensiveincome",  # NVO tiene EPS aquí
    ],
    "revenue_sections": [
        "NetRevenue", 
        "Revenue", 
        "RevenueFromContractsWithCustomers",
        "IncomestatementandStatementofcomprehensiveincome",
    ],
    "equity_sections": [
        "Equity", 
        "StatementsOfShareholdersEquity",
        "BalanceSheets",  # IFRS a veces tiene Equity en Balance
    ],
    "eps": [
        "DilutedEarningsLossPerShare",
        "BasicEarningsLossPerShare", 
        "DilutedEarningsPerShare",
        "BasicEarningsPerShare",
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
    ],
    "revenue": [
        "Revenue",
        "Revenues",
        "NetRevenue",
        "TotalRevenue",
        "RevenueFromContractsWithCustomers",
        "SalesRevenue",
    ],
    "net_income": [
        "ProfitLoss",
        "ProfitLossAttributableToOwnersOfParent",
        "NetIncomeLoss",
        "ProfitLossForThePeriod",
    ],
    "equity": [
        "Equity",  # IFRS usa "Equity" directamente
        "TotalEquity",
        "EquityAttributableToOwnersOfParent",
        "StockholdersEquity",
        "TotalEquityAttributableToEquityHoldersOfParent",
    ],
    "assets": ["Assets", "TotalAssets"],
    "liabilities": ["Liabilities", "TotalLiabilities"],
    "cash": [
        "CashAndCashEquivalents", 
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
    ],
    "operating_income": [
        "ProfitLossFromOperatingActivities",  # IFRS común
        "OperatingIncomeLoss",
        "OperatingProfit",
    ],
    "depreciation": [
        "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
        "DepreciationAndAmortisation",
        "DepreciationDepletionAndAmortization",
    ],
}


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def _extraer_valor(items: Any, es_balance: bool = False) -> Optional[float]:
    """Extrae valor numérico de un item XBRL."""
    if items is None:
        return None

    if isinstance(items, dict):
        value = items.get("value")
        if value:
            try:
                return float(value)
            except:
                return None
        return None

    if isinstance(items, list):
        # Filtrar items sin segmentos (totales)
        items_simples = [
            item for item in items
            if "segment" not in item and item.get("value")
        ]
        if not items_simples:
            items_simples = [item for item in items if item.get("value")]
        if not items_simples:
            return None

        # Ordenar por fecha más reciente
        def obtener_fecha(item):
            periodo = item.get("period", {})
            return periodo.get("endDate") or periodo.get("instant") or ""

        items_simples.sort(key=obtener_fecha, reverse=True)

        # Para income statement, preferir periodos anuales
        if not es_balance:
            for item in items_simples:
                periodo = item.get("period", {})
                if "startDate" in periodo and "endDate" in periodo:
                    try:
                        inicio = datetime.strptime(periodo["startDate"], "%Y-%m-%d")
                        fin = datetime.strptime(periodo["endDate"], "%Y-%m-%d")
                        dias = (fin - inicio).days
                        if dias > 300:  # Periodo anual
                            return float(item["value"])
                    except:
                        pass

        try:
            return float(items_simples[0]["value"])
        except:
            return None

    return None


def _buscar_en_secciones(xbrl_data: Dict, secciones: List[str]) -> Optional[Dict]:
    """Busca primera sección existente."""
    for seccion in secciones:
        if seccion in xbrl_data and xbrl_data[seccion]:
            return xbrl_data[seccion]
    return None


def _buscar_valor_en_tags(datos: Dict, tags: List[str], es_balance: bool = False) -> Optional[float]:
    """Busca valor probando múltiples tags."""
    for tag in tags:
        valor = _extraer_valor(datos.get(tag), es_balance)
        if valor is not None:
            return valor
    return None


def _buscar_valor_multiseccion(
    xbrl_data: Dict, secciones: List[str], tags: List[str], es_balance: bool = False
) -> Optional[float]:
    """Busca valor en múltiples secciones y tags."""
    for seccion in secciones:
        if seccion in xbrl_data:
            valor = _buscar_valor_en_tags(xbrl_data[seccion], tags, es_balance)
            if valor is not None:
                return valor
    return _buscar_valor_en_tags(xbrl_data, tags, es_balance)


# =============================================================================
# FUNCIONES ASYNC DE API
# =============================================================================

async def _buscar_filing(ticker: str, cik: str = None) -> Optional[Dict]:
    """Busca el filing más reciente (10-K, 20-F, 10-Q, 6-K).
    
    Args:
        ticker: Símbolo de la acción
        cik: CIK de la empresa (más preciso que ticker)
    
    Preferencia: CIK > ticker (CIK es único, ticker puede ser ambiguo)
    Excluye amendments (/A) porque suelen ser correcciones parciales.
    """
    headers = {
        "Authorization": SEC_API_KEY,
        "Content-Type": "application/json"
    }
    form_types = ["10-K", "20-F", "10-Q", "6-K"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for form_type in form_types:
            # Preferir CIK si está disponible (más preciso)
            if cik:
                # Limpiar CIK (puede venir con ceros a la izquierda o sin ellos)
                cik_clean = str(cik).lstrip('0') if cik else None
                search_query = f'cik:"{cik_clean}" AND formType:"{form_type}" AND NOT formType:"{form_type}/A"'
            else:
                # Fallback a ticker con filtro de fecha
                search_query = f'ticker:"{ticker.upper()}" AND formType:"{form_type}" AND NOT formType:"{form_type}/A" AND filedAt:[2022-01-01 TO *]'
            
            query = {
                "query": {
                    "query_string": {
                        "query": search_query
                    }
                },
                "from": "0",
                "size": "1",
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            try:
                response = await client.post(QUERY_API, headers=headers, json=query)
                if response.status_code == 200:
                    filings = response.json().get("filings", [])
                    if filings:
                        filing = filings[0]
                        if "/A" not in filing.get("formType", ""):
                            logger.info("filing_found", ticker=ticker, cik=cik, form_type=filing.get("formType"), used_cik=bool(cik))
                            return filing
            except Exception as e:
                logger.warning("sec_api_filing_search_error", form_type=form_type, error=str(e))
                continue
    return None


async def _obtener_xbrl(accession_no: str) -> Optional[Dict]:
    """Obtiene datos XBRL convertidos a JSON."""
    headers = {"Authorization": SEC_API_KEY}
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(
                XBRL_API,
                headers=headers,
                params={"accession-no": accession_no}
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning("sec_api_xbrl_error", accession_no=accession_no, error=str(e))
    return None


async def _obtener_shares_outstanding(ticker: str) -> Optional[int]:
    """Obtiene acciones en circulación desde API Float."""
    headers = {"Authorization": SEC_API_KEY}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                FLOAT_API,
                headers=headers,
                params={"ticker": ticker.upper()}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    shares_list = data["data"][0].get("float", {}).get("outstandingShares", [])
                    return sum(item.get("value", 0) for item in shares_list)
        except Exception as e:
            logger.warning("sec_api_float_error", ticker=ticker, error=str(e))
    return None


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

async def extraer_fundamentales(ticker: str, cik: str = None) -> Dict:
    """
    Extrae todos los fundamentales de un ticker desde SEC XBRL.
    Detecta automáticamente US-GAAP o IFRS.
    
    Args:
        ticker: Símbolo de la acción
        cik: CIK de la empresa (opcional, más preciso)
    """
    resultado = {
        "ticker": ticker.upper(),
        "status": "error",
        "standard": None,
        "filing": {},
        "fundamentals": {}
    }

    # Paso 1: Buscar filing (preferir CIK si está disponible)
    filing = await _buscar_filing(ticker, cik)
    if not filing:
        resultado["error"] = "No SEC filing found"
        return resultado

    resultado["filing"] = {
        "form_type": filing.get("formType"),
        "period_end": filing.get("periodOfReport"),
        "filed_at": filing.get("filedAt"),
        "accession_no": filing.get("accessionNo"),
        "company_name": filing.get("companyName")
    }

    # Paso 2: Obtener XBRL
    xbrl = await _obtener_xbrl(filing.get("accessionNo"))
    if not xbrl:
        resultado["error"] = "Could not extract XBRL data"
        return resultado

    # Paso 3: Detectar estándar (US-GAAP o IFRS)
    es_usgaap = any(section in xbrl for section in USGAAP["income_sections"])

    if es_usgaap:
        resultado["standard"] = "US-GAAP"
        tags = USGAAP
        income_sections = USGAAP["income_sections"]
        balance_sections = USGAAP["balance_sections"]
        eps_sections = income_sections
    else:
        resultado["standard"] = "IFRS"
        tags = IFRS
        income_sections = IFRS["income_sections"]
        balance_sections = IFRS["balance_sections"]
        eps_sections = IFRS.get("eps_sections", []) + income_sections

    # Paso 4: Extraer fundamentales
    fundamentals = {}

    # EPS
    fundamentals["eps_diluted"] = _buscar_valor_multiseccion(
        xbrl, eps_sections, tags["eps"], es_balance=False
    )

    # Revenue
    revenue_sections = income_sections
    if "revenue_sections" in tags:
        revenue_sections = tags["revenue_sections"] + income_sections
    fundamentals["revenue"] = _buscar_valor_multiseccion(
        xbrl, revenue_sections, tags["revenue"], es_balance=False
    )

    # Net Income
    fundamentals["net_income"] = _buscar_valor_multiseccion(
        xbrl, income_sections, tags["net_income"], es_balance=False
    )

    # Stockholders Equity
    equity_sections = balance_sections
    if "equity_sections" in tags:
        equity_sections = tags["equity_sections"] + balance_sections
    fundamentals["stockholders_equity"] = _buscar_valor_multiseccion(
        xbrl, equity_sections, tags["equity"], es_balance=True
    )

    # Total Assets
    fundamentals["total_assets"] = _buscar_valor_multiseccion(
        xbrl, balance_sections, tags.get("assets", ["Assets"]), es_balance=True
    )

    # Total Liabilities
    fundamentals["total_liabilities"] = _buscar_valor_multiseccion(
        xbrl, balance_sections, tags.get("liabilities", ["Liabilities"]), es_balance=True
    )

    # Cash
    fundamentals["cash"] = _buscar_valor_multiseccion(
        xbrl, balance_sections, tags.get("cash", ["CashAndCashEquivalentsAtCarryingValue"]), es_balance=True
    )

    # Debt
    debt_lt = _buscar_valor_multiseccion(
        xbrl, balance_sections, tags.get("debt", ["LongTermDebtNoncurrent"]), es_balance=True
    ) or 0
    debt_st = _buscar_valor_multiseccion(
        xbrl, balance_sections, tags.get("debt_current", ["LongTermDebtCurrent"]), es_balance=True
    ) or 0
    fundamentals["total_debt"] = debt_lt + debt_st

    # Operating Income
    fundamentals["operating_income"] = _buscar_valor_multiseccion(
        xbrl, income_sections, tags.get("operating_income", ["OperatingIncomeLoss"]), es_balance=False
    )

    # Depreciation
    cashflow_sections = tags.get("cashflow_sections", ["StatementsOfCashFlows"])
    fundamentals["depreciation"] = _buscar_valor_multiseccion(
        xbrl, cashflow_sections, tags.get("depreciation", ["DepreciationDepletionAndAmortization"]), es_balance=False
    )

    # Shares Outstanding
    shares = await _obtener_shares_outstanding(ticker)
    if not shares:
        cover = xbrl.get("CoverPage", {})
        shares_xbrl = _buscar_valor_en_tags(cover, tags.get("shares", ["EntityCommonStockSharesOutstanding"]), es_balance=True)
        if shares_xbrl:
            shares = int(shares_xbrl)
    fundamentals["shares_outstanding"] = shares

    resultado["fundamentals"] = fundamentals
    resultado["status"] = "success"

    logger.info("fundamentals_extracted", ticker=ticker, standard=resultado["standard"], form_type=resultado["filing"].get("form_type"))

    return resultado


async def calcular_ratios(ticker: str, precio: float, cik: str = None) -> Dict:
    """
    Extrae fundamentales y calcula P/E, P/B, P/S, EV/EBITDA, D/E.
    
    Args:
        ticker: Símbolo
        precio: Precio actual
        cik: CIK de la empresa (más preciso que ticker)
    """
    data = await extraer_fundamentales(ticker, cik)

    if data["status"] != "success":
        return data

    f = data["fundamentals"]
    ratios = {}

    # Market Cap
    market_cap = None
    if f.get("shares_outstanding"):
        market_cap = precio * f["shares_outstanding"]
        ratios["market_cap"] = market_cap

    # P/E = Precio / EPS (mostrar incluso si EPS es negativo)
    if f.get("eps_diluted") and f["eps_diluted"] != 0:
        ratios["pe_ratio"] = round(precio / f["eps_diluted"], 2)
    else:
        ratios["pe_ratio"] = None

    # P/B = Market Cap / Book Value (mostrar incluso si equity es negativo)
    if market_cap and f.get("stockholders_equity") and f["stockholders_equity"] != 0:
        ratios["pb_ratio"] = round(market_cap / f["stockholders_equity"], 2)
    else:
        ratios["pb_ratio"] = None

    # P/S = Market Cap / Revenue (solo si revenue > 0, no podemos dividir por 0)
    if market_cap and f.get("revenue") and f["revenue"] > 0:
        ratios["ps_ratio"] = round(market_cap / f["revenue"], 2)
    else:
        ratios["ps_ratio"] = None

    # EV/EBITDA (mostrar incluso si EBITDA es negativo)
    if market_cap and f.get("operating_income"):
        ebitda = f["operating_income"] + (f.get("depreciation") or 0)
        ev = market_cap + (f.get("total_debt") or 0) - (f.get("cash") or 0)
        ratios["enterprise_value"] = ev
        ratios["ebitda"] = ebitda
        if ebitda != 0:  # Mostrar incluso si negativo
            ratios["ev_ebitda"] = round(ev / ebitda, 2)

    # Debt/Equity (mostrar incluso si equity es negativo)
    if f.get("stockholders_equity") and f["stockholders_equity"] != 0:
        ratios["debt_equity"] = round((f.get("total_debt") or 0) / f["stockholders_equity"], 2)

    # Profit Margin (mostrar incluso si net_income es negativo, pero revenue debe ser > 0)
    if f.get("net_income") is not None and f.get("revenue") and f["revenue"] > 0:
        ratios["profit_margin"] = round((f["net_income"] / f["revenue"]) * 100, 2)

    data["current_price"] = precio
    data["ratios"] = ratios

    return data


# =============================================================================
# FUNCIÓN PARA FAN (con cache)
# =============================================================================

async def get_fundamentals_for_fan(ticker: str, current_price: float, redis_client=None, cik: str = None) -> Dict:
    """
    Obtiene fundamentales para FAN con caché de 7 días.
    
    Args:
        ticker: Símbolo
        current_price: Precio actual
        redis_client: Cliente Redis para caché
        cik: CIK de la empresa (más preciso que ticker)
    
    Returns dict con:
    - fundamentals: datos crudos de XBRL
    - ratios: P/E, P/B, P/S, EV/EBITDA calculados
    - filing: info del filing usado
    """
    cache_key = f"fundamentals:xbrl:{ticker.upper()}"
    
    # Check cache
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached and isinstance(cached, dict):
                # redis_client.get() ya deserializa JSON automáticamente
                data = cached
                # Recalcular ratios con precio actual
                if data.get("status") == "success":
                    f = data["fundamentals"]
                    ratios = {}
                    market_cap = None
                    
                    if f.get("shares_outstanding"):
                        market_cap = current_price * f["shares_outstanding"]
                        ratios["market_cap"] = market_cap
                    
                    # P/E (mostrar incluso si negativo)
                    if f.get("eps_diluted") and f["eps_diluted"] != 0:
                        ratios["pe_ratio"] = round(current_price / f["eps_diluted"], 2)
                    
                    # P/B (mostrar incluso si equity negativo)
                    if market_cap and f.get("stockholders_equity") and f["stockholders_equity"] != 0:
                        ratios["pb_ratio"] = round(market_cap / f["stockholders_equity"], 2)
                    
                    # P/S (solo si revenue > 0)
                    if market_cap and f.get("revenue") and f["revenue"] > 0:
                        ratios["ps_ratio"] = round(market_cap / f["revenue"], 2)
                    
                    # EV/EBITDA (mostrar incluso si negativo)
                    if market_cap and f.get("operating_income"):
                        ebitda = f["operating_income"] + (f.get("depreciation") or 0)
                        ev = market_cap + (f.get("total_debt") or 0) - (f.get("cash") or 0)
                        if ebitda != 0:
                            ratios["ev_ebitda"] = round(ev / ebitda, 2)
                    
                    # D/E (mostrar incluso si equity negativo)
                    if f.get("stockholders_equity") and f["stockholders_equity"] != 0:
                        ratios["debt_equity"] = round((f.get("total_debt") or 0) / f["stockholders_equity"], 2)
                    
                    # Profit Margin (mostrar negativo, pero revenue debe ser > 0)
                    if f.get("net_income") is not None and f.get("revenue") and f["revenue"] > 0:
                        ratios["profit_margin"] = round((f["net_income"] / f["revenue"]) * 100, 2)
                    
                    data["ratios"] = ratios
                    data["current_price"] = current_price
                    logger.info("fundamentals_cache_hit", ticker=ticker)
                    return data
        except Exception as e:
            logger.warning("fundamentals_cache_error", ticker=ticker, error=str(e))
    
    # Fetch fresh data (usar CIK si disponible)
    result = await calcular_ratios(ticker, current_price, cik)
    
    # Cache successful results
    if redis_client and result.get("status") == "success":
        try:
            # Cache sin ratios (se recalculan con precio actual)
            cache_data = {
                "ticker": result["ticker"],
                "status": result["status"],
                "standard": result["standard"],
                "filing": result["filing"],
                "fundamentals": result["fundamentals"]
            }
            # redis_client.set() serializa automáticamente
            await redis_client.set(cache_key, cache_data, ttl=CACHE_TTL)
            logger.info("fundamentals_cached", ticker=ticker, ttl_days=CACHE_TTL // 86400)
        except Exception as e:
            logger.warning("fundamentals_cache_set_error", ticker=ticker, error=str(e))
    
    return result
