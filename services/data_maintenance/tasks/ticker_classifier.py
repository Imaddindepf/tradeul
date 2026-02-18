"""
Ticker Classifier — Dual-Layer Classification System (GICS + Thematic Tags)

Batch job that classifies every ticker in the universe using Gemini 3 Pro.
Produces two outputs per ticker:
  Layer 1: GICS-based structural classification (sector → industry → sub_industry)
  Layer 2: Multi-label thematic tags with relevance scores

Architecture:
  1. Load all ticker metadata from tickers_unified
  2. Process in batches of 20 via Gemini 3 Pro (structured JSON output)
  3. Post-validate against canonical taxonomies
  4. Upsert into ticker_classification + ticker_themes tables

Design principles:
  - Revenue-primary classification (GICS 60% rule)
  - One ticker = one structural classification (no duplicates)
  - One ticker = 0..N thematic tags (multi-label)
  - Non-operating entities (funds, SPACs, shells) flagged as is_operating=false
  - Deterministic: same input → same output (temperature=0)
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL GICS TAXONOMY (February 2025 official + trader-oriented naming)
# Source: MSCI/S&P GICS Methodology February 2025
# ═══════════════════════════════════════════════════════════════════════════════

GICS_SECTORS = [
    "Energy",
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Information Technology",
    "Communication Services",
    "Utilities",
    "Real Estate",
]

GICS_TAXONOMY: Dict[str, Dict[str, List[str]]] = {
    # ── ENERGY ──────────────────────────────────────────────────────────────
    "Energy": {
        "Energy Equipment & Services": [
            "Oil & Gas Drilling",
            "Oil & Gas Equipment & Services",
        ],
        "Oil, Gas & Consumable Fuels": [
            "Integrated Oil & Gas",
            "Oil & Gas Exploration & Production",
            "Oil & Gas Refining & Marketing",
            "Oil & Gas Storage & Transportation",
            "Coal & Consumable Fuels",
        ],
    },
    # ── MATERIALS ───────────────────────────────────────────────────────────
    "Materials": {
        "Chemicals": [
            "Commodity Chemicals",
            "Diversified Chemicals",
            "Fertilizers & Agricultural Chemicals",
            "Industrial Gases",
            "Specialty Chemicals",
        ],
        "Construction Materials": [
            "Construction Materials",
        ],
        "Containers & Packaging": [
            "Metal, Glass & Plastic Containers",
            "Paper & Plastic Packaging Products & Materials",
        ],
        "Metals & Mining": [
            "Aluminum",
            "Diversified Metals & Mining",
            "Copper",
            "Gold",
            "Precious Metals & Minerals",
            "Silver",
            "Steel",
        ],
        "Paper & Forest Products": [
            "Forest Products",
            "Paper Products",
        ],
    },
    # ── INDUSTRIALS ─────────────────────────────────────────────────────────
    "Industrials": {
        "Aerospace & Defense": [
            "Aerospace & Defense",
        ],
        "Building Products": [
            "Building Products",
        ],
        "Construction & Engineering": [
            "Construction & Engineering",
        ],
        "Electrical Equipment": [
            "Electrical Components & Equipment",
            "Heavy Electrical Equipment",
        ],
        "Industrial Conglomerates": [
            "Industrial Conglomerates",
        ],
        "Machinery": [
            "Construction Machinery & Heavy Transportation Equipment",
            "Agricultural & Farm Machinery",
            "Industrial Machinery & Supplies & Components",
        ],
        "Trading Companies & Distributors": [
            "Trading Companies & Distributors",
        ],
        "Commercial Services & Supplies": [
            "Commercial Printing",
            "Environmental & Facilities Services",
            "Office Services & Supplies",
            "Diversified Support Services",
            "Security & Alarm Services",
        ],
        "Professional Services": [
            "Human Resource & Employment Services",
            "Research & Consulting Services",
            "Data Processing & Outsourced Services",
        ],
        "Air Freight & Logistics": [
            "Air Freight & Logistics",
        ],
        "Passenger Airlines": [
            "Passenger Airlines",
        ],
        "Marine Transportation": [
            "Marine Transportation",
        ],
        "Ground Transportation": [
            "Rail Transportation",
            "Cargo Ground Transportation",
            "Passenger Ground Transportation",
        ],
        "Transportation Infrastructure": [
            "Airport Services",
            "Highways & Railtracks",
            "Marine Ports & Services",
        ],
    },
    # ── CONSUMER DISCRETIONARY ──────────────────────────────────────────────
    "Consumer Discretionary": {
        "Automobile Components": [
            "Automotive Parts & Equipment",
            "Tires & Rubber",
        ],
        "Automobiles": [
            "Automobile Manufacturers",
            "Motorcycle Manufacturers",
        ],
        "Household Durables": [
            "Consumer Electronics",
            "Home Furnishings",
            "Homebuilding",
            "Household Appliances",
            "Housewares & Specialties",
        ],
        "Leisure Products": [
            "Leisure Products",
        ],
        "Textiles, Apparel & Luxury Goods": [
            "Apparel, Accessories & Luxury Goods",
            "Footwear",
            "Textiles",
        ],
        "Hotels, Restaurants & Leisure": [
            "Casinos & Gaming",
            "Hotels, Resorts & Cruise Lines",
            "Leisure Facilities",
            "Restaurants",
        ],
        "Diversified Consumer Services": [
            "Education Services",
            "Specialized Consumer Services",
        ],
        "Distributors": [
            "Distributors",
        ],
        "Broadline Retail": [
            "Broadline Retail",
        ],
        "Specialty Retail": [
            "Apparel Retail",
            "Computer & Electronics Retail",
            "Home Improvement Retail",
            "Other Specialty Retail",
            "Automotive Retail",
            "Homefurnishing Retail",
        ],
    },
    # ── CONSUMER STAPLES ────────────────────────────────────────────────────
    "Consumer Staples": {
        "Consumer Staples Distribution & Retail": [
            "Drug Retail",
            "Food Distributors",
            "Food Retail",
            "Consumer Staples Merchandise Retail",
        ],
        "Beverages": [
            "Brewers",
            "Distillers & Vintners",
            "Soft Drinks & Non-alcoholic Beverages",
        ],
        "Food Products": [
            "Agricultural Products & Services",
            "Packaged Foods & Meats",
        ],
        "Tobacco": [
            "Tobacco",
        ],
        "Household Products": [
            "Household Products",
        ],
        "Personal Care Products": [
            "Personal Care Products",
        ],
    },
    # ── HEALTH CARE ─────────────────────────────────────────────────────────
    "Health Care": {
        "Health Care Equipment & Supplies": [
            "Health Care Equipment",
            "Health Care Supplies",
        ],
        "Health Care Providers & Services": [
            "Health Care Distributors",
            "Health Care Services",
            "Health Care Facilities",
            "Managed Health Care",
        ],
        "Health Care Technology": [
            "Health Care Technology",
        ],
        "Biotechnology": [
            "Biotechnology",
        ],
        "Pharmaceuticals": [
            "Pharmaceuticals",
        ],
        "Life Sciences Tools & Services": [
            "Life Sciences Tools & Services",
        ],
    },
    # ── FINANCIALS ──────────────────────────────────────────────────────────
    "Financials": {
        "Banks": [
            "Diversified Banks",
            "Regional Banks",
        ],
        "Financial Services": [
            "Diversified Financial Services",
            "Multi-Sector Holdings",
            "Specialized Finance",
            "Commercial & Residential Mortgage Finance",
            "Transaction & Payment Processing Services",
        ],
        "Consumer Finance": [
            "Consumer Finance",
        ],
        "Capital Markets": [
            "Asset Management & Custody Banks",
            "Investment Banking & Brokerage",
            "Diversified Capital Markets",
            "Financial Exchanges & Data",
        ],
        "Mortgage REITs": [
            "Mortgage REITs",
        ],
        "Insurance": [
            "Insurance Brokers",
            "Life & Health Insurance",
            "Multi-line Insurance",
            "Property & Casualty Insurance",
            "Reinsurance",
        ],
    },
    # ── INFORMATION TECHNOLOGY ──────────────────────────────────────────────
    "Information Technology": {
        "IT Services": [
            "IT Consulting & Other Services",
            "Internet Services & Infrastructure",
        ],
        "Software": [
            "Application Software",
            "Systems Software",
        ],
        "Communications Equipment": [
            "Communications Equipment",
        ],
        "Technology Hardware, Storage & Peripherals": [
            "Technology Hardware, Storage & Peripherals",
        ],
        "Electronic Equipment, Instruments & Components": [
            "Electronic Equipment & Instruments",
            "Electronic Components",
            "Electronic Manufacturing Services",
            "Technology Distributors",
        ],
        "Semiconductors & Semiconductor Equipment": [
            "Semiconductor Materials & Equipment",
            "Semiconductors",
        ],
    },
    # ── COMMUNICATION SERVICES ──────────────────────────────────────────────
    "Communication Services": {
        "Diversified Telecommunication Services": [
            "Alternative Carriers",
            "Integrated Telecommunication Services",
        ],
        "Wireless Telecommunication Services": [
            "Wireless Telecommunication Services",
        ],
        "Media": [
            "Advertising",
            "Broadcasting",
            "Cable & Satellite",
            "Publishing",
        ],
        "Entertainment": [
            "Movies & Entertainment",
            "Interactive Home Entertainment",
        ],
        "Interactive Media & Services": [
            "Interactive Media & Services",
        ],
    },
    # ── UTILITIES ───────────────────────────────────────────────────────────
    "Utilities": {
        "Electric Utilities": [
            "Electric Utilities",
        ],
        "Gas Utilities": [
            "Gas Utilities",
        ],
        "Multi-Utilities": [
            "Multi-Utilities",
        ],
        "Water Utilities": [
            "Water Utilities",
        ],
        "Independent Power and Renewable Electricity Producers": [
            "Independent Power Producers & Energy Traders",
            "Renewable Electricity",
        ],
    },
    # ── REAL ESTATE ─────────────────────────────────────────────────────────
    "Real Estate": {
        "Diversified REITs": [
            "Diversified REITs",
        ],
        "Industrial REITs": [
            "Industrial REITs",
        ],
        "Hotel & Resort REITs": [
            "Hotel & Resort REITs",
        ],
        "Office REITs": [
            "Office REITs",
        ],
        "Health Care REITs": [
            "Health Care REITs",
        ],
        "Residential REITs": [
            "Multi-Family Residential REITs",
            "Single-Family Residential REITs",
        ],
        "Retail REITs": [
            "Retail REITs",
        ],
        "Specialized REITs": [
            "Other Specialized REITs",
            "Self-Storage REITs",
            "Telecom Tower REITs",
            "Timber REITs",
            "Data Center REITs",
        ],
        "Real Estate Management & Development": [
            "Diversified Real Estate Activities",
            "Real Estate Operating Companies",
            "Real Estate Development",
            "Real Estate Services",
        ],
    },
}

# Build flat sets for validation
ALL_INDUSTRIES: Set[str] = set()
ALL_SUB_INDUSTRIES: Set[str] = set()
SUB_TO_INDUSTRY: Dict[str, str] = {}
for sector, industries in GICS_TAXONOMY.items():
    for industry, subs in industries.items():
        ALL_INDUSTRIES.add(industry)
        ALL_SUB_INDUSTRIES.update(subs)
        for sub in subs:
            SUB_TO_INDUSTRY[sub] = industry


# ═══════════════════════════════════════════════════════════════════════════════
# THEMATIC TAGS CATALOG
# Based on Global X Thematic Framework + 2025-2026 trading themes
# ═══════════════════════════════════════════════════════════════════════════════

THEMATIC_CATALOG: Dict[str, List[str]] = {
    # ── SEMICONDUCTORS ──────────────────────────────────────────────────────
    "semiconductors": [
        "semiconductors",               # broad: any chip company
        "semiconductor_equipment",       # ASML, LRCX, KLAC, AMAT
        "memory_chips",                  # MU, SNDK, WDC — DRAM, NAND, SSD
        "gpu_accelerators",              # NVDA, AMD — GPUs, AI accelerators
        "cpu_processors",                # INTC, AMD — x86/ARM processors
        "analog_mixed_signal",           # TXN, ADI, MCHP, ON — analog/power ICs
        "networking_chips",              # AVGO, MRVL — ethernet, switching ASICs
        "rf_wireless_chips",             # QCOM, SWKS, QRVO — RF, modem, 5G chips
        "chip_foundry",                  # TSM, GFS, UMC — contract fabrication
        "power_semiconductors",          # ON, WOLF, DIOD — SiC, GaN, IGBT
        "eda_chip_design",               # SNPS, CDNS, ARM — EDA tools, IP cores
    ],
    # ── AI & SOFTWARE ───────────────────────────────────────────────────────
    "ai_software": [
        "artificial_intelligence",       # broad AI play
        "generative_ai",                 # LLM, image gen — NVDA, MSFT, GOOG, META
        "machine_learning",              # ML infrastructure
        "data_infrastructure",           # SNOW, MDB, DDOG, PLTR — data platforms
        "cloud_computing",               # AWS/Azure/GCP infra plays
        "edge_computing",                # FSLY, NET — edge compute / CDN
        "saas",                          # broad SaaS
        "enterprise_software",           # SAP, ORCL, WDAY — ERP, HCM
        "crm_marketing_tech",            # CRM, HUBS, BRZE — customer platforms
        "developer_tools",               # GTLB, ESTC, DDOG — devops, CI/CD
        "big_data_analytics",            # analytics & BI
        "cybersecurity",                 # broad cybersec
        "identity_zero_trust",           # OKTA, CYBR, ZS — IAM, zero-trust
        "endpoint_network_security",     # CRWD, PANW, FTNT — endpoint/firewall
        "ar_vr",                         # META, AAPL, U — augmented/virtual reality
    ],
    # ── CONNECTIVITY & TELECOM ──────────────────────────────────────────────
    "connectivity": [
        "5g_iot",                        # 5G infra + IoT devices
        "satellite_internet",            # ASTS, GSAT, IRDM — LEO/GEO broadband
        "fiber_optics",                  # AAOI, LITE, COHR — optical components
    ],
    # ── ROBOTICS & AUTOMATION ───────────────────────────────────────────────
    "robotics_automation": [
        "robotics",                      # broad robotics
        "surgical_robotics",             # ISRG, MBOT — robotic surgery
        "industrial_automation",         # ROK, EMR, ABB — factory automation, PLCs
        "autonomous_vehicles",           # TSLA, GOOGL Waymo, GM Cruise
        "lidar",                         # LAZR, INVZ, OUST — lidar sensors
        "drones",                        # AVAV, JOBY, ACHR — UAV, eVTOL
        "3d_printing",                   # DDD, SSYS, DM — additive manufacturing
    ],
    # ── QUANTUM & FRONTIER ──────────────────────────────────────────────────
    "frontier_tech": [
        "quantum_computing",             # IONQ, RGTI, QBTS — quantum hardware/SW
        "blockchain_crypto",             # broad blockchain
        "crypto_exchange",               # COIN, HOOD crypto — trading platforms
        "space_technology",              # RKLB, SPCE, BA space — launch, satellites
    ],
    # ── FINTECH & FINANCIAL ─────────────────────────────────────────────────
    "fintech_financial": [
        "fintech",                       # broad fintech
        "digital_payments",              # V, MA, PYPL, SQ — payments processing
        "buy_now_pay_later",             # AFRM, SHOP — BNPL consumer credit
        "neobanking",                    # SOFI, NU — digital-first banks
        "insurtech",                     # LMND, ROOT, OSCR — digital insurance
        "lending_platforms",             # UPST, LC — AI/online lending
        "wealthtech",                    # robo-advisors, digital wealth
        "payroll_hr_tech",               # PAYC, PCTY, ADP — payroll, HCM
        "online_gambling",               # DKNG, FLUT, MGM — sports betting, iGaming
    ],
    # ── BIOTECH & PHARMA ────────────────────────────────────────────────────
    "biotech_pharma": [
        "biotech",                       # broad biotech
        "genomics",                      # ILMN, PACB — sequencing, genomic tools
        "gene_editing_crispr",           # CRSP, BEAM, NTLA — CRISPR, base editing
        "mrna_therapeutics",             # MRNA, BNTX — mRNA platform
        "cell_gene_therapy",             # BLUE, KRTX, ALNY — cell therapy, gene tx
        "immunotherapy",                 # BMY (Opdivo), MRK (Keytruda) — checkpoint, CAR-T
        "oncology",                      # broad cancer therapeutics
        "glp1_weight_loss",              # LLY, NVO, VKTX — GLP-1 agonists
        "diabetes",                      # DXCM, PODD, TNDM — diabetes devices/drugs
        "neuroscience",                  # BIIB, SAVA, AXSM — CNS, neuro disorders
        "cardiovascular",                # heart disease therapeutics
        "rare_disease",                  # orphan drugs
        "vaccines",                      # PFE, MRNA, NVAX — vaccine platforms
        "psychedelics",                  # CMPS, MNMD — psilocybin, MDMA therapy
        "cannabis",                      # TLRY, CGC — cannabis operators
    ],
    # ── MEDTECH & HEALTH SERVICES ───────────────────────────────────────────
    "medtech_health": [
        "digital_health",                # broad digital health
        "telehealth",                    # TDOC, AMWL — virtual care
        "medical_devices",               # MDT, SYK, ABT, BSX — devices, implants
        "diagnostics",                   # DGX, LH, EXAS — lab testing, liquid biopsy
        "medical_imaging",               # HOLX, ISRG vision, NUVA — imaging equipment
        "dental",                        # ALGN, XRAY, HSIC — dental tech & supplies
        "animal_health",                 # ZTS, IDXX — veterinary pharma/diagnostics
        "cro_cdmo",                      # ICLR, CRL, CTLT — contract research/manufacturing
        "aging_population",              # senior care, geriatric products
    ],
    # ── ENERGY: OIL & GAS ───────────────────────────────────────────────────
    "oil_gas": [
        "oil_exploration",               # upstream — XOM, CVX, PXD, FANG
        "oil_refining",                  # downstream — MPC, VLO, PSX
        "oil_services",                  # SLB, HAL, BKR — oilfield services
        "midstream_pipelines",           # KMI, WMB, ET, EPD — pipelines, MLPs
        "natural_gas",                   # LNG, EQT, AR — gas producers, LNG export
    ],
    # ── ENERGY: CLEAN & NUCLEAR ─────────────────────────────────────────────
    "clean_energy": [
        "clean_energy",                  # broad renewables
        "solar",                         # FSLR, ENPH, SEDG, RUN — solar panels/inverters
        "wind",                          # NEE, CWEN, ORA — wind turbines/farms
        "nuclear_energy",                # CEG, VST — nuclear power operators
        "uranium",                       # CCJ, DNN, LEU — uranium miners/enrichment
        "hydrogen_fuel_cells",           # PLUG, BE, FCEL — green hydrogen
        "battery_storage",               # QS, MVST, AMPS — grid/EV batteries
        "lithium",                       # ALB, SQM, LAC — lithium miners
        "carbon_capture",                # AIRS, etc. — CCS technology
        "smart_grid",                    # ITRI, GNRC — grid modernization, meters
    ],
    # ── TRANSPORTATION & EVs ────────────────────────────────────────────────
    "transportation": [
        "electric_vehicles",             # TSLA, RIVN, LCID — EV manufacturers
        "ev_charging",                   # CHPT, BLNK, EVGO — charging networks
        "ride_sharing",                  # UBER, LYFT — mobility-as-a-service
        "shipping",                      # ZIM, SBLK, DAC — ocean freight, tankers
        "rails_freight",                 # UNP, CSX, NSC — rail operators
        "airlines",                      # DAL, UAL, LUV — passenger airlines
    ],
    # ── MINING & MATERIALS ──────────────────────────────────────────────────
    "mining_materials": [
        "gold_mining",                   # NEM, GOLD, AEM — gold miners
        "silver_mining",                 # PAAS, HL, AG — silver miners
        "copper",                        # FCX, SCCO — copper producers
        "rare_earths",                   # MP, UUUU — rare-earth elements
        "steel",                         # NUE, STLD, CLF — steel producers
        "aluminum",                      # AA, CENX — aluminum smelters
        "agriculture_agtech",            # DE, AGCO, FMC — ag equipment, precision ag
    ],
    # ── CONSUMER DIGITAL ────────────────────────────────────────────────────
    "consumer_digital": [
        "e_commerce",                    # AMZN, SHOP, MELI — online retail
        "social_media",                  # META, SNAP, PINS — social platforms
        "streaming",                     # NFLX, DIS+, ROKU — video/audio streaming
        "esports_gaming",                # RBLX, EA, TTWO, U — gaming publishers/platforms
        "food_delivery",                 # DASH, UBER Eats — delivery platforms
        "education_tech",                # DUOL, CHGG, COUR — edtech
    ],
    # ── CONSUMER LIFESTYLE ──────────────────────────────────────────────────
    "consumer_lifestyle": [
        "travel_tech",                   # BKNG, ABNB, EXPE — online travel
        "gig_economy",                   # FVRR, UPWK — freelance platforms
        "luxury_brands",                 # TPR, CPRI, RH — luxury goods
        "restaurant_tech",               # TOST, PAR — restaurant POS/platforms
        "pet_economy",                   # CHWY, WOOF, ZTS — pet products/services
        "athleisure_wellness",           # LULU, PTON, NKE — fitness/wellness
    ],
    # ── DEFENSE & AEROSPACE ─────────────────────────────────────────────────
    "defense_aerospace": [
        "defense_contractors",           # LMT, RTX, NOC, GD — prime defense
        "defense_tech",                  # PLTR, BWXT — defense software/tech
        "commercial_aerospace",          # BA, AIR, SPR — commercial aviation
        "hypersonics_missiles",          # LMT, RTX — hypersonic, missile systems
        "border_surveillance",           # FLIR, DRS — border/surveillance tech
    ],
    # ── INFRASTRUCTURE & INDUSTRIAL ─────────────────────────────────────────
    "industrial_infra": [
        "construction_engineering",      # CAT, DE, VMC, MLM — heavy equipment, materials
        "water_treatment",               # XYL, WMS, WTRG — water infrastructure
        "waste_management",              # WM, RSG, CLH — waste/recycling
    ],
    # ── REAL ESTATE VERTICALS ───────────────────────────────────────────────
    "real_estate_verticals": [
        "data_center_reits",             # EQIX, DLR — data center REITs
        "cell_tower_reits",              # AMT, CCI, SBAC — cell tower REITs
        "healthcare_reits",              # VTR, WELL, OHI — healthcare REITs
    ],
}

ALL_THEMES: Set[str] = set()
THEME_TO_CATEGORY: Dict[str, str] = {}
for category, themes in THEMATIC_CATALOG.items():
    ALL_THEMES.update(themes)
    for t in themes:
        THEME_TO_CATEGORY[t] = category


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_PROMPT = """\
You are a senior financial data analyst at MSCI. Classify each company below using EXACTLY the GICS taxonomy provided and assign thematic investment tags.

