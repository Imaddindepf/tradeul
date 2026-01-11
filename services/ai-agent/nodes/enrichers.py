"""
ENRICH nodes - Add intelligence to data.
Based on Narrative Econometrics: use real news context for classification.
Reference: "From Headlines to Forecasts: Narrative Econometrics in Equity Markets"
"""
from typing import Dict, Any, Optional, List
import pandas as pd
import asyncio
from nodes.base import NodeBase, NodeCategory, NodeResult
import structlog

logger = structlog.get_logger()


class NewsEnricherNode(NodeBase):
    """
    Fetch news for each ticker using Grok research.
    Adds: has_news, news_count, latest_headline, news_summary
    """
    name = "news_enricher"
    category = NodeCategory.ENRICH
    description = "Add real-time news context for each ticker"
    config_schema = {
        "max_tickers": {"type": "int", "default": 20},
        "news_limit": {"type": "int", "default": 3},
        "batch_size": {"type": "int", "default": 5},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            max_tickers = self.get_config_value("max_tickers", 20)
            batch_size = self.get_config_value("batch_size", 5)
            
            if "symbol" not in df.columns:
                return NodeResult(success=False, error="symbol column required")
            
            tickers = df["symbol"].head(max_tickers).tolist()
            
            # Initialize columns
            df["has_news"] = False
            df["news_count"] = 0
            df["latest_headline"] = ""
            df["news_summary"] = ""
            
            # Process in batches
            for i in range(0, len(tickers), batch_size):
                batch = tickers[i:i+batch_size]
                tasks = [self._fetch_news(ticker) for ticker in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for ticker, result in zip(batch, results):
                    if isinstance(result, Exception):
                        continue
                    if result:
                        mask = df["symbol"] == ticker
                        df.loc[mask, "has_news"] = result.get("has_news", False)
                        df.loc[mask, "news_count"] = result.get("count", 0)
                        df.loc[mask, "latest_headline"] = result.get("headline", "")[:150]
                        df.loc[mask, "news_summary"] = result.get("summary", "")[:300]
            
            with_news = int(df["has_news"].sum())
            self.logger.info("news_enricher_complete", processed=len(tickers), with_news=with_news)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"processed": len(tickers), "with_news": with_news}
            )
            
        except Exception as e:
            self.logger.error("news_enricher_error", error=str(e))
            return NodeResult(success=False, error=str(e))
    
    async def _fetch_news(self, ticker: str) -> Dict[str, Any]:
        try:
            from research.grok_research import research_ticker
            
            result = await research_ticker(
                ticker=ticker,
                query=f"Latest breaking news and catalysts for {ticker} stock today"
            )
            
            if result.get("success") and result.get("content"):
                content = result["content"]
                return {
                    "has_news": True,
                    "count": len(result.get("citations", [])),
                    "headline": content[:150],
                    "summary": content[:400]
                }
            return {"has_news": False, "count": 0, "headline": "", "summary": ""}
        except:
            return {"has_news": False, "count": 0, "headline": "", "summary": ""}


