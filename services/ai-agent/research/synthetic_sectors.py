"""
Synthetic Sectors / ETFs Generator
===================================
Uses LLM KNOWLEDGE to dynamically classify tickers into thematic sectors.

The LLM knows virtually ALL publicly traded companies, so it can
intelligently group stocks into sectors like Nuclear, AI, EV, etc.
"""

import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime
import structlog
import pandas as pd

logger = structlog.get_logger(__name__)


async def classify_tickers_into_synthetic_sectors(
    tickers_df: pd.DataFrame,
    llm_client,
    max_sectors: int = 15,
    min_tickers_per_sector: int = 2
) -> pd.DataFrame:
    """
    Use LLM's KNOWLEDGE to classify tickers into thematic synthetic sectors.
    """
    if tickers_df.empty or llm_client is None:
        logger.warning("synthetic_sectors_no_data_or_llm")
        return pd.DataFrame()
    
    df = tickers_df.copy()
    
    # Filter out warrants and weird symbols (LLM doesn't know them)
    # Warrants end in W, .WS, or have special characters
    df = df[~df['symbol'].str.contains(r'\.WS$|W$|\.U$|\.R$|\+', regex=True, na=False)]
    df = df[df['symbol'].str.len() <= 5]  # Normal tickers are 1-5 chars
    
    # Use ALL tickers with market cap (LLM knows companies better with context)
    if 'market_cap' in df.columns:
        df_with_cap = df[df['market_cap'] > 0].copy()
        if len(df_with_cap) >= 30:
            df = df_with_cap
    
    # Remove duplicates
    df_to_classify = df.drop_duplicates(subset='symbol').copy()
    
    # Get all unique symbols
    symbols = df_to_classify['symbol'].tolist()
    
    logger.info("synthetic_sectors_classifying", 
               total_tickers=len(tickers_df),
               unique_to_classify=len(symbols))
    
    # Process in batches of 40 (gemini-2.0-flash handles this well)
    BATCH_SIZE = 40
    all_classifications = {}
    
    # Build context dict: symbol -> (sector, industry) from scanner data
    symbol_context = {}
    for _, row in df_to_classify.iterrows():
        sym = row['symbol']
        sector = row.get('sector', '') or ''
        industry = row.get('industry', '') or ''
        symbol_context[sym] = (sector, industry)
    
    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        # Build batch with context
        batch_with_context = [(sym, symbol_context.get(sym, ('', ''))) for sym in batch]
        
        logger.info("classifying_batch", 
                   batch_num=i // BATCH_SIZE + 1,
                   batch_size=len(batch),
                   total_batches=(len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE)
        
        batch_classifications = await _llm_classify_with_context(
            symbols_with_context=batch_with_context,
            llm_client=llm_client
        )
        
        if batch_classifications:
            all_classifications.update(batch_classifications)
    
    if not all_classifications:
        logger.warning("synthetic_sectors_llm_returned_empty")
        return pd.DataFrame()
    
    classifications = all_classifications
    
    # Build result DataFrame
    results = []
    for _, row in df_to_classify.iterrows():
        symbol = row['symbol']
        synthetic_sector = classifications.get(symbol)
        
        # Skip unclassified
        if not synthetic_sector or synthetic_sector in ["Unknown", "Other", "N/A"]:
            continue
        
        results.append({
            "symbol": symbol,
            "synthetic_sector": synthetic_sector,
            "price": row.get('price', 0),
            "change_percent": row.get('change_percent', 0),
            "premarket_change_percent": row.get('premarket_change_percent', 0),
            "volume_today": row.get('volume_today', 0),
            "market_cap": row.get('market_cap', 0),
        })
    
    if not results:
        return pd.DataFrame()
    
    result_df = pd.DataFrame(results)
    
    # Filter sectors with too few tickers
    sector_counts = result_df['synthetic_sector'].value_counts()
    valid_sectors = sector_counts[sector_counts >= min_tickers_per_sector].index.tolist()
    result_df = result_df[result_df['synthetic_sector'].isin(valid_sectors)]
    
    logger.info("synthetic_sectors_classified",
               total_classified=len(result_df),
               sectors=result_df['synthetic_sector'].nunique(),
               sector_names=result_df['synthetic_sector'].unique().tolist())
    
    return result_df


async def _llm_classify_with_context(
    symbols_with_context: List[tuple],  # [(symbol, (sector, industry)), ...] - we ignore the context now
    llm_client
) -> Dict[str, str]:
    """
    LLM classification using LLM's OWN KNOWLEDGE of companies.
    No official sector/industry passed to avoid biasing the thematic classification.
    """
    
    # Just pass the symbols - let LLM use its knowledge
    symbols = [sym for sym, _ in symbols_with_context]
    batch_str = ", ".join(symbols)
    
    prompt = f"""You are creating THEMATIC SYNTHETIC ETFs by grouping stocks.

STEP 1: For each ticker, recall what company it is and what they do.
STEP 2: Classify into the most specific THEMATIC sector.

TICKERS TO CLASSIFY:
{batch_str}

THEMATIC SECTORS (these are INVESTMENT THEMES, not traditional sectors):
- Nuclear Energy (uranium miners, nuclear power plants, reactor builders)
- AI & Semiconductors (GPU makers, AI chip designers, AI infrastructure like CoreWeave)
- Electric Vehicles (EV manufacturers, battery makers, charging networks)
- Solar & Clean Energy (solar panel makers, wind energy, clean tech)
- Biotech & Pharmaceuticals (drug developers, clinical stage biotechs)
- Fintech & Digital Payments (payment processors, neobanks, trading platforms)
- Crypto & Bitcoin (crypto exchanges, Bitcoin miners, blockchain companies)
- Cybersecurity (security software, threat detection, identity protection)
- Gaming & Entertainment (video game publishers, esports, streaming)
- E-Commerce (online retailers, marketplaces, D2C brands)
- Cloud Computing (cloud infrastructure, SaaS platforms, data centers)
- Cannabis (marijuana growers, CBD products, dispensaries - ONLY actual cannabis businesses)
- Space Exploration (rocket companies, satellite operators, space tech)
- Defense & Aerospace (military contractors, aerospace manufacturers)
- Industrial Machinery (factory equipment, automation)
- Online Gambling (sports betting, online casinos, iGaming)
- Medical Diagnostics (diagnostic equipment, lab testing, medical devices)
- Oil & Gas (drillers, refiners, pipelines)
- Real Estate (REITs) (property owners, real estate services)
- Mining & Materials (gold/silver miners, lithium, rare earths)
- Quantum Computing (quantum hardware, quantum software)
- Weight Loss / GLP-1 Drugs (Ozempic-like drugs, obesity treatments)
- China Tech (Chinese internet, Chinese tech giants)

CLASSIFICATION RULES:
1. USE YOUR KNOWLEDGE of what each company actually does
2. CoreWeave (CRWV) = GPU cloud infrastructure → AI & Semiconductors or Cloud Computing
3. SPACs/Blank checks with no clear target → SKIP (don't classify)
4. If you don't know the company → SKIP (don't guess)
5. Be SPECIFIC - prefer "Weight Loss / GLP-1 Drugs" over generic "Biotech"

Respond ONLY with valid JSON (no markdown):
{{"TICKER": "Sector", ...}}"""

    try:
        from google.genai import types
        
        # Use gemini-2.0-flash specifically - it handles JSON better than 2.5
        # Using async API for non-blocking execution
        response = await llm_client.client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            )
        )
        
        response_text = response.text if response.text else ""
        
        logger.info("llm_raw_response", length=len(response_text), preview=response_text[:200])
        
        # Clean and parse JSON
        response_text = response_text.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        response_text = response_text.strip()
        
        # Find JSON boundaries
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        
        if start >= 0 and end > start:
            json_str = response_text[start:end]
            
            # Fix common JSON issues
            # Remove trailing commas before }
            import re
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*$', '', json_str)
            
            # Ensure proper closing
            if not json_str.endswith('}'):
                json_str += '}'
            
            try:
                classifications = json.loads(json_str)
                logger.info("llm_classification_complete",
                           classified=len(classifications),
                           unique_sectors=len(set(classifications.values())))
                return classifications
            except json.JSONDecodeError as je:
                logger.error("json_parse_error", error=str(je), json_preview=json_str[:300])
            
    except Exception as e:
        logger.error("llm_classification_error", error=str(e))
    
    return {}