## CLASSIFICATION RULES (GICS methodology)
1. PRIMARY: Classify by the business activity generating >60% of revenue.
2. If no single activity >60%, use the activity providing majority of BOTH revenue AND earnings.
3. If diversified across 3+ sectors → use "Industrial Conglomerates" or "Multi-Sector Holdings".
4. SPACs, blank-check companies, shell companies → sector "Financials", industry "Specialized Finance", is_operating=false.
5. Closed-end funds, BDCs, ETNs, investment trusts, asset management vehicles → sector "Financials", industry "Asset Management & Custody Banks", is_operating=false.
6. company_name_clean: Remove suffixes like "Inc.", "Corp.", "Ltd.", "Common Stock", "Class A", etc. Keep the essential brand name.

## THEMATIC TAGS RULES
1. Assign 0-8 thematic tags per company. ONLY from the CANONICAL list below.
2. A tag applies ONLY if the company derives meaningful revenue from that area OR is widely recognized by investors as part of that theme.
3. For each tag, assign a relevance score (0.50-1.00): 1.00 = core business, 0.70 = significant segment, 0.50 = emerging/minor exposure.
4. Do NOT over-tag. If unsure, skip the tag. Precision > recall.
5. Funds/SPACs/shells: assign zero thematic tags (empty array).

