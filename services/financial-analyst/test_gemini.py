#!/usr/bin/env python3
"""Test Gemini with Google Search"""

import os
import json
from google import genai
from google.genai.types import Tool, GoogleSearch

client = genai.Client(api_key=os.getenv('GOOGL_API_KEY'))
google_search_tool = Tool(google_search=GoogleSearch())

prompt = """Generate a financial report for NVDA. Use Google Search for real-time data.

Return ONLY valid JSON (no markdown, no code blocks) with this structure:
{
    "ticker": "NVDA",
    "company_name": "Full company name",
    "sector": "Technology",
    "business_summary": "2-3 sentences about what the company does",
    "consensus_rating": "Strong Buy/Buy/Hold/Sell",
    "average_price_target": 150.00,
    "price_target_high": 180.00,
    "price_target_low": 120.00,
    "pe_ratio": 25.5,
    "dividend_yield": 0.5,
    "risk_sentiment": "Bullish/Neutral/Bearish",
    "critical_event": "Most important recent news or null"
}"""

print("Generating report for NVDA...")

response = client.models.generate_content(
    model='gemini-2.0-flash-exp',
    contents=prompt,
    config={'tools': [google_search_tool]}
)

text = response.text
print("\n=== Raw Response ===")
print(text[:500])

# Clean markdown if present
if "```json" in text:
    text = text.split("```json")[1].split("```")[0]
elif "```" in text:
    text = text.split("```")[1].split("```")[0]

print("\n=== Parsed JSON ===")
data = json.loads(text.strip())
print(json.dumps(data, indent=2))

