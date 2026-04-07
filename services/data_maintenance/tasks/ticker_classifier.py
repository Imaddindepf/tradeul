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
# Each tag has a one-line description + key examples sent directly to Gemini.
# Format: { category: { tag: "description (e.g. TICK1, TICK2)" } }
# ═══════════════════════════════════════════════════════════════════════════════

THEMATIC_CATALOG: Dict[str, Dict[str, str]] = {
    # ── SEMICONDUCTORS ──────────────────────────────────────────────────────
    "semiconductors": {
        "semiconductors":           "Broad chip company — designer, fab, or IP licensor. Use when no specific sub-tag fits. (e.g. NVDA, AMD, TSM, QCOM, TXN, AVGO)",
        "semiconductor_equipment":  "Equipment to fabricate chips: lithography, etch, CVD, inspection. (e.g. ASML, LRCX, KLAC, AMAT, ONTO)",
        "memory_chips":             "DRAM, NAND flash, or HBM high-bandwidth memory. (e.g. MU, WDC, SNDK)",
        "gpu_accelerators":         "GPU and AI accelerator chips for ML training/inference. Includes custom AI ASIC silicon for hyperscalers. (e.g. NVDA H100/Blackwell, AMD Instinct MI300X, MRVL custom, CRWV)",
        "cpu_processors":           "General-purpose CPUs: x86, ARM, RISC-V. (e.g. INTC, AMD EPYC/Ryzen, ARM Holdings, QCOM Snapdragon, MRVL Octeon)",
        "analog_mixed_signal":      "Analog, mixed-signal, and power management ICs for industrial/auto/consumer. (e.g. TXN, ADI, MCHP, ON, SWKS)",
        "networking_chips":         "Ethernet, switching, routing ASICs and network connectivity silicon. (e.g. AVGO, MRVL, CSCO silicon)",
        "rf_wireless_chips":        "RF front-end modules, modem, 5G baseband chips. (e.g. QCOM, SWKS, QRVO, MTSI)",
        "chip_foundry":             "Contract semiconductor fabrication. (e.g. TSM, GFS, UMC, Intel Foundry)",
        "power_semiconductors":     "SiC, GaN, IGBT, power MOSFETs for EVs, renewables, and industrial. (e.g. ON, WOLF, STM, DIOD)",
        "eda_chip_design":          "EDA software and semiconductor IP cores used to design chips. (e.g. SNPS, CDNS, ARM, ANSYS)",
    },
    # ── AI & SOFTWARE ───────────────────────────────────────────────────────
    "ai_software": {
        "artificial_intelligence":      "Broad AI — company derives meaningful revenue or product value from AI. (e.g. NVDA, MSFT, GOOGL, META, PLTR)",
        "generative_ai":                "Building or deploying LLMs, image-gen, or multimodal foundation models. (e.g. NVDA, MSFT/OpenAI, GOOGL Gemini, META Llama, ADBE Firefly)",
        "machine_learning":             "ML infrastructure: model training pipelines, MLOps, feature stores. (e.g. DDOG, SNOW, SAMSARA)",
        "data_infrastructure":          "Data platforms, data lakes, real-time analytics infrastructure. (e.g. SNOW, MDB, DDOG, PLTR, DBX)",
        "cloud_computing":              "Public cloud IaaS/PaaS and cloud-native infrastructure. (e.g. AMZN AWS, MSFT Azure, GOOGL GCP, NET)",
        "edge_computing":               "Computing at the network edge — CDN, edge nodes, IoT processing. (e.g. NET, FSLY, AKAM)",
        "saas":                         "Software-as-a-Service: subscription cloud software. (e.g. CRM, NOW, WDAY, HUBS, ZM)",
        "enterprise_software":          "ERP, HCM, finance and supply chain software for enterprises. (e.g. ORCL, SAP, WDAY, INTU, IBM)",
        "crm_marketing_tech":           "CRM, marketing automation, customer data platforms. (e.g. CRM, HUBS, BRZE, KVYO)",
        "developer_tools":              "DevOps, CI/CD, observability, code collaboration. (e.g. GTLB, ESTC, DDOG, TEAM)",
        "big_data_analytics":           "Analytics, business intelligence, data warehousing. (e.g. SNOW, PLTR, MSTR, DOMO)",
        "cybersecurity":                "Broad cybersecurity — security as primary or major revenue driver. (e.g. CRWD, PANW, ZS, FTNT, OKTA)",
        "identity_zero_trust":          "Identity management, zero-trust network access, PAM. (e.g. OKTA, CYBR, ZS, SAIL)",
        "endpoint_network_security":    "Endpoint protection, firewall, network security appliances. (e.g. CRWD, PANW, FTNT, S, CHKP)",
        "ar_vr":                        "Augmented/virtual reality hardware and software. (e.g. META Quest, AAPL Vision Pro, SNAP, U)",
        "ai_data_centers":              "Operators of high-performance compute (HPC) data centers for AI training/inference — NOT REITs. (e.g. IREN, CORZ, CRWV, HUT after pivot)",
        "ai_agents_inference":          "Platforms deploying AI agents, copilots, or inference APIs as a commercial product. (e.g. BBAI, CRNC, AI, SOUN, PLTR AI Platform)",
        "data_center_hardware":         "Servers, rack systems, and liquid cooling infrastructure purpose-built for AI data centers. (e.g. SMCI, DELL PowerEdge AI, HPE, VRT, NTAP)",
    },
    # ── CONNECTIVITY & TELECOM ──────────────────────────────────────────────
    "connectivity": {
        "5g_iot":           "5G infrastructure buildout and IoT connected device ecosystem. (e.g. ERIC, NOK, QCOM, CSCO, KEYS)",
        "satellite_internet": "LEO or GEO broadband satellite internet services. (e.g. ASTS, GSAT, IRDM, VSAT)",
        "fiber_optics":     "Fiber optic transceivers, components, and optical networking equipment. (e.g. AAOI, LITE, COHR, VIAV)",
    },
    # ── ROBOTICS & AUTOMATION ───────────────────────────────────────────────
    "robotics_automation": {
        "robotics":                 "Broad industrial, service, or collaborative robotics. (e.g. ROK, ISRG, ABB, Fanuc ADRs)",
        "surgical_robotics":        "Robotic-assisted surgical systems and instruments. (e.g. ISRG, MBOT, CMR)",
        "industrial_automation":    "Factory automation, PLCs, SCADA, motor drives, industrial sensors. (e.g. ROK, EMR, HON, ABB)",
        "autonomous_vehicles":      "Self-driving cars, AV software, and enabling sensors/compute. (e.g. TSLA FSD, GOOGL Waymo, MBLY)",
        "lidar":                    "LiDAR sensors for automotive, industrial, or geospatial use. (e.g. LAZR, INVZ, OUST, AEYE)",
        "drones":                   "Commercial UAVs, eVTOL aircraft, drone delivery platforms. (e.g. AVAV, JOBY, ACHR, RCAT)",
        "3d_printing":              "Additive manufacturing hardware, software, and materials. (e.g. DDD, SSYS, DM, NNDM)",
        "humanoid_robotics":        "Humanoid robot development and enabling components. (e.g. TSLA Optimus, ISRG, ABB, FANUY)",
    },
    # ── QUANTUM & FRONTIER ──────────────────────────────────────────────────
    "frontier_tech": {
        "quantum_computing":    "Quantum computing hardware, software, and error correction. (e.g. IONQ, RGTI, QBTS, QUBT)",
        "blockchain_crypto":    "Broad blockchain infrastructure, crypto exchanges, DeFi — NOT bitcoin mining specifically. (e.g. COIN, HOOD, MSTR Bitcoin treasury, PYPL crypto)",
        "bitcoin_mining":       "Companies that mine Bitcoin or other PoW cryptocurrency as their primary business — high power consumption, ASICs. (e.g. MARA, RIOT, CLSK, HUT, BITF, WULF, CIFR, IREN, CORZ)",
        "crypto_exchange":      "Platforms where users buy, sell, or trade crypto assets. (e.g. COIN, HOOD crypto, Kraken)",
        "space_technology":     "Rocket launch services, satellite manufacturing, space exploration. (e.g. RKLB, SPCE, BA Space, ASTS)",
    },
    # ── FINTECH & FINANCIAL ─────────────────────────────────────────────────
    "fintech_financial": {
        "fintech":              "Broad fintech — technology-enabled financial services disrupting traditional banking/finance. (e.g. SQ, PYPL, SOFI, NU, AFRM)",
        "digital_payments":     "Payment processing networks, merchant acquiring, digital wallets. (e.g. V, MA, PYPL, SQ, ADYEY)",
        "buy_now_pay_later":    "BNPL consumer credit embedded at checkout. (e.g. AFRM, SEZL, LPRO)",
        "neobanking":           "Digital-first banks without physical branches. (e.g. SOFI, NU, DAVE)",
        "insurtech":            "Technology-driven insurance underwriting and distribution. (e.g. LMND, ROOT, OSCR)",
        "lending_platforms":    "AI/online loan origination: personal, student, small business. (e.g. UPST, LC, SLM)",
        "wealthtech":           "Digital wealth management, robo-advisors, retail investing platforms. (e.g. HOOD, SCHW digital, SOFI invest)",
        "payroll_hr_tech":      "Cloud payroll, HRIS, workforce management software. (e.g. PAYC, PCTY, ADP, PAYX)",
        "online_gambling":      "Sports betting, iGaming, daily fantasy sports. (e.g. DKNG, FLUT, PENN, MGM online)",
    },
    # ── BIOTECH & PHARMA ────────────────────────────────────────────────────
    "biotech_pharma": {
        "biotech":              "Broad biotech — drug R&D company, typically pre-commercial or early revenue stage. (e.g. MRNA platform, VRTX, REGN, BLUE)",
        "genomics":             "DNA sequencing instruments, genomic analysis tools and services. (e.g. ILMN, PACB, BRKR)",
        "gene_editing_crispr":  "CRISPR, base editing, prime editing therapeutic platforms. (e.g. CRSP, BEAM, NTLA, EDIT)",
        "mrna_therapeutics":    "mRNA drug delivery platforms beyond COVID vaccines. (e.g. MRNA, BNTX, ARCT)",
        "cell_gene_therapy":    "CAR-T, TIL cell therapies and gene replacement therapies. (e.g. BLUE, KRTX, ALNY)",
        "immunotherapy":        "Cancer immunotherapy: checkpoint inhibitors, CAR-T, bispecific antibodies. (e.g. MRK Keytruda, BMY Opdivo, GILD Yescarta)",
        "oncology":             "Broad cancer therapeutics including chemo, targeted therapy. (e.g. MRK, BMY, ABBV, EXEL)",
        "glp1_weight_loss":     "GLP-1 receptor agonists for obesity and type-2 diabetes treatment. (e.g. LLY Mounjaro/Zepbound, NVO Ozempic/Wegovy, VKTX, AMGN)",
        "diabetes":             "Diabetes management: CGM devices, insulin pumps, diabetes drugs. (e.g. DXCM, PODD, TNDM, LLY, NVO)",
        "neuroscience":         "CNS disorders: Alzheimer's, Parkinson's, depression, epilepsy. (e.g. BIIB, SAVA, AXSM, ACAD)",
        "cardiovascular":       "Heart disease therapeutics, cardiovascular devices and diagnostics. (e.g. ABT, MDT, BSX, ITCI)",
        "rare_disease":         "Orphan drug development for rare or ultra-rare conditions. (e.g. ALNY, SRPT, BMRN, RARE)",
        "vaccines":             "Vaccine platforms: mRNA, viral vector, protein subunit. (e.g. PFE, MRNA, NVAX, BNTX)",
        "psychedelics":         "Psilocybin, MDMA, ketamine as mental health therapeutics. (e.g. CMPS, MNMD, ATAI)",
        "cannabis":             "Cannabis cultivation, retail dispensaries, and derivative products. (e.g. TLRY, CGC, CRON, ACB)",
    },
    # ── MEDTECH & HEALTH SERVICES ───────────────────────────────────────────
    "medtech_health": {
        "digital_health":   "Broad digital health — apps, platforms, remote patient monitoring. (e.g. TDOC, AMWL, HIMS, ACCD)",
        "telehealth":       "Virtual care and telemedicine consultations. (e.g. TDOC, AMWL, DOCS)",
        "medical_devices":  "Implantable and non-implantable medical devices and instruments. (e.g. MDT, SYK, ABT, BSX, ISRG)",
        "diagnostics":      "Lab testing, in vitro diagnostics, liquid biopsy. (e.g. DGX, LH, EXAS, NTRA, GH)",
        "medical_imaging":  "Imaging systems: MRI, CT, ultrasound, nuclear medicine. (e.g. HOLX, SIE-Healthineers, PHG)",
        "dental":           "Dental technology, orthodontics, and dental supply distribution. (e.g. ALGN, XRAY, HSIC, PDCO)",
        "animal_health":    "Veterinary pharmaceuticals, diagnostics, and animal health monitoring. (e.g. ZTS, IDXX, ELAN, PAHC)",
        "cro_cdmo":         "Contract research organizations (CRO) and contract drug manufacturers (CDMO). (e.g. ICLR, CRL, CTLT, MEDP)",
        "aging_population": "Products and services targeting elderly care: senior housing, geriatric drugs, home care. (e.g. VTR, WELL, BKD)",
    },
    # ── ENERGY: OIL & GAS ───────────────────────────────────────────────────
    "oil_gas": {
        "oil_exploration":      "Upstream oil & gas: exploration, drilling, and production (E&P). (e.g. XOM, CVX, PXD, FANG, OXY)",
        "oil_refining":         "Downstream: crude oil refining and petroleum product marketing. (e.g. MPC, VLO, PSX, DK)",
        "oil_services":         "Oilfield services: drilling, completion, well services, equipment rental. (e.g. SLB, HAL, BKR, RES)",
        "midstream_pipelines":  "Oil & gas pipelines, storage terminals, processing plants, MLPs. (e.g. KMI, WMB, ET, EPD, MPLX)",
        "natural_gas":          "Natural gas producers, LNG exporters, and gas utilities. (e.g. LNG, EQT, AR, RRC, CTRA)",
    },
    # ── ENERGY: CLEAN & NUCLEAR ─────────────────────────────────────────────
    "clean_energy": {
        "clean_energy":         "Broad renewables — any company generating meaningful revenue from non-fossil clean power. (e.g. NEE, CWEN, FSLR, ENPH, RUN)",
        "solar":                "Solar panel manufacturing, inverters, residential/utility installation. (e.g. FSLR, ENPH, SEDG, RUN, ARRY)",
        "wind":                 "Wind turbine manufacturing, offshore/onshore wind farms. (e.g. NEE wind, CWEN, VWSYF)",
        "nuclear_energy":       "Nuclear power generation, SMR development, uranium enrichment. (e.g. CEG, VST nuclear, CCJ, NuScale)",
        "nuclear_power_ai":     "Power generators with signed PPAs or contracts to supply AI hyperscalers or data centers with baseload electricity. (e.g. CEG, VST, NRG, ETR, DUK)",
        "uranium":              "Uranium mining, milling, and fuel cycle services. (e.g. CCJ, DNN, UEC, LEU, NXE)",
        "hydrogen_fuel_cells":  "Green hydrogen production, fuel cell systems, electrolyzer manufacturing. (e.g. PLUG, BE, FCEL)",
        "battery_storage":      "Grid-scale and EV battery storage systems and cell manufacturing. (e.g. QS, MVST, AMPS, STEM)",
        "lithium":              "Lithium mining, processing, and battery-grade chemical production. (e.g. ALB, SQM, LAC, LTHM)",
        "carbon_capture":       "Carbon capture, utilization, and storage (CCUS) technology. (e.g. CTRA CCUS, XOM CCS)",
        "smart_grid":           "Grid modernization: smart meters, demand response, grid software. (e.g. ITRI, GNRC, AMETEK, REZI)",
    },
    # ── TRANSPORTATION & EVs ────────────────────────────────────────────────
    "transportation": {
        "electric_vehicles":    "Battery electric vehicle manufacturers and EV-focused startups. (e.g. TSLA, RIVN, LCID, NIO, LI)",
        "ev_charging":          "EV charging network operators and charging equipment manufacturers. (e.g. CHPT, BLNK, EVGO)",
        "ride_sharing":         "Ride-hailing and mobility-as-a-service platforms. (e.g. UBER, LYFT, DIDI)",
        "shipping":             "Ocean freight, dry bulk, container shipping lines. (e.g. ZIM, SBLK, DAC, MATX)",
        "rails_freight":        "Rail freight carriers and railroad operators. (e.g. UNP, CSX, NSC, CP, CN)",
        "airlines":             "Passenger airline carriers, both legacy and low-cost. (e.g. DAL, UAL, LUV, AAL, JBLU)",
    },
    # ── MINING & MATERIALS ──────────────────────────────────────────────────
    "mining_materials": {
        "gold_mining":          "Gold mining and royalty/streaming companies. (e.g. NEM, GOLD, AEM, KGC, WPM)",
        "silver_mining":        "Primary silver miners and silver streaming companies. (e.g. PAAS, HL, AG, WPM)",
        "copper":               "Copper mining and smelting — key metal for EVs and grid infrastructure. (e.g. FCX, SCCO, TECK)",
        "rare_earths":          "Rare earth element mining, separation, and magnet production. (e.g. MP, UUUU, NMP)",
        "steel":                "Steel production, mini-mills, flat-rolled and structural steel. (e.g. NUE, STLD, CLF, X)",
        "aluminum":             "Primary aluminum smelting and downstream aluminum products. (e.g. AA, CENX, CSTM)",
        "agriculture_agtech":   "Agricultural equipment, precision farming, crop inputs, ag-biotech. (e.g. DE, AGCO, FMC, CTVA)",
    },
    # ── CONSUMER DIGITAL ────────────────────────────────────────────────────
    "consumer_digital": {
        "e_commerce":           "Online retail marketplaces and direct-to-consumer e-commerce platforms. (e.g. AMZN, SHOP, MELI, ETSY, PDD)",
        "social_media":         "Social networking platforms monetized via advertising or subscriptions. (e.g. META, SNAP, PINS, RDDT)",
        "streaming":            "Video and audio streaming services. (e.g. NFLX, DIS+, ROKU, SPOT, PARA+)",
        "esports_gaming":       "Video game publishers, gaming platforms, and esports leagues. (e.g. RBLX, EA, TTWO, U, ATVI)",
        "food_delivery":        "On-demand food and grocery delivery platforms. (e.g. DASH, UBER Eats, TKWY)",
        "education_tech":       "Online learning platforms and education technology. (e.g. DUOL, CHGG, COUR, UDMY)",
        "digital_advertising":  "Digital and programmatic advertising platforms generating ad revenue at scale. (e.g. GOOGL Ads, META Ads, TTD, AMZN Ads, PUBM, MGNI, IAS)",
    },
    # ── CONSUMER LIFESTYLE ──────────────────────────────────────────────────
    "consumer_lifestyle": {
        "travel_tech":          "Online travel agencies, booking platforms, vacation rental. (e.g. BKNG, ABNB, EXPE, TRIP)",
        "gig_economy":          "Online marketplaces connecting freelance workers with clients. (e.g. FVRR, UPWK)",
        "luxury_brands":        "Premium and luxury consumer goods: fashion, accessories, jewelry. (e.g. TPR, CPRI, RH)",
        "restaurant_tech":      "Restaurant management software, POS systems, ordering platforms. (e.g. TOST, PAR, YELP)",
        "pet_economy":          "Pet food, veterinary services, pet accessories and insurance. (e.g. CHWY, WOOF, ZTS, TRUP)",
        "athleisure_wellness":  "Athletic apparel, fitness equipment, wellness apps. (e.g. LULU, PTON, NKE, UA)",
    },
    # ── DEFENSE & AEROSPACE ─────────────────────────────────────────────────
    "defense_aerospace": {
        "defense_contractors":  "Prime defense contractors: weapons systems, aircraft, naval vessels. (e.g. LMT, RTX, NOC, GD, BA defense)",
        "defense_tech":         "Defense software, analytics, AI for military and government. (e.g. PLTR, BWXT, LDOS, SAIC, CACI)",
        "commercial_aerospace": "Commercial aircraft manufacturing, aerostructures, MRO services. (e.g. BA, SPR, HXL, TDG, HEICO)",
        "hypersonics_missiles": "Hypersonic weapons, directed energy, advanced missile systems. (e.g. LMT, RTX, NOC)",
        "border_surveillance":  "Border security, surveillance technology, biometrics. (e.g. AXON, FLIR/TTEC, DRS)",
    },
    # ── INFRASTRUCTURE & INDUSTRIAL ─────────────────────────────────────────
    "industrial_infra": {
        "construction_engineering": "Heavy construction, engineering services, building materials. (e.g. CAT, VMC, MLM, PWR, FLR)",
        "water_treatment":          "Water utilities, industrial water treatment, filtration systems. (e.g. XYL, WMS, WTRG, ERII)",
        "waste_management":         "Waste collection, recycling, and environmental services. (e.g. WM, RSG, CLH, SRCL)",
    },
    # ── REAL ESTATE VERTICALS ───────────────────────────────────────────────
    "real_estate_verticals": {
        "data_center_reits":    "REITs that own and lease data center facilities. (e.g. EQIX, DLR, VNET, IRM digital, QTS)",
        "cell_tower_reits":     "REITs that own wireless tower infrastructure. (e.g. AMT, CCI, SBAC, UNIT)",
        "healthcare_reits":     "REITs focused on senior housing, medical offices, hospitals. (e.g. VTR, WELL, OHI, NHI)",
    },
}

