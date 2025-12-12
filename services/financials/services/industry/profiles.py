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
    sic_codes: Set[int]
    income_fields: List[str]
    balance_fields: List[str]
    cashflow_fields: List[str]
    key_metrics: List[str]


# =============================================================================
# PERFILES POR INDUSTRIA
# =============================================================================

INSURANCE_PROFILE = IndustryProfile(
    name="Insurance",
    sic_codes={
        6311, 6321, 6324, 6331, 6351, 6361, 6399, 6411,
    },
    income_fields=[
        'premiums_earned_net', 'premiums_written_gross', 'premiums_written_net',
        'interest_and_dividend_income_operating', 'fee_income', 'other_income', 'revenue',
        'policyholder_benefits_and_claims_incurred_net', 'interest_credited_to_policyholder_account_balances',
        'policyholder_dividends', 'liability_for_future_policy_benefits_period_expense',
        'deferred_policy_acquisition_cost_amortization_expense', 'general_insurance_expense',
        'cost_of_revenue', 'operating_income', 'net_income', 'eps_diluted',
    ],
    balance_fields=[
        'investments_total', 'reinsurance_recoverables', 'deferred_policy_acquisition_costs',
        'policy_liabilities', 'unearned_premiums', 'claims_and_claims_expense',
        'total_assets', 'total_liabilities', 'total_equity',
    ],
    cashflow_fields=[
        'operating_cf', 'premiums_collected', 'claims_paid',
        'investment_income_received', 'free_cash_flow',
    ],
    key_metrics=[
        'combined_ratio', 'loss_ratio', 'expense_ratio',
        'medical_loss_ratio', 'return_on_equity',
    ]
)

BANKING_PROFILE = IndustryProfile(
    name="Banking",
    sic_codes={
        6020, 6021, 6022, 6029, 6035, 6036, 6099, 6141,
        6153, 6159, 6162, 6172, 6199, 6211, 6221, 6282,
    },
    income_fields=[
        'interest_income_expense_net', 'interest_and_fee_income_loans_and_leases',
        'interest_and_dividend_income_securities', 'interest_income_operating',
        'interest_expense_deposits', 'interest_expense_borrowings', 'interest_expense_operating',
        'provision_for_loan_losses_expensed', 'provision_for_loan_lease_and_other_losses',
        'noninterest_income', 'fee_and_commission_income', 'trading_gains_losses',
        'investment_banking_revenue', 'noninterest_expense',
        'operating_income', 'net_income', 'eps_diluted',
    ],
    balance_fields=[
        'loans_and_leases_receivable_net', 'deposits', 'federal_funds_sold',
        'securities_available_for_sale', 'securities_held_to_maturity',
        'allowance_for_loan_losses', 'total_assets', 'total_liabilities', 'total_equity',
    ],
    cashflow_fields=[
        'operating_cf', 'loans_originated', 'deposits_change', 'free_cash_flow',
    ],
    key_metrics=[
        'net_interest_margin', 'efficiency_ratio', 'return_on_assets',
        'return_on_equity', 'tier_1_capital_ratio', 'loan_to_deposit_ratio',
    ]
)

REAL_ESTATE_PROFILE = IndustryProfile(
    name="Real Estate",
    sic_codes={
        6500, 6510, 6512, 6513, 6514, 6515, 6517, 6519,
        6531, 6532, 6552, 6798,
    },
    income_fields=[
        'rental_revenue', 'real_estate_revenue_net', 'tenant_reimbursements',
        'property_operating_expense', 'depreciation_real_estate', 'interest_expense',
        'funds_from_operations', 'net_income', 'eps_diluted',
    ],
    balance_fields=[
        'real_estate_investment_property_net', 'land_and_land_improvements',
        'buildings_and_improvements', 'mortgage_loans_payable',
        'total_assets', 'total_liabilities', 'total_equity',
    ],
    cashflow_fields=[
        'operating_cf', 'acquisitions_of_real_estate', 'capital_expenditures_real_estate',
        'dividends_paid', 'free_cash_flow',
    ],
    key_metrics=[
        'funds_from_operations_per_share', 'adjusted_ffo_per_share',
        'net_asset_value_per_share', 'occupancy_rate', 'cap_rate',
    ]
)