## GICS SECTORS (pick ONE)
{sectors}

## GICS TAXONOMY (sector → industry → sub_industry)
{taxonomy}

## THEMATIC TAGS CATALOG (category: tags)
{themes}

## COMPANIES TO CLASSIFY
{companies}

## OUTPUT FORMAT — Return ONLY a JSON array:
[
  {{
    "symbol": "AAPL",
    "sector": "Information Technology",
    "industry": "Technology Hardware, Storage & Peripherals",
    "sub_industry": "Technology Hardware, Storage & Peripherals",
    "company_name_clean": "Apple",
    "is_operating": true,
    "themes": [
      {{"tag": "semiconductors", "relevance": 0.60}},
      {{"tag": "artificial_intelligence", "relevance": 0.70}}
    ]
  }}
]

CRITICAL: Every field MUST use values from the taxonomies above. Do NOT invent new sectors, industries, sub-industries, or themes."""


def _build_taxonomy_text() -> str:
    lines = []
    for sector, industries in GICS_TAXONOMY.items():
        lines.append(f"\n### {sector}")
        for industry, subs in industries.items():
            sub_list = ", ".join(subs)
            lines.append(f"  {industry}: [{sub_list}]")
    return "\n".join(lines)


def _build_themes_text() -> str:
    lines = []
    for category, themes in THEMATIC_CATALOG.items():
        lines.append(f"  {category}: {', '.join(themes)}")
    return "\n".join(lines)


def _build_company_block(companies: List[Dict]) -> str:
    lines = []
    for c in companies:
        desc = (c.get("description") or "")[:400]
        lines.append(
            f"- {c['symbol']}: {c.get('company_name', 'N/A')} | "
            f"SIC Industry: {c.get('industry', 'N/A')} | "
            f"SIC Sector: {c.get('sector', 'N/A')} | "
            f"Market Cap: {c.get('market_cap', 'N/A')} | "
            f"Desc: {desc}"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# LLM BATCH PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

GOOGLE_API_KEY = os.getenv('GOOGL_API_KEY', os.getenv('GOOGLE_API_KEY', ''))

TAXONOMY_TEXT = _build_taxonomy_text()
THEMES_TEXT = _build_themes_text()
SECTORS_TEXT = "\n".join(f"  - {s}" for s in GICS_SECTORS)


def _build_response_schema():
    """Build Gemini response_schema for structured JSON output."""
    from google.genai import types

    theme_schema = types.Schema(
        type='OBJECT',
        properties={
            'tag': types.Schema(type='STRING'),
            'relevance': types.Schema(type='NUMBER'),
        },
        required=['tag', 'relevance'],
    )

    item_schema = types.Schema(
        type='OBJECT',
        properties={
            'symbol': types.Schema(type='STRING'),
            'sector': types.Schema(type='STRING'),
            'industry': types.Schema(type='STRING'),
            'sub_industry': types.Schema(type='STRING'),
            'company_name_clean': types.Schema(type='STRING'),
            'is_operating': types.Schema(type='BOOLEAN'),
            'themes': types.Schema(type='ARRAY', items=theme_schema),
        },
        required=['symbol', 'sector', 'industry', 'sub_industry',
                  'company_name_clean', 'is_operating', 'themes'],
    )

    return types.Schema(type='ARRAY', items=item_schema)


_RESPONSE_SCHEMA = None


def _get_response_schema():
    global _RESPONSE_SCHEMA
    if _RESPONSE_SCHEMA is None:
        _RESPONSE_SCHEMA = _build_response_schema()
    return _RESPONSE_SCHEMA


async def _classify_batch(companies: List[Dict], genai_client) -> List[Dict]:
    """Classify a batch of companies using Gemini 3 Pro with structured output."""
    from google.genai import types

    prompt = CLASSIFICATION_PROMPT.format(
        sectors=SECTORS_TEXT,
        taxonomy=TAXONOMY_TEXT,
        themes=THEMES_TEXT,
        companies=_build_company_block(companies),
    )

    try:
        response = await genai_client.aio.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=32768,
                response_mime_type='application/json',
                response_schema=_get_response_schema(),
                thinking_config=types.ThinkingConfig(thinking_budget=2048),
            ),
        )

        if response.text is None:
            finish = (response.candidates[0].finish_reason
                      if response.candidates else "unknown")
            logger.warning("classifier_empty_response: finish_reason=%s", finish)
            return []

        result = json.loads(response.text)

        if isinstance(result, dict) and len(result) == 1:
            result = list(result.values())[0]

        if not isinstance(result, list):
            logger.warning("classifier_unexpected_format: type=%s", type(result).__name__)
            return []

        return _validate_results(result)

    except json.JSONDecodeError as e:
        logger.error("classifier_json_error: %s", str(e))
        return []
    except Exception as e:
        logger.error("classifier_llm_error: %s (%s)", str(e), type(e).__name__)
        return []


def _validate_results(results: List[Dict]) -> List[Dict]:
    """Post-validate LLM output against canonical taxonomies."""
    validated = []
    for item in results:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol", "").upper().strip()
        sector = item.get("sector", "").strip()
        industry = item.get("industry", "").strip()
        sub_industry = item.get("sub_industry", "").strip()

        if not symbol or not sector or not industry:
            logger.warning("classifier_missing_fields: symbol=%s", symbol)
            continue

        if sector not in GICS_SECTORS:
            logger.warning("classifier_invalid_sector: symbol=%s sector=%s", symbol, sector)
            continue

        if industry not in ALL_INDUSTRIES:
            closest = _find_closest(industry, ALL_INDUSTRIES)
            if closest:
                logger.debug("classifier_industry_corrected: %s → %s", industry, closest)
                industry = closest
            elif industry in SUB_TO_INDUSTRY:
                sub_industry = industry
                industry = SUB_TO_INDUSTRY[industry]
                logger.debug("classifier_sub_as_industry_fixed: %s → industry=%s sub=%s",
                             symbol, industry, sub_industry)
            else:
                logger.warning("classifier_invalid_industry: symbol=%s industry=%s", symbol, industry)
                continue

        if sub_industry and sub_industry not in ALL_SUB_INDUSTRIES:
            closest = _find_closest(sub_industry, ALL_SUB_INDUSTRIES)
            if closest:
                sub_industry = closest

        themes = []
        raw_themes = item.get("themes", [])
        if isinstance(raw_themes, list):
            for t in raw_themes:
                if isinstance(t, dict):
                    tag = t.get("tag", "").strip()
                    rel = t.get("relevance", 1.0)
                    if tag in ALL_THEMES:
                        themes.append({
                            "tag": tag,
                            "relevance": min(1.0, max(0.0, float(rel))),
                            "category": THEME_TO_CATEGORY.get(tag, ""),
                        })
                    else:
                        logger.debug("classifier_invalid_theme: symbol=%s tag=%s", symbol, tag)

        validated.append({
            "symbol": symbol,
            "sector": sector,
            "industry": industry,
            "sub_industry": sub_industry,
            "company_name_clean": item.get("company_name_clean", "").strip(),
            "is_operating": item.get("is_operating", True),
            "themes": themes,
        })

    return validated


def _find_closest(value: str, valid_set: Set[str]) -> Optional[str]:
    """Find closest match by case-insensitive exact comparison only.

    Avoids aggressive partial matching that could map
    'Asset Management & Custody Banks' → 'Banks'.
    """
    value_lower = value.lower().strip()
    for v in valid_set:
        if v.lower() == value_lower:
            return v
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def _upsert_classifications(conn, results: List[Dict]) -> Tuple[int, int]:
    """Upsert classification results into both tables."""
    classifications = 0
    theme_tags = 0

    for item in results:
        sym = item["symbol"]

        await conn.execute("""
            INSERT INTO ticker_classification
                (symbol, sector, industry_group, industry, sub_industry,
                 company_name_clean, is_operating, source, confidence, classified_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'gemini_3_pro', $8, NOW(), NOW())
            ON CONFLICT (symbol) DO UPDATE SET
                sector = EXCLUDED.sector,
                industry_group = EXCLUDED.industry_group,
                industry = EXCLUDED.industry,
                sub_industry = EXCLUDED.sub_industry,
                company_name_clean = EXCLUDED.company_name_clean,
                is_operating = EXCLUDED.is_operating,
                source = EXCLUDED.source,
                confidence = EXCLUDED.confidence,
                updated_at = NOW()
        """,
            sym,
            item["sector"],
            _get_industry_group(item["sector"], item["industry"]),
            item["industry"],
            item.get("sub_industry") or None,
            item.get("company_name_clean") or None,
            item.get("is_operating", True),
            0.95,
        )
        classifications += 1

        if item.get("themes"):
            await conn.execute(
                "DELETE FROM ticker_themes WHERE symbol = $1", sym
            )
            for t in item["themes"]:
                await conn.execute("""
                    INSERT INTO ticker_themes (symbol, theme, relevance, theme_category, source, classified_at)
                    VALUES ($1, $2, $3, $4, 'gemini_3_pro', NOW())
                    ON CONFLICT (symbol, theme) DO UPDATE SET
                        relevance = EXCLUDED.relevance,
                        theme_category = EXCLUDED.theme_category,
                        source = EXCLUDED.source,
                        classified_at = NOW()
                """,
                    sym,
                    t["tag"],
                    t["relevance"],
                    t["category"],
                )
                theme_tags += 1

    return classifications, theme_tags


def _get_industry_group(sector: str, industry: str) -> Optional[str]:
    """Derive GICS industry_group from sector + industry."""
    sector_data = GICS_TAXONOMY.get(sector, {})
    if industry in sector_data:
        return industry
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN TASK
# ═══════════════════════════════════════════════════════════════════════════════

class TickerClassifierTask:
    """
    Batch job: classify all tickers using dual-layer GICS + thematic system.

    Tables written:
      ticker_classification — 1 row per ticker (GICS structural classification)
      ticker_themes         — 0..N rows per ticker (thematic tags with relevance)
    """

    name = "ticker_classifier"

    BATCH_SIZE = 20
    CONCURRENCY = 5
    MAX_RETRIES = 2

    def __init__(self, db_pool):
        self._pool = db_pool
        self._genai_client = None

    def _get_genai_client(self):
        if self._genai_client is None:
            from google import genai
            api_key = GOOGLE_API_KEY
            if not api_key:
                raise RuntimeError("GOOGLE_API_KEY env var required for ticker classifier")
            self._genai_client = genai.Client(api_key=api_key)
        return self._genai_client

    async def execute(self, skip_classified: bool = True) -> Dict:
        """
        Execute full classification.

        Args:
            skip_classified: If True, skip tickers already in ticker_classification.
        """
        logger.info("ticker_classifier_starting")
        start_time = time.time()

        try:
            genai_client = self._get_genai_client()
        except RuntimeError as e:
            logger.error("ticker_classifier_no_api_key: %s", str(e))
            return {"success": False, "error": str(e)}

        all_tickers = await self._load_tickers(skip_classified)
        if not all_tickers:
            logger.info("ticker_classifier_nothing_to_classify")
            return {"success": True, "classified": 0, "message": "All tickers already classified"}

        logger.info("ticker_classifier_loaded: count=%d", len(all_tickers))

        batches = [
            all_tickers[i:i + self.BATCH_SIZE]
            for i in range(0, len(all_tickers), self.BATCH_SIZE)
        ]

        total_classifications = 0
        total_themes = 0
        errors = 0
        processed = 0
        semaphore = asyncio.Semaphore(self.CONCURRENCY)

        async def process_batch(batch: List[Dict]) -> None:
            nonlocal total_classifications, total_themes, errors, processed
            async with semaphore:
                for attempt in range(self.MAX_RETRIES + 1):
                    try:
                        results = await _classify_batch(batch, genai_client)
                        if results:
                            async with self._pool.acquire() as conn:
                                c, t = await _upsert_classifications(conn, results)
                                total_classifications += c
                                total_themes += t
                            break
                        elif attempt < self.MAX_RETRIES:
                            await asyncio.sleep(2 ** attempt)
                    except Exception as e:
                        if attempt == self.MAX_RETRIES:
                            errors += len(batch)
                            logger.error(
                                "ticker_classifier_batch_failed: %s symbols=%s",
                                str(e),
                                [c["symbol"] for c in batch],
                            )
                        else:
                            await asyncio.sleep(2 ** attempt)

                processed += len(batch)
                if processed % 200 == 0 or processed == len(all_tickers):
                    pct = round(processed / len(all_tickers) * 100, 1)
                    logger.info(
                        "ticker_classifier_progress: %d/%d (%.1f%%) classified=%d themes=%d errors=%d",
                        processed, len(all_tickers), pct,
                        total_classifications, total_themes, errors,
                    )

        await asyncio.gather(
            *[process_batch(b) for b in batches],
            return_exceptions=True,
        )

        elapsed = round(time.time() - start_time, 1)
        logger.info(
            "ticker_classifier_completed: classified=%d themes=%d errors=%d elapsed=%.1fs",
            total_classifications, total_themes, errors, elapsed,
        )

        return {
            "success": True,
            "tickers_loaded": len(all_tickers),
            "classified": total_classifications,
            "themes_assigned": total_themes,
            "errors": errors,
            "elapsed_seconds": elapsed,
        }

    async def _load_tickers(self, skip_classified: bool) -> List[Dict]:
        """Load tickers from tickers_unified, optionally skipping already classified."""
        async with self._pool.acquire() as conn:
            if skip_classified:
                rows = await conn.fetch("""
                    SELECT tu.symbol, tu.company_name, tu.sector, tu.industry,
                           tu.description, tu.market_cap, tu.is_etf
                    FROM tickers_unified tu
                    LEFT JOIN ticker_classification tc ON tu.symbol = tc.symbol
                    WHERE tu.is_active = true AND tc.symbol IS NULL
                    ORDER BY tu.market_cap DESC NULLS LAST
                """)
            else:
                rows = await conn.fetch("""
                    SELECT symbol, company_name, sector, industry,
                           description, market_cap, is_etf
                    FROM tickers_unified
                    WHERE is_active = true
                    ORDER BY market_cap DESC NULLS LAST
                """)

        return [
            {
                "symbol": r["symbol"],
                "company_name": r["company_name"] or "",
                "sector": r["sector"] or "",
                "industry": r["industry"] or "",
                "description": r["description"] or "",
                "market_cap": str(r["market_cap"]) if r["market_cap"] else "N/A",
            }
            for r in rows
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    """Run classification as standalone script."""
    import asyncpg

    db_host = os.getenv("POSTGRES_HOST", "timescaledb")
    db_port = int(os.getenv("POSTGRES_PORT", "5432"))
    db_user = os.getenv("POSTGRES_USER", "tradeul_user")
    db_pass = os.getenv("POSTGRES_PASSWORD", "")
    db_name = os.getenv("POSTGRES_DB", "tradeul")

    dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, command_timeout=120)

    try:
        task = TickerClassifierTask(db_pool=pool)
        skip = "--full" not in sys.argv
        result = await task.execute(skip_classified=skip)
        print(json.dumps(result, indent=2, default=str))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