class NarrativeClassifierNode(NodeBase):
    """
    AUTONOMOUS Narrative Classifier with real news context.
    
    Based on Narrative Econometrics methodology:
    1. First fetches relevant news/context for each ticker
    2. Then classifies based on ACTUAL information, not just numbers
    
    Categories:
    - CATALYST_DRIVEN: Confirmed news, FDA, earnings beat, M&A, etc.
    - MACRO_SECTOR: Sector-wide move, Fed, economic data
    - SILENT_ACCUMULATION: High volume WITHOUT news (potential insider)
    - EARNINGS_PLAY: Pre/post earnings volatility
    - TECHNICAL: Chart breakout, no fundamental catalyst
    - UNKNOWN: Insufficient data
    """
    name = "narrative_classifier"
    category = NodeCategory.ENRICH
    description = "AI-powered narrative classification with real news context"
    config_schema = {
        "max_tickers": {"type": "int", "default": 15},
        "fetch_news": {"type": "bool", "default": True, "description": "Fetch real news before classifying"},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            max_tickers = self.get_config_value("max_tickers", 15)
            fetch_news = self.get_config_value("fetch_news", True)
            
            if "symbol" not in df.columns:
                return NodeResult(success=False, error="symbol column required")
            
            llm_client = self.context.get("llm_client")
            if not llm_client:
                df["narrative"] = "UNKNOWN"
                df["narrative_confidence"] = 0.0
                df["narrative_reason"] = "No LLM available"
                return NodeResult(success=True, data=df)
            
            # Initialize columns
            df["narrative"] = "UNKNOWN"
            df["narrative_confidence"] = 0.0
            df["narrative_reason"] = ""
            
            tickers = df["symbol"].head(max_tickers).tolist()
            
            # STEP 1: Gather context for each ticker
            ticker_contexts = {}
            
            # Check if we already have news data
            has_existing_news = "news_summary" in df.columns and df["has_news"].any() if "has_news" in df.columns else False
            
            if has_existing_news:
                # Use existing news data
                for ticker in tickers:
                    row = df[df["symbol"] == ticker].iloc[0]
                    ticker_contexts[ticker] = {
                        "has_news": row.get("has_news", False),
                        "headline": row.get("latest_headline", ""),
                        "summary": row.get("news_summary", "")
                    }
                self.logger.info("using_existing_news_data", tickers=len(tickers))
            
            elif fetch_news:
                # FETCH REAL NEWS - This is the key improvement
                self.logger.info("fetching_real_news", tickers=len(tickers))
                
                news_tasks = [self._quick_news_search(ticker) for ticker in tickers]
                news_results = await asyncio.gather(*news_tasks, return_exceptions=True)
                
                for ticker, news in zip(tickers, news_results):
                    if isinstance(news, Exception):
                        ticker_contexts[ticker] = {"has_news": False, "headline": "", "summary": ""}
                    else:
                        ticker_contexts[ticker] = news
            else:
                # No news context
                for ticker in tickers:
                    ticker_contexts[ticker] = {"has_news": False, "headline": "", "summary": ""}
            
            # STEP 2: Build comprehensive prompt with context
            ticker_data_lines = []
            for ticker in tickers:
                row = df[df["symbol"] == ticker].iloc[0]
                ctx = ticker_contexts.get(ticker, {})
                
                line = f"• {ticker}: "
                
                # Price data
                if "change_percent" in df.columns:
                    chg = row.get("change_percent", 0) or 0
                    line += f"Change={chg:+.1f}%, "
                if "rvol" in df.columns:
                    rvol = row.get("rvol", 0) or 0
                    line += f"RelVol={rvol:.1f}x, "
                if "volume_today" in df.columns:
                    vol = row.get("volume_today", 0) or 0
                    line += f"Vol={vol/1e6:.1f}M, "
                if "sector" in df.columns:
                    line += f"Sector={row.get('sector', 'N/A')}"
                
                # NEWS CONTEXT - This is crucial
                if ctx.get("has_news") and ctx.get("headline"):
                    line += f"\n  → NEWS: {ctx['headline'][:100]}"
                else:
                    line += "\n  → NO NEWS FOUND"
                
                ticker_data_lines.append(line)
            
            # STEP 3: Classification with context
            prompt = f"""You are a financial analyst classifying stock movements based on data AND news context.

STOCKS TO CLASSIFY:
{chr(10).join(ticker_data_lines)}

CLASSIFICATION RULES:
1. CATALYST_DRIVEN: CONFIRMED news explains the move (FDA, earnings, M&A, contract)
2. MACRO_SECTOR: Move follows sector/market trend, no company-specific news
3. SILENT_ACCUMULATION: High volume (RelVol>3x) + big move + NO NEWS = suspicious
4. EARNINGS_PLAY: Near earnings date, IV expansion, anticipation
5. TECHNICAL: Chart pattern, support/resistance, no fundamental catalyst
6. UNKNOWN: Cannot determine with confidence

IMPORTANT:
- If there IS news that explains the move → CATALYST_DRIVEN
- If there is NO news but big volume → SILENT_ACCUMULATION (potential insider activity)
- Be specific in your reason

OUTPUT FORMAT (one per line):
TICKER|CATEGORY|CONFIDENCE(0.0-1.0)|REASON

Example:
NVDA|CATALYST_DRIVEN|0.95|CES AI announcement drove buying
XYZZ|SILENT_ACCUMULATION|0.85|+40% on 10x volume with no news - suspicious"""

            try:
                from google.genai import types
                
                response = llm_client.client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2000)
                )
                
                # Parse response
                for line in response.text.strip().split("\n"):
                    line = line.strip()
                    if not line or "|" not in line:
                        continue
                    
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 2:
                        continue
                    
                    ticker = parts[0].upper()
                    narrative = parts[1].upper()
                    
                    # Normalize
                    if "CATALYST" in narrative:
                        narrative = "CATALYST_DRIVEN"
                    elif "MACRO" in narrative or "SECTOR" in narrative:
                        narrative = "MACRO_SECTOR"
                    elif "SILENT" in narrative or "ACCUMULATION" in narrative:
                        narrative = "SILENT_ACCUMULATION"
                    elif "EARNING" in narrative:
                        narrative = "EARNINGS_PLAY"
                    elif "TECHNICAL" in narrative:
                        narrative = "TECHNICAL"
                    else:
                        narrative = "UNKNOWN"
                    
                    try:
                        confidence = float(parts[2]) if len(parts) > 2 else 0.5
                    except:
                        confidence = 0.5
                    
                    reason = parts[3][:150] if len(parts) > 3 else ""
                    
                    mask = df["symbol"] == ticker
                    if mask.any():
                        df.loc[mask, "narrative"] = narrative
                        df.loc[mask, "narrative_confidence"] = min(1.0, max(0.0, confidence))
                        df.loc[mask, "narrative_reason"] = reason
                        
            except Exception as e:
                self.logger.error("narrative_llm_error", error=str(e))
            
            classified = int((df["narrative"] != "UNKNOWN").sum())
            self.logger.info("narrative_classifier_complete", classified=classified, total=len(tickers))
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"classified": classified, "total": len(tickers), "news_fetched": fetch_news}
            )
            
        except Exception as e:
            self.logger.error("narrative_classifier_error", error=str(e))
            return NodeResult(success=False, error=str(e))
    
    async def _quick_news_search(self, ticker: str) -> Dict[str, Any]:
        """Quick news search using Grok - optimized for batch processing."""
        try:
            from research.grok_research import research_ticker
            
            # Fast, focused query
            result = await research_ticker(
                ticker=ticker,
                query=f"Why is {ticker} stock moving today? Latest news catalyst"
            )
            
            if result.get("success") and result.get("content"):
                content = result["content"]
                # Extract first sentence as headline
                first_sentence = content.split(".")[0] + "." if "." in content else content[:100]
                return {
                    "has_news": True,
                    "headline": first_sentence[:150],
                    "summary": content[:300]
                }
            return {"has_news": False, "headline": "", "summary": ""}
        except:
            return {"has_news": False, "headline": "", "summary": ""}


