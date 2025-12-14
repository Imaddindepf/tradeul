#!/usr/bin/env python3
"""
SEC Financial Statement Data Sets Parser
=========================================

Genera mappings automáticos (Tier 2) desde los datasets públicos de la SEC.
https://www.sec.gov/dera/data/financial-statement-data-sets.html

Uso:
    1. Descarga manualmente el ZIP de SEC (ej: 2024q3.zip)
    2. Extrae en data/sec_datasets/2024q3/
    3. Ejecuta: python3 parse_sec_dataset.py data/sec_datasets/2024q3/

Output:
    - tier2_mappings.json: Mappings XBRL → canonical por frecuencia de uso
    - tag_analysis.json: Estadísticas de tags por statement type
"""

import os
import sys
import json
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    print("⚠️  rapidfuzz not installed - fuzzy matching disabled")


@dataclass
class XBRLTag:
    """Representa un tag XBRL del dataset SEC"""
    tag: str                    # Tag XBRL (ej: RevenueFromContractWithCustomerExcludingAssessedTax)
    plabel: str                 # Preferred label (ej: "Net Revenue")
    stmt: str                   # Statement: IS, BS, CF, EQ, CI
    inpth: int                  # Indentation (0=main, 1=sub, etc.)
    count: int = 0              # Cuántas empresas lo usan
    total_value: float = 0.0   # Suma de valores (para ordenar por importancia)


@dataclass
class CanonicalMapping:
    """Mapping XBRL → canonical con metadatos"""
    xbrl_tag: str
    canonical_key: str
    confidence: float           # 1.0 = manual, 0.85 = auto, 0.0 = unmapped
    tier: str                   # 'manual', 'auto', 'fallback'
    plabel: str
    stmt: str
    frequency: int              # Cuántas empresas lo usan


