"""
Industry Profiles - Mapeo de SIC codes a campos específicos por industria.

Basado en la taxonomía FASB US-GAAP 2024:
- soi-ins: Insurance
- soi-int: Banking (Interest-based)
- soi-re: Real Estate
- soi-reit: REIT

Esto permite mostrar los campos relevantes según la industria de cada empresa.
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass


@dataclass
class IndustryProfile:
    """Perfil de industria con campos específicos a mostrar."""
    name: str
    sic_codes: Set[int]  # Códigos SIC que pertenecen a esta industria
    income_fields: List[str]  # Campos de Income Statement a mostrar prominentemente
    balance_fields: List[str]  # Campos de Balance Sheet específicos
    cashflow_fields: List[str]  # Campos de Cash Flow específicos
    key_metrics: List[str]  # Métricas clave de la industria


# =============================================================================
# PERFILES POR INDUSTRIA
# =============================================================================

INSURANCE_PROFILE = IndustryProfile(
    name="Insurance",
    sic_codes={
        6311,  # Life Insurance
        6321,  # Accident & Health Insurance
        6324,  # Hospital & Medical Service Plans (UNH)
        6331,  # Fire, Marine & Casualty Insurance
        6351,  # Surety Insurance
        6361,  # Title Insurance
        6399,  # Insurance Carriers, NEC
        6411,  # Insurance Agents, Brokers & Service
    },
    income_fields=[
        # Revenue breakdown
        'premiums_earned_net',
        'premiums_written_gross',
        'premiums_written_net',
        'interest_and_dividend_income_operating',
        'fee_income',
        'other_income',
        'revenue',
        # Costs
        'policyholder_benefits_and_claims_incurred_net',
        'interest_credited_to_policyholder_account_balances',
        'policyholder_dividends',
        'liability_for_future_policy_benefits_period_expense',
        'deferred_policy_acquisition_cost_amortization_expense',
        'general_insurance_expense',
        'cost_of_revenue',
        # Standard
        'operating_income',
        'net_income',
        'eps_diluted',
    ],
    balance_fields=[
        'investments_total',
        'reinsurance_recoverables',
        'deferred_policy_acquisition_costs',
        'policy_liabilities',
        'unearned_premiums',
        'claims_and_claims_expense',
        'total_assets',
        'total_liabilities',
        'total_equity',
    ],
    cashflow_fields=[
        'operating_cf',
        'premiums_collected',
        'claims_paid',
        'investment_income_received',
        'free_cash_flow',
    ],
    key_metrics=[
        'combined_ratio',  # Loss Ratio + Expense Ratio
        'loss_ratio',
        'expense_ratio',
        'medical_loss_ratio',  # Para health insurance
        'return_on_equity',
    ]
)

BANKING_PROFILE = IndustryProfile(
    name="Banking",
    sic_codes={
        6020,  # Commercial Banks
        6021,  # National Commercial Banks (JPM)
        6022,  # State Commercial Banks (BAC, WFC)
        6029,  # Commercial Banks, NEC
        6035,  # Savings Institutions, Federally Chartered
        6036,  # Savings Institutions, Not Federally Chartered
        6099,  # Functions Related to Depository Banking
        6141,  # Personal Credit Institutions
        6153,  # Short-Term Business Credit
        6159,  # Miscellaneous Business Credit
        6162,  # Mortgage Bankers & Loan Correspondents
        6172,  # Finance Lessors
        6199,  # Finance Services
        6211,  # Security Brokers, Dealers & Flotation
        6221,  # Commodity Contracts Dealers, Brokers
        6282,  # Investment Advice
    },
    income_fields=[
        # Interest Income/Expense
        'interest_income_expense_net',
        'interest_and_fee_income_loans_and_leases',
        'interest_and_dividend_income_securities',
        'interest_income_operating',
        'interest_expense_deposits',
        'interest_expense_borrowings',
        'interest_expense_operating',
        # Provisions
        'provision_for_loan_losses_expensed',
        'provision_for_loan_lease_and_other_losses',
        # Non-Interest
        'noninterest_income',
        'fee_and_commission_income',
        'trading_gains_losses',
        'investment_banking_revenue',
        'noninterest_expense',
        # Standard
        'operating_income',
        'net_income',
        'eps_diluted',
    ],
    balance_fields=[
        'loans_and_leases_receivable_net',
        'deposits',
        'federal_funds_sold',
        'securities_available_for_sale',
        'securities_held_to_maturity',
        'allowance_for_loan_losses',
        'total_assets',
        'total_liabilities',
        'total_equity',
    ],
    cashflow_fields=[
        'operating_cf',
        'loans_originated',
        'deposits_change',
        'free_cash_flow',
    ],
    key_metrics=[
        'net_interest_margin',
        'efficiency_ratio',
        'return_on_assets',
        'return_on_equity',
        'tier_1_capital_ratio',
        'loan_to_deposit_ratio',
    ]
)

REAL_ESTATE_PROFILE = IndustryProfile(
    name="Real Estate",
    sic_codes={
        6500,  # Real Estate
        6510,  # Real Estate Operators
        6512,  # Operators of Nonresidential Buildings
        6513,  # Operators of Apartment Buildings
        6514,  # Operators of Dwellings Other Than Apartment Buildings
        6515,  # Operators of Residential Mobile Home Sites
        6517,  # Lessors of Railroad Property
        6519,  # Lessors of Real Property, NEC
        6531,  # Real Estate Agents & Managers
        6532,  # Real Estate Dealers
        6552,  # Land Subdividers & Developers
        6798,  # Real Estate Investment Trusts (REITs)
    },
    income_fields=[
        'rental_revenue',
        'real_estate_revenue_net',
        'tenant_reimbursements',
        'property_operating_expense',
        'depreciation_real_estate',
        'interest_expense',
        'funds_from_operations',  # FFO - métrica clave de REITs
        'net_income',
        'eps_diluted',
    ],
    balance_fields=[
        'real_estate_investment_property_net',
        'land_and_land_improvements',
        'buildings_and_improvements',
        'mortgage_loans_payable',
        'total_assets',
        'total_liabilities',
        'total_equity',
    ],
    cashflow_fields=[
        'operating_cf',
        'acquisitions_of_real_estate',
        'capital_expenditures_real_estate',
        'dividends_paid',
        'free_cash_flow',
    ],
    key_metrics=[
        'funds_from_operations_per_share',
        'adjusted_ffo_per_share',
        'net_asset_value_per_share',
        'occupancy_rate',
        'cap_rate',
    ]
)

TECHNOLOGY_PROFILE = IndustryProfile(
    name="Technology",
    sic_codes={
        3571,  # Electronic Computers (AAPL)
        3572,  # Computer Storage Devices
        3575,  # Computer Terminals
        3576,  # Computer Communication Equipment
        3577,  # Computer Peripheral Equipment, NEC
        3578,  # Calculating & Accounting Machines
        3579,  # Office Machines, NEC
        3661,  # Telephone & Telegraph Apparatus
        3663,  # Radio & TV Broadcasting Equipment
        3669,  # Communications Equipment, NEC
        3674,  # Semiconductors (NVDA, AMD)
        3679,  # Electronic Components, NEC
        7370,  # Computer Programming Services (GOOGL, META)
        7371,  # Computer Programming Services
        7372,  # Prepackaged Software (MSFT)
        7373,  # Computer Integrated Systems Design
        7374,  # Computer Processing & Data Preparation
        7375,  # Information Retrieval Services
        7376,  # Computer Facilities Management Services
        7377,  # Computer Rental & Leasing
        7378,  # Computer Maintenance & Repair
        7379,  # Computer Related Services, NEC
    },
    income_fields=[
        'revenue',
        'product_revenue',
        'service_revenue',
        'subscription_revenue',
        'cost_of_revenue',
        'gross_profit',
        'rd_expenses',
        'sales_marketing',
        'ga_expenses',
        'stock_compensation',
        'operating_income',
        'ebitda',
        'net_income',
        'eps_diluted',
    ],
    balance_fields=[
        'cash',
        'st_investments',
        'receivables',
        'inventory',
        'deferred_revenue',
        'total_assets',
        'total_liabilities',
        'total_equity',
    ],
    cashflow_fields=[
        'operating_cf',
        'capex',
        'stock_repurchased',
        'dividends_paid',
        'free_cash_flow',
    ],
    key_metrics=[
        'gross_margin',
        'operating_margin',
        'net_margin',
        'revenue_growth_yoy',
        'rd_as_percent_of_revenue',
    ]
)

RETAIL_PROFILE = IndustryProfile(
    name="Retail",
    sic_codes={
        5200,  # Building Materials, Hardware
        5211,  # Lumber & Building Materials Dealers
        5231,  # Paint, Glass & Wallpaper Stores
        5251,  # Hardware Stores
        5261,  # Retail Nurseries, Lawn & Garden Supply
        5271,  # Mobile Home Dealers
        5311,  # Department Stores
        5331,  # Variety Stores (WMT, TGT)
        5399,  # Miscellaneous General Merchandise
        5411,  # Grocery Stores
        5412,  # Convenience Stores
        5441,  # Candy, Nut & Confectionery Stores
        5451,  # Dairy Products Stores
        5461,  # Retail Bakeries
        5499,  # Miscellaneous Food Stores
        5500,  # Auto Dealers & Gas Stations
        5531,  # Auto & Home Supply Stores
        5600,  # Apparel & Accessory Stores
        5700,  # Home Furniture & Equipment Stores
        5812,  # Eating Places
        5912,  # Drug Stores
        5940,  # Miscellaneous Shopping Goods
        5961,  # Catalog & Mail-Order Houses (AMZN)
        5990,  # Retail Stores, NEC
    },
    income_fields=[
        'revenue',
        'net_sales',
        'cost_of_revenue',
        'gross_profit',
        'sga_expenses',
        'store_operating_expense',
        'fulfillment_expense',  # E-commerce
        'operating_income',
        'ebitda',
        'net_income',
        'eps_diluted',
    ],
    balance_fields=[
        'cash',
        'inventory',
        'receivables',
        'ppe',
        'accounts_payable',
        'total_assets',
        'total_liabilities',
        'total_equity',
    ],
    cashflow_fields=[
        'operating_cf',
        'capex',
        'inventory_change',
        'dividends_paid',
        'free_cash_flow',
    ],
    key_metrics=[
        'gross_margin',
        'operating_margin',
        'same_store_sales_growth',
        'inventory_turnover',
        'return_on_invested_capital',
    ]
)

HEALTHCARE_PROFILE = IndustryProfile(
    name="Healthcare",
    sic_codes={
        2833,  # Medicinal Chemicals & Botanical Products
        2834,  # Pharmaceutical Preparations
        2835,  # In Vitro & In Vivo Diagnostic Substances
        2836,  # Biological Products, Except Diagnostic
        3826,  # Laboratory Analytical Instruments
        3841,  # Surgical & Medical Instruments
        3842,  # Orthopedic, Prosthetic & Surgical Appliances
        3843,  # Dental Equipment & Supplies
        3844,  # X-Ray Apparatus & Tubes
        3845,  # Electromedical & Electrotherapeutic Apparatus
        3851,  # Ophthalmic Goods
        8000,  # Health Services
        8011,  # Offices & Clinics of Doctors of Medicine
        8050,  # Nursing & Personal Care Facilities
        8060,  # Hospitals
        8071,  # Medical Laboratories
        8082,  # Home Health Care Services
        8090,  # Miscellaneous Health & Allied Services
    },
    income_fields=[
        'revenue',
        'product_sales',
        'service_revenue',
        'cost_of_revenue',
        'gross_profit',
        'rd_expenses',  # Muy importante en pharma
        'sga_expenses',
        'operating_income',
        'net_income',
        'eps_diluted',
    ],
    balance_fields=[
        'cash',
        'inventory',
        'intangibles',  # Patentes
        'goodwill',
        'total_assets',
        'total_liabilities',
        'total_equity',
    ],
    cashflow_fields=[
        'operating_cf',
        'rd_capitalized',
        'acquisitions',
        'free_cash_flow',
    ],
    key_metrics=[
        'gross_margin',
        'rd_as_percent_of_revenue',
        'pipeline_value',  # Pharma
        'operating_margin',
    ]
)

# =============================================================================
# MAPEO Y UTILIDADES
# =============================================================================

# Todos los perfiles
ALL_PROFILES: Dict[str, IndustryProfile] = {
    'insurance': INSURANCE_PROFILE,
    'banking': BANKING_PROFILE,
    'real_estate': REAL_ESTATE_PROFILE,
    'technology': TECHNOLOGY_PROFILE,
    'retail': RETAIL_PROFILE,
    'healthcare': HEALTHCARE_PROFILE,
}

# Mapeo SIC -> Industria para búsqueda rápida
SIC_TO_INDUSTRY: Dict[int, str] = {}
for industry_name, profile in ALL_PROFILES.items():
    for sic in profile.sic_codes:
        SIC_TO_INDUSTRY[sic] = industry_name


def get_industry_from_sic(sic_code: int) -> Optional[str]:
    """Obtener nombre de industria desde SIC code."""
    return SIC_TO_INDUSTRY.get(sic_code)


def get_profile_from_sic(sic_code: int) -> Optional[IndustryProfile]:
    """Obtener perfil completo desde SIC code."""
    industry = get_industry_from_sic(sic_code)
    if industry:
        return ALL_PROFILES.get(industry)
    return None


def get_profile_by_name(industry_name: str) -> Optional[IndustryProfile]:
    """Obtener perfil por nombre de industria."""
    return ALL_PROFILES.get(industry_name.lower())


def get_prominent_fields(sic_code: int, statement_type: str) -> List[str]:
    """
    Obtener campos que deben mostrarse prominentemente para una industria.
    
    Args:
        sic_code: Código SIC de la empresa
        statement_type: 'income', 'balance', 'cashflow'
    
    Returns:
        Lista de keys de campos a mostrar prominentemente
    """
    profile = get_profile_from_sic(sic_code)
    if not profile:
        return []
    
    if statement_type == 'income':
        return profile.income_fields
    elif statement_type == 'balance':
        return profile.balance_fields
    elif statement_type == 'cashflow':
        return profile.cashflow_fields
    return []


def should_show_field(sic_code: int, field_key: str, statement_type: str) -> bool:
    """
    Determinar si un campo debe mostrarse para una industria específica.
    
    Campos en el perfil de la industria se muestran siempre.
    Campos estándar (revenue, net_income, etc.) se muestran siempre.
    Campos específicos de otras industrias se ocultan.
    """
    # Campos universales que siempre se muestran
    universal_fields = {
        'revenue', 'cost_of_revenue', 'gross_profit', 'operating_income',
        'net_income', 'ebitda', 'eps_basic', 'eps_diluted',
        'total_assets', 'total_liabilities', 'total_equity',
        'operating_cf', 'investing_cf', 'financing_cf', 'free_cash_flow',
        'cash', 'receivables', 'inventory', 'ppe', 'goodwill',
        'accounts_payable', 'lt_debt', 'st_debt',
    }
    
    if field_key in universal_fields:
        return True
    
    # Si tenemos perfil, verificar si el campo está en él
    profile = get_profile_from_sic(sic_code)
    if profile:
        all_profile_fields = set(
            profile.income_fields + 
            profile.balance_fields + 
            profile.cashflow_fields
        )
        return field_key in all_profile_fields
    
    # Sin perfil, mostrar todo
    return True


# =============================================================================
# EJEMPLOS DE USO
# =============================================================================
if __name__ == "__main__":
    # Test
    test_sics = [
        (6324, "UNH - Insurance"),
        (6022, "JPM - Banking"),
        (7370, "GOOGL - Technology"),
        (5331, "WMT - Retail"),
        (5961, "AMZN - Retail/E-commerce"),
        (3571, "AAPL - Technology"),
        (2834, "Pharma - Healthcare"),
    ]
    
    for sic, name in test_sics:
        industry = get_industry_from_sic(sic)
        profile = get_profile_from_sic(sic)
        print(f"{name} (SIC {sic}): {industry or 'Unknown'}")
        if profile:
            print(f"  Key income fields: {profile.income_fields[:5]}")
        print()