class RiskScorerNode(NodeBase):
    """
    AUTONOMOUS Risk Scorer with real event detection.
    
    Searches for actual upcoming events:
    - Earnings dates
    - FDA decisions
    - Merger votes
    - Lock-up expirations
    - Conference presentations
    """
    name = "risk_scorer"
    category = NodeCategory.ENRICH
    description = "Score risk based on real upcoming binary events"
    config_schema = {
        "max_tickers": {"type": "int", "default": 15},
        "risk_window_days": {"type": "int", "default": 7},
        "fetch_events": {"type": "bool", "default": True},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            max_tickers = self.get_config_value("max_tickers", 15)
            fetch_events = self.get_config_value("fetch_events", True)
            
            if "symbol" not in df.columns:
                return NodeResult(success=False, error="symbol column required")
            
            # Initialize risk columns
            df["risk_score"] = 0.5
            df["has_binary_event"] = False
            df["risk_factors"] = ""
            df["event_date"] = ""
            
            llm_client = self.context.get("llm_client")
            if not llm_client:
                return NodeResult(success=True, data=df, metadata={"llm_available": False})
            
            tickers = df["symbol"].head(max_tickers).tolist()
            
            # STEP 1: Fetch real event data
            event_data = {}
            
            if fetch_events:
                self.logger.info("fetching_event_data", tickers=len(tickers))
                event_tasks = [self._search_events(ticker) for ticker in tickers]
                event_results = await asyncio.gather(*event_tasks, return_exceptions=True)
                
                for ticker, events in zip(tickers, event_results):
                    if isinstance(events, Exception):
                        event_data[ticker] = {"has_event": False, "details": ""}
                    else:
                        event_data[ticker] = events
            
            # STEP 2: Build prompt with event context
            ticker_lines = []
            for ticker in tickers:
                row = df[df["symbol"] == ticker].iloc[0]
                evt = event_data.get(ticker, {})
                
                line = f"• {ticker}"
                if "change_percent" in df.columns:
                    line += f" (Today: {row.get('change_percent', 0):+.1f}%)"
                
                if evt.get("has_event") and evt.get("details"):
                    line += f"\n  → EVENTS: {evt['details'][:150]}"
                else:
                    line += "\n  → No upcoming events found"
                
                ticker_lines.append(line)
            
            prompt = f"""Analyze risk for these stocks based on upcoming binary events in the next 7 days.

STOCKS:
{chr(10).join(ticker_lines)}

RISK FACTORS TO CONSIDER:
- Earnings release (HIGH RISK)
- FDA decision date (VERY HIGH RISK)
- Merger/acquisition vote (HIGH RISK)
- Lock-up expiration (MEDIUM RISK)
- Conference/presentation (LOW RISK)
- No events (LOW RISK)

OUTPUT FORMAT (one per line):
TICKER|RISK_SCORE(0.0-1.0)|HAS_BINARY_EVENT(true/false)|EVENT_DATE_IF_KNOWN|RISK_FACTORS

Example:
NVDA|0.7|true|2026-01-15|Earnings Jan 15
AAPL|0.2|false||No near-term events"""

            try:
                from google.genai import types
                
                response = llm_client.client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=2000)
                )
                
                for line in response.text.strip().split("\n"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 3:
                        continue
                    
                    ticker = parts[0].upper()
                    try:
                        risk_score = float(parts[1])
                    except:
                        risk_score = 0.5
                    
                    has_event = parts[2].lower() == "true"
                    event_date = parts[3] if len(parts) > 3 else ""
                    factors = parts[4][:100] if len(parts) > 4 else ""
                    
                    mask = df["symbol"] == ticker
                    if mask.any():
                        df.loc[mask, "risk_score"] = min(1.0, max(0.0, risk_score))
                        df.loc[mask, "has_binary_event"] = has_event
                        df.loc[mask, "event_date"] = event_date
                        df.loc[mask, "risk_factors"] = factors
                        
            except Exception as e:
                self.logger.error("risk_scorer_llm_error", error=str(e))
            
            high_risk = int((df["risk_score"] >= 0.7).sum())
            self.logger.info("risk_scorer_complete", scored=len(tickers), high_risk=high_risk)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"scored": len(tickers), "high_risk_count": high_risk}
            )
            
        except Exception as e:
            self.logger.error("risk_scorer_error", error=str(e))
            return NodeResult(success=False, error=str(e))
    
    async def _search_events(self, ticker: str) -> Dict[str, Any]:
        """Search for upcoming events using Grok."""
        try:
            from research.grok_research import research_ticker
            
            result = await research_ticker(
                ticker=ticker,
                query=f"{ticker} upcoming earnings date FDA decision merger vote next 7 days"
            )
            
            if result.get("success") and result.get("content"):
                content = result["content"].lower()
                # Check for event keywords
                has_event = any(kw in content for kw in [
                    "earnings", "fda", "merger", "acquisition", "vote", 
                    "lock-up", "lockup", "conference", "presentation"
                ])
                return {
                    "has_event": has_event,
                    "details": result["content"][:200]
                }
            return {"has_event": False, "details": ""}
        except:
            return {"has_event": False, "details": ""}