TECHNOLOGY_PROFILE = IndustryProfile(
    name="Technology",
    sic_codes={
        3571, 3572, 3575, 3576, 3577, 3578, 3579,
        3661, 3663, 3669, 3674, 3679,
        7370, 7371, 7372, 7373, 7374, 7375, 7376, 7377, 7378, 7379,
    },
    income_fields=[
        'revenue', 'product_revenue', 'service_revenue', 'subscription_revenue',
        'cost_of_revenue', 'gross_profit', 'rd_expenses', 'sales_marketing',
        'ga_expenses', 'stock_compensation', 'operating_income', 'ebitda',
        'net_income', 'eps_diluted',
    ],
    balance_fields=[
        'cash', 'st_investments', 'receivables', 'inventory', 'deferred_revenue',
        'total_assets', 'total_liabilities', 'total_equity',
    ],
    cashflow_fields=[
        'operating_cf', 'capex', 'stock_repurchased', 'dividends_paid', 'free_cash_flow',
    ],
    key_metrics=[
        'gross_margin', 'operating_margin', 'net_margin',
        'revenue_growth_yoy', 'rd_as_percent_of_revenue',
    ]
)

RETAIL_PROFILE = IndustryProfile(
    name="Retail",
    sic_codes={
        5200, 5211, 5231, 5251, 5261, 5271, 5311, 5331, 5399,
        5411, 5412, 5441, 5451, 5461, 5499, 5500, 5531,
        5600, 5700, 5812, 5912, 5940, 5961, 5990,
    },
    income_fields=[
        'revenue', 'net_sales', 'cost_of_revenue', 'gross_profit',
        'sga_expenses', 'store_operating_expense', 'fulfillment_expense',
        'operating_income', 'ebitda', 'net_income', 'eps_diluted',
    ],
    balance_fields=[
        'cash', 'inventory', 'receivables', 'ppe', 'accounts_payable',
        'total_assets', 'total_liabilities', 'total_equity',
    ],
    cashflow_fields=[
        'operating_cf', 'capex', 'inventory_change', 'dividends_paid', 'free_cash_flow',
    ],
    key_metrics=[
        'gross_margin', 'operating_margin', 'same_store_sales_growth',
        'inventory_turnover', 'return_on_invested_capital',
    ]
)

HEALTHCARE_PROFILE = IndustryProfile(
    name="Healthcare",
    sic_codes={
        2833, 2834, 2835, 2836, 3826, 3841, 3842, 3843, 3844, 3845, 3851,
        8000, 8011, 8050, 8060, 8071, 8082, 8090,
    },
    income_fields=[
        'revenue', 'product_sales', 'service_revenue', 'cost_of_revenue', 'gross_profit',
        'rd_expenses', 'sga_expenses', 'operating_income', 'net_income', 'eps_diluted',
    ],
    balance_fields=[
        'cash', 'inventory', 'intangibles', 'goodwill',
        'total_assets', 'total_liabilities', 'total_equity',
    ],
    cashflow_fields=[
        'operating_cf', 'rd_capitalized', 'acquisitions', 'free_cash_flow',
    ],
    key_metrics=[
        'gross_margin', 'rd_as_percent_of_revenue', 'pipeline_value', 'operating_margin',
    ]
)


# =============================================================================
# MAPEO Y UTILIDADES
# =============================================================================

ALL_PROFILES: Dict[str, IndustryProfile] = {
    'insurance': INSURANCE_PROFILE,
    'banking': BANKING_PROFILE,
    'real_estate': REAL_ESTATE_PROFILE,
    'technology': TECHNOLOGY_PROFILE,
    'retail': RETAIL_PROFILE,
    'healthcare': HEALTHCARE_PROFILE,
}

# Mapeo SIC -> Industria
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
    """
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
    
    profile = get_profile_from_sic(sic_code)
    if profile:
        all_profile_fields = set(
            profile.income_fields + 
            profile.balance_fields + 
            profile.cashflow_fields
        )
        return field_key in all_profile_fields
    
    return True