ALL_THEMES: Set[str] = set()
THEME_TO_CATEGORY: Dict[str, str] = {}
for category, theme_dict in THEMATIC_CATALOG.items():
    ALL_THEMES.update(theme_dict.keys())
    for t in theme_dict.keys():
        THEME_TO_CATEGORY[t] = category


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_PROMPT = """\
You are a senior financial data analyst specializing in equity classification for a professional trading platform. Today's date is {today}. Classify each company below using EXACTLY the GICS taxonomy provided and assign thematic investment tags.

## CLASSIFICATION RULES (GICS methodology)
1. PRIMARY: Classify by the business activity generating >60% of revenue.
2. If no single activity >60%, use the activity providing majority of BOTH revenue AND earnings.
3. If diversified across 3+ sectors → use "Industrial Conglomerates" or "Multi-Sector Holdings".
4. SPACs, blank-check companies, shell companies → sector "Financials", industry "Specialized Finance", is_operating=false.
5. Closed-end funds, BDCs, ETNs, investment trusts, asset management vehicles → sector "Financials", industry "Asset Management & Custody Banks", is_operating=false.
6. company_name_clean: Remove suffixes like "Inc.", "Corp.", "Ltd.", "Common Stock", "Class A", etc. Keep the essential brand name.

## THEMATIC TAGS RULES
1. Assign 0-12 thematic tags per company. ONLY from the CANONICAL list below.
2. A tag applies if the company derives revenue from that area, OR if investors widely trade it as part of that theme.
3. For each tag, assign a relevance score (0.50-1.00): 1.00 = core business, 0.70 = significant segment, 0.50 = notable exposure or thematic association.
4. Be thorough: a company can belong to multiple themes. Assign all that apply with score ≥ 0.50.
5. If a company pivoted its business model recently (e.g. miners becoming AI data center operators), classify based on its CURRENT business as described, not only its original business.
6. Funds/SPACs/shells: assign zero thematic tags (empty array).

## GICS SECTORS (pick ONE)
{sectors}

## GICS TAXONOMY (sector → industry → sub_industry)
{taxonomy}

## THEMATIC TAGS CATALOG
Each tag includes a description and examples. Assign any tag that fits the company.
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
      {{"tag": "artificial_intelligence", "relevance": 0.80}}
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
    for category, theme_dict in THEMATIC_CATALOG.items():
        lines.append(f"\n[{category.upper()}]")
        for tag, description in theme_dict.items():
            lines.append(f"  {tag} — {description}")
    return "\n".join(lines)


def _build_company_block(companies: List[Dict]) -> str:
    lines = []
    for c in companies:
        desc = (c.get("description") or "")[:700]
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
        today=datetime.utcnow().strftime("%B %Y"),
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