class SentimentScorerNode(NodeBase):
    """
    Score sentiment from news and social data.
    Works best AFTER NewsEnricher or NarrativeClassifier.
    """
    name = "sentiment_scorer"
    category = NodeCategory.ENRICH
    description = "Score market sentiment from news context"
    config_schema = {
        "max_tickers": {"type": "int", "default": 20},
    }
    
    async def execute(self, input_data: Optional[pd.DataFrame] = None) -> NodeResult:
        if not self.validate_input(input_data):
            return NodeResult(success=False, error="Input data required")
        
        try:
            df = input_data.copy()
            max_tickers = self.get_config_value("max_tickers", 20)
            
            if "symbol" not in df.columns:
                return NodeResult(success=False, error="symbol column required")
            
            # Initialize columns
            df["sentiment_score"] = 0.0  # -1 (bearish) to +1 (bullish)
            df["sentiment_label"] = "NEUTRAL"
            
            llm_client = self.context.get("llm_client")
            if not llm_client:
                return NodeResult(success=True, data=df, metadata={"llm_available": False})
            
            tickers = df["symbol"].head(max_tickers).tolist()
            
            # Build context from available data
            ticker_lines = []
            for ticker in tickers:
                row = df[df["symbol"] == ticker].iloc[0]
                
                line = f"• {ticker}: "
                if "change_percent" in df.columns:
                    line += f"Change={row.get('change_percent', 0):+.1f}%, "
                
                # Use narrative reason if available
                if "narrative_reason" in df.columns and row.get("narrative_reason"):
                    line += f"Context: {row['narrative_reason'][:100]}"
                elif "news_summary" in df.columns and row.get("news_summary"):
                    line += f"News: {row['news_summary'][:100]}"
                elif "latest_headline" in df.columns and row.get("latest_headline"):
                    line += f"Headline: {row['latest_headline'][:100]}"
                else:
                    line += "No context available"
                
                ticker_lines.append(line)
            
            prompt = f"""Score market sentiment for each stock based on context.

STOCKS:
{chr(10).join(ticker_lines)}

SCORING:
- Positive news, beats, upgrades, strong moves up → BULLISH (+0.5 to +1.0)
- Negative news, misses, downgrades, crashes → BEARISH (-1.0 to -0.5)
- Mixed or no clear signal → NEUTRAL (-0.5 to +0.5)

OUTPUT FORMAT (one per line):
TICKER|SCORE(-1.0 to 1.0)|LABEL(BULLISH/BEARISH/NEUTRAL)

Example:
NVDA|0.8|BULLISH
AAPL|-0.3|NEUTRAL"""

            try:
                from google.genai import types
                
                response = llm_client.client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
                    config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=1000)
                )
                
                for line in response.text.strip().split("\n"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 2:
                        continue
                    
                    ticker = parts[0].upper()
                    try:
                        score = float(parts[1])
                    except:
                        score = 0.0
                    
                    label = parts[2].upper() if len(parts) > 2 else "NEUTRAL"
                    if label not in ["BULLISH", "BEARISH", "NEUTRAL"]:
                        label = "BULLISH" if score > 0.3 else "BEARISH" if score < -0.3 else "NEUTRAL"
                    
                    mask = df["symbol"] == ticker
                    if mask.any():
                        df.loc[mask, "sentiment_score"] = min(1.0, max(-1.0, score))
                        df.loc[mask, "sentiment_label"] = label
                        
            except Exception as e:
                self.logger.error("sentiment_llm_error", error=str(e))
            
            bullish = int((df["sentiment_label"] == "BULLISH").sum())
            bearish = int((df["sentiment_label"] == "BEARISH").sum())
            
            self.logger.info("sentiment_scorer_complete", bullish=bullish, bearish=bearish)
            
            return NodeResult(
                success=True,
                data=df,
                metadata={"bullish": bullish, "bearish": bearish, "neutral": len(tickers) - bullish - bearish}
            )
            
        except Exception as e:
            self.logger.error("sentiment_scorer_error", error=str(e))
            return NodeResult(success=False, error=str(e))


# Registry
ENRICH_NODES = {
    "news_enricher": NewsEnricherNode,
    "narrative_classifier": NarrativeClassifierNode,
    "risk_scorer": RiskScorerNode,
    "sentiment_scorer": SentimentScorerNode,
}