def calculate_synthetic_sector_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate aggregate performance for each synthetic sector."""
    if df.empty or 'synthetic_sector' not in df.columns:
        return pd.DataFrame()
    
    # Determine which change column to use
    if 'premarket_change_percent' in df.columns:
        premarket_non_zero = (df['premarket_change_percent'].fillna(0) != 0).sum()
        change_col = 'premarket_change_percent' if premarket_non_zero > len(df) * 0.3 else 'change_percent'
    else:
        change_col = 'change_percent'
    
    # Aggregate by sector - show ALL tickers, not just top 5
    sector_stats = df.groupby('synthetic_sector').agg({
        'symbol': ['count', lambda x: ', '.join(sorted(x))],  # ALL tickers
        change_col: ['mean', 'median', 'min', 'max'],
        'volume_today': 'sum',
        'market_cap': 'sum'
    }).reset_index()
    
    sector_stats.columns = [
        'sector', 'ticker_count', 'tickers',  # Renamed from 'top_tickers' to 'tickers'
        'avg_change', 'median_change', 'min_change', 'max_change',
        'total_volume', 'total_market_cap'
    ]
    
    # Round and sort
    for col in ['avg_change', 'median_change', 'min_change', 'max_change']:
        sector_stats[col] = sector_stats[col].round(2)
    
    sector_stats = sector_stats.sort_values('avg_change', ascending=False)
    
    logger.info("synthetic_sector_performance_calculated",
               sectors=len(sector_stats),
               top_sector=sector_stats.iloc[0]['sector'] if len(sector_stats) > 0 else None)
    
    return sector_stats


def clean_tickers_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Remove unnecessary columns from tickers dataframe for cleaner display."""
    if df.empty:
        return df
    
    # Remove premarket_change_percent if all values are 0 or null
    if 'premarket_change_percent' in df.columns:
        premarket_non_zero = (df['premarket_change_percent'].fillna(0) != 0).sum()
        if premarket_non_zero == 0:
            df = df.drop(columns=['premarket_change_percent'])
    
    return df