class SECDatasetParser:
    """Parser para SEC Financial Statement Data Sets"""
    
    # Mappings manuales existentes (Tier 1)
    TIER1_MAPPINGS = {
        # Revenue
        "Revenues": "revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
        "SalesRevenueNet": "revenue",
        # Cost
        "CostOfGoodsAndServicesSold": "cost_of_revenue",
        "CostOfGoodsSold": "cost_of_revenue",
        "CostOfRevenue": "cost_of_revenue",
        # Gross Profit
        "GrossProfit": "gross_profit",
        # Operating Expenses
        "OperatingExpenses": "operating_expenses",
        "SellingGeneralAndAdministrativeExpense": "sga",
        "ResearchAndDevelopmentExpense": "rd_expense",
        # Operating Income
        "OperatingIncomeLoss": "operating_income",
        # Net Income
        "NetIncomeLoss": "net_income",
        "ProfitLoss": "net_income",
        # EPS
        "EarningsPerShareBasic": "eps_basic",
        "EarningsPerShareDiluted": "eps_diluted",
        # Balance Sheet
        "Assets": "total_assets",
        "Liabilities": "total_liabilities",
        "StockholdersEquity": "total_equity",
        "CashAndCashEquivalentsAtCarryingValue": "cash",
        # Cash Flow
        "NetCashProvidedByUsedInOperatingActivities": "operating_cf",
        "NetCashProvidedByUsedInInvestingActivities": "investing_cf",
        "NetCashProvidedByUsedInFinancingActivities": "financing_cf",
    }
    
    # Patterns para inferir canonical_key desde plabel
    PLABEL_PATTERNS = [
        (r"^(total\s+)?revenue[s]?$", "revenue"),
        (r"^(total\s+)?net\s+(sales|revenue)", "revenue"),
        (r"^cost\s+of\s+(goods|revenue|sales)", "cost_of_revenue"),
        (r"^gross\s+profit", "gross_profit"),
        (r"^operating\s+(income|profit|loss)", "operating_income"),
        (r"^net\s+income", "net_income"),
        (r"^(basic\s+)?earnings?\s+per\s+share", "eps_basic"),
        (r"^diluted\s+earnings?\s+per\s+share", "eps_diluted"),
        (r"^total\s+assets?$", "total_assets"),
        (r"^total\s+liabilit", "total_liabilities"),
        (r"^(total\s+)?(stockholders?|shareholders?)\s+equity", "total_equity"),
        (r"^cash\s+(and|&)\s+(cash\s+)?equivalent", "cash"),
        (r"^(net\s+)?cash\s+(provided|used).+operat", "operating_cf"),
        (r"^(net\s+)?cash\s+(provided|used).+invest", "investing_cf"),
        (r"^(net\s+)?cash\s+(provided|used).+financ", "financing_cf"),
        (r"^research\s+(and|&)\s+development", "rd_expense"),
        (r"^selling.+general.+admin", "sga"),
        (r"^depreciation", "depreciation"),
        (r"^amortization", "amortization"),
        (r"^interest\s+expense", "interest_expense"),
        (r"^interest\s+income", "interest_income"),
        (r"^income\s+tax", "income_tax"),
        (r"^accounts?\s+receivable", "receivables"),
        (r"^inventor", "inventory"),
        (r"^accounts?\s+payable", "accounts_payable"),
        (r"^long.?term\s+debt", "lt_debt"),
        (r"^short.?term\s+(debt|borrow)", "st_debt"),
        (r"^property.+plant.+equipment", "ppe"),
        (r"^goodwill$", "goodwill"),
        (r"^intangible", "intangibles"),
        (r"^retained\s+earnings?", "retained_earnings"),
        (r"^common\s+stock", "common_stock"),
        (r"^treasury\s+stock", "treasury_stock"),
        (r"^dividends?\s+(paid|declared)", "dividends_paid"),
        (r"^stock.?based\s+compensation", "stock_compensation"),
        (r"^capital\s+expenditure", "capex"),
        (r"^free\s+cash\s+flow", "free_cash_flow"),
    ]
    
    def __init__(self, dataset_path: str):
        self.dataset_path = Path(dataset_path)
        self.tags: Dict[str, XBRLTag] = {}
        self.tag_by_stmt: Dict[str, List[str]] = defaultdict(list)
        
    def parse(self) -> Dict[str, List[CanonicalMapping]]:
        """
        Parsea el dataset SEC completo.
        Returns: Dict con mappings por statement type
        """
        # 1. Parsear pre.txt (tags con statement classification)
        self._parse_pre_txt()
        
        # 2. Parsear num.txt (valores para determinar frecuencia/importancia)
        self._parse_num_txt()
        
        # 3. Generar mappings automáticos
        mappings = self._generate_mappings()
        
        return mappings
    
    def _parse_pre_txt(self):
        """
        Parsea pre.txt: presenta tags con su statement y orden.
        
        Columnas: adsh, report, line, stmt, inpth, rfile, tag, version, plabel, negating
        """
        pre_file = self.dataset_path / "pre.txt"
        if not pre_file.exists():
            raise FileNotFoundError(f"pre.txt not found in {self.dataset_path}")
        
        print(f"📄 Parsing pre.txt...")
        
        seen_tags = set()
        
        with open(pre_file, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            for row in reader:
                tag = row.get('tag', '')
                stmt = row.get('stmt', '')
                plabel = row.get('plabel', '')
                inpth_str = row.get('inpth', '0')
                
                if not tag or not stmt:
                    continue
                
                # Solo statements que nos interesan
                if stmt not in ('IS', 'BS', 'CF'):
                    continue
                
                try:
                    inpth = int(float(inpth_str)) if inpth_str else 0
                except ValueError:
                    inpth = 0
                
                # Crear o actualizar tag
                tag_key = f"{tag}:{stmt}"
                
                if tag_key not in seen_tags:
                    seen_tags.add(tag_key)
                    
                    if tag not in self.tags:
                        self.tags[tag] = XBRLTag(
                            tag=tag,
                            plabel=plabel,
                            stmt=stmt,
                            inpth=inpth
                        )
                        self.tag_by_stmt[stmt].append(tag)
                    
                    self.tags[tag].count += 1
        
        print(f"   ✅ Found {len(self.tags)} unique tags")
        print(f"      IS: {len(self.tag_by_stmt['IS'])} | BS: {len(self.tag_by_stmt['BS'])} | CF: {len(self.tag_by_stmt['CF'])}")
    
    def _parse_num_txt(self):
        """
        Parsea num.txt: valores numéricos.
        
        Columnas: adsh, tag, version, coreg, ddate, qtrs, uom, value, footnote
        """
        num_file = self.dataset_path / "num.txt"
        if not num_file.exists():
            print(f"⚠️  num.txt not found, skipping value analysis")
            return
        
        print(f"📄 Parsing num.txt (this may take a while)...")
        
        count = 0
        with open(num_file, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            for row in reader:
                tag = row.get('tag', '')
                value_str = row.get('value', '')
                
                if tag in self.tags and value_str:
                    try:
                        value = float(value_str)
                        self.tags[tag].total_value += abs(value)
                    except ValueError:
                        pass
                
                count += 1
                if count % 1_000_000 == 0:
                    print(f"   ... processed {count:,} rows")
        
        print(f"   ✅ Processed {count:,} value rows")
    
    def _generate_mappings(self) -> Dict[str, List[CanonicalMapping]]:
        """Genera mappings automáticos basados en frecuencia y plabel"""
        
        mappings_by_stmt = {
            'IS': [],
            'BS': [],
            'CF': []
        }
        
        for tag_name, tag_data in self.tags.items():
            # 1. Verificar si ya está en Tier 1
            if tag_name in self.TIER1_MAPPINGS:
                canonical_key = self.TIER1_MAPPINGS[tag_name]
                confidence = 1.0
                tier = 'manual'
            else:
                # 2. Intentar inferir desde plabel
                canonical_key = self._infer_canonical_from_plabel(tag_data.plabel)
                
                if canonical_key:
                    confidence = 0.85
                    tier = 'auto'
                else:
                    # 3. Fallback: normalizar el tag name
                    canonical_key = self._normalize_tag_name(tag_name)
                    confidence = 0.0
                    tier = 'fallback'
            
            mapping = CanonicalMapping(
                xbrl_tag=tag_name,
                canonical_key=canonical_key,
                confidence=confidence,
                tier=tier,
                plabel=tag_data.plabel,
                stmt=tag_data.stmt,
                frequency=tag_data.count
            )
            
            mappings_by_stmt[tag_data.stmt].append(mapping)
        
        # Ordenar por frecuencia (más usados primero)
        for stmt in mappings_by_stmt:
            mappings_by_stmt[stmt].sort(key=lambda m: -m.frequency)
        
        return mappings_by_stmt
    
    def _infer_canonical_from_plabel(self, plabel: str) -> Optional[str]:
        """Intenta inferir canonical_key desde el plabel usando patterns"""
        if not plabel:
            return None
        
        plabel_lower = plabel.lower().strip()
        
        for pattern, canonical_key in self.PLABEL_PATTERNS:
            if re.search(pattern, plabel_lower):
                return canonical_key
        
        return None
    
    def _normalize_tag_name(self, tag: str) -> str:
        """Convierte CamelCase a snake_case"""
        s1 = re.sub(r'([a-z])([A-Z])', r'\1_\2', tag)
        return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def save_mappings(self, mappings: Dict[str, List[CanonicalMapping]], output_dir: str):
        """Guarda los mappings en JSON"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Guardar mappings completos
        all_mappings = []
        for stmt, stmt_mappings in mappings.items():
            for m in stmt_mappings:
                all_mappings.append(asdict(m))
        
        mappings_file = output_path / "tier2_mappings.json"
        with open(mappings_file, 'w') as f:
            json.dump(all_mappings, f, indent=2)
        
        print(f"📁 Saved {len(all_mappings)} mappings to {mappings_file}")
        
        # 2. Guardar análisis de tags
        analysis = {
            'summary': {
                'total_tags': len(self.tags),
                'by_statement': {
                    'IS': len(self.tag_by_stmt['IS']),
                    'BS': len(self.tag_by_stmt['BS']),
                    'CF': len(self.tag_by_stmt['CF']),
                }
            },
            'tier_breakdown': {
                'manual': sum(1 for m in all_mappings if m['tier'] == 'manual'),
                'auto': sum(1 for m in all_mappings if m['tier'] == 'auto'),
                'fallback': sum(1 for m in all_mappings if m['tier'] == 'fallback'),
            },
            'top_tags_by_frequency': [
                {'tag': t.tag, 'plabel': t.plabel, 'stmt': t.stmt, 'count': t.count}
                for t in sorted(self.tags.values(), key=lambda x: -x.count)[:100]
            ]
        }
        
        analysis_file = output_path / "tag_analysis.json"
        with open(analysis_file, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        print(f"📊 Saved analysis to {analysis_file}")
        
        # 3. Imprimir resumen
        print(f"\n{'='*60}")
        print(f"RESUMEN DE MAPPINGS")
        print(f"{'='*60}")
        print(f"Total tags: {len(self.tags)}")
        print(f"  - Manual (Tier 1): {analysis['tier_breakdown']['manual']}")
        print(f"  - Auto (Tier 2):   {analysis['tier_breakdown']['auto']}")
        print(f"  - Fallback:        {analysis['tier_breakdown']['fallback']}")
        print(f"\nTop 10 tags más usados:")
        for tag in analysis['top_tags_by_frequency'][:10]:
            print(f"  {tag['count']:5d}x | {tag['stmt']} | {tag['plabel'][:40]}")


class PlabelGrouper:
    """
    Agrupa tags con plabels similares usando fuzzy matching.
    Implementa la sugerencia del amigo: "Agrupa tags con plabel similar (~85%)"
    """
    
    def __init__(self, threshold: int = 85):
        self.threshold = threshold
        self.groups: Dict[str, List[str]] = {}
    
    def group_tags(self, tags: List[XBRLTag]) -> Dict[str, List[XBRLTag]]:
        """
        Agrupa tags por similitud de plabel.
        El tag más frecuente del grupo se convierte en el canonical.
        """
        groups: Dict[str, List[XBRLTag]] = {}
        processed_plabels: Dict[str, str] = {}  # plabel → group_canonical
        
        # Ordenar por frecuencia (más usados primero)
        sorted_tags = sorted(tags, key=lambda t: -t.count)
        
        for tag in sorted_tags:
            plabel = tag.plabel.lower().strip()
            
            if not plabel:
                continue
            
            # Buscar grupo existente con plabel similar
            if processed_plabels and HAS_RAPIDFUZZ:
                # Usar fuzzy match para encontrar similitudes
                match = process.extractOne(
                    plabel,
                    processed_plabels.keys(),
                    scorer=fuzz.ratio,
                    score_cutoff=self.threshold
                )
                
                if match:
                    matched_plabel, score, _ = match
                    group_canonical = processed_plabels[matched_plabel]
                    groups[group_canonical].append(tag)
                    continue
            
            # Crear nuevo grupo
            canonical_name = self._normalize_plabel(plabel)
            groups[canonical_name] = [tag]
            processed_plabels[plabel] = canonical_name
        
        return groups
    
    def _normalize_plabel(self, plabel: str) -> str:
        """Normaliza plabel a formato canonical"""
        # Remove special chars, lowercase, replace spaces with underscore
        normalized = re.sub(r'[^\w\s]', '', plabel.lower())
        normalized = re.sub(r'\s+', '_', normalized.strip())
        return normalized


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_sec_dataset.py <path_to_extracted_zip>")
        print("Example: python3 parse_sec_dataset.py data/sec_datasets/2024q3/")
        sys.exit(1)
    
    dataset_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "data/sec_mappings"
    
    parser = SECDatasetParser(dataset_path)
    mappings = parser.parse()
    parser.save_mappings(mappings, output_dir)


if __name__ == "__main__":
    main()

