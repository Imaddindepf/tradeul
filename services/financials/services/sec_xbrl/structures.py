"""
SEC XBRL Structures - Estructuras jerárquicas para estados financieros.

Define el orden, secciones e indentación de cada campo.
Soporta estructuras base + específicas por industria.
"""

from typing import Dict, Optional


# =============================================================================
# INCOME STATEMENT STRUCTURE
# =============================================================================

INCOME_STATEMENT_STRUCTURE = {
    # === REVENUE ===
    'revenue':           {'section': 'Revenue',           'order': 100, 'indent': 0, 'is_subtotal': False},
    'revenue_yoy':       {'section': 'Revenue',           'order': 101, 'indent': 1, 'is_subtotal': False},
    
    # === COST & GROSS PROFIT ===
    'cost_of_revenue':   {'section': 'Cost & Gross Profit', 'order': 200, 'indent': 0, 'is_subtotal': False},
    'gross_profit':      {'section': 'Cost & Gross Profit', 'order': 210, 'indent': 0, 'is_subtotal': True},
    'gross_profit_yoy':  {'section': 'Cost & Gross Profit', 'order': 211, 'indent': 1, 'is_subtotal': False},
    'gross_margin':      {'section': 'Cost & Gross Profit', 'order': 212, 'indent': 1, 'is_subtotal': False},
    
    # === OPERATING EXPENSES ===
    'rd_expenses':       {'section': 'Operating Expenses', 'order': 300, 'indent': 1, 'is_subtotal': False},
    'sales_marketing':   {'section': 'Operating Expenses', 'order': 310, 'indent': 1, 'is_subtotal': False},
    'fulfillment_expense':{'section': 'Operating Expenses', 'order': 315, 'indent': 1, 'is_subtotal': False},
    'sga_expenses':      {'section': 'Operating Expenses', 'order': 320, 'indent': 1, 'is_subtotal': False},
    'ga_expenses':       {'section': 'Operating Expenses', 'order': 325, 'indent': 1, 'is_subtotal': False},
    'stock_compensation':{'section': 'Operating Expenses', 'order': 326, 'indent': 1, 'is_subtotal': False},
    'restructuring_charges': {'section': 'Operating Expenses', 'order': 330, 'indent': 1, 'is_subtotal': False},
    'operating_expenses':{'section': 'Operating Expenses', 'order': 390, 'indent': 0, 'is_subtotal': True},
    
    # === OPERATING INCOME ===
    'operating_income':  {'section': 'Operating Income',  'order': 400, 'indent': 0, 'is_subtotal': True},
    'operating_income_yoy': {'section': 'Operating Income', 'order': 401, 'indent': 1, 'is_subtotal': False},
    'operating_margin':  {'section': 'Operating Income',  'order': 402, 'indent': 1, 'is_subtotal': False},
    'depreciation':      {'section': 'Operating Income',  'order': 410, 'indent': 1, 'is_subtotal': False},
    'ebitda':            {'section': 'Operating Income',  'order': 420, 'indent': 0, 'is_subtotal': True},
    'ebitda_margin':     {'section': 'Operating Income',  'order': 421, 'indent': 1, 'is_subtotal': False},
    
    # === NON-OPERATING ===
    'interest_income':   {'section': 'Non-Operating',     'order': 500, 'indent': 1, 'is_subtotal': False},
    'interest_expense':  {'section': 'Non-Operating',     'order': 510, 'indent': 1, 'is_subtotal': False},
    'investment_income': {'section': 'Non-Operating',     'order': 515, 'indent': 1, 'is_subtotal': False},
    'other_income':      {'section': 'Non-Operating',     'order': 520, 'indent': 1, 'is_subtotal': False},
    'gain_loss_securities': {'section': 'Non-Operating',  'order': 530, 'indent': 1, 'is_subtotal': False},
    'gain_loss_business': {'section': 'Non-Operating',    'order': 535, 'indent': 1, 'is_subtotal': False},
    'impairment_charges': {'section': 'Non-Operating',    'order': 540, 'indent': 1, 'is_subtotal': False},
    'unusual_items':     {'section': 'Non-Operating',     'order': 545, 'indent': 1, 'is_subtotal': False},
    'foreign_currency_transaction_gain_loss_before_tax': {'section': 'Non-Operating', 'order': 550, 'indent': 1, 'is_subtotal': False},
    
    # === EARNINGS ===
    'income_before_tax': {'section': 'Earnings',          'order': 600, 'indent': 0, 'is_subtotal': True},
    'income_tax':        {'section': 'Earnings',          'order': 610, 'indent': 1, 'is_subtotal': False},
    'net_income':        {'section': 'Earnings',          'order': 620, 'indent': 0, 'is_subtotal': True},
    'net_margin':        {'section': 'Earnings',          'order': 621, 'indent': 1, 'is_subtotal': False},
    'net_income_yoy':    {'section': 'Earnings',          'order': 622, 'indent': 1, 'is_subtotal': False},
    
    # === PER SHARE DATA ===
    'eps_basic':         {'section': 'Per Share Data',    'order': 700, 'indent': 0, 'is_subtotal': False},
    'eps_diluted':       {'section': 'Per Share Data',    'order': 710, 'indent': 0, 'is_subtotal': False},
    'eps_yoy':           {'section': 'Per Share Data',    'order': 711, 'indent': 1, 'is_subtotal': False},
    'shares_basic':      {'section': 'Per Share Data',    'order': 720, 'indent': 0, 'is_subtotal': False},
    'shares_diluted':    {'section': 'Per Share Data',    'order': 730, 'indent': 0, 'is_subtotal': False},
    'dividend_per_share':{'section': 'Per Share Data',    'order': 740, 'indent': 0, 'is_subtotal': False},
}


# =============================================================================
# BALANCE SHEET STRUCTURE
# =============================================================================

BALANCE_SHEET_STRUCTURE = {
    # === CURRENT ASSETS ===
    'cash':              {'section': 'Current Assets',    'order': 100, 'indent': 1, 'is_subtotal': False},
    'st_investments':    {'section': 'Current Assets',    'order': 110, 'indent': 1, 'is_subtotal': False},
    'receivables':       {'section': 'Current Assets',    'order': 120, 'indent': 1, 'is_subtotal': False},
    'inventory':         {'section': 'Current Assets',    'order': 130, 'indent': 1, 'is_subtotal': False},
    'prepaid':           {'section': 'Current Assets',    'order': 140, 'indent': 1, 'is_subtotal': False},
    'current_assets':    {'section': 'Current Assets',    'order': 190, 'indent': 0, 'is_subtotal': True},
    
    # === NON-CURRENT ASSETS ===
    'ppe':               {'section': 'Non-Current Assets','order': 200, 'indent': 1, 'is_subtotal': False},
    'goodwill':          {'section': 'Non-Current Assets','order': 210, 'indent': 1, 'is_subtotal': False},
    'intangibles':       {'section': 'Non-Current Assets','order': 220, 'indent': 1, 'is_subtotal': False},
    'lt_investments':    {'section': 'Non-Current Assets','order': 230, 'indent': 1, 'is_subtotal': False},
    'total_assets':      {'section': 'Non-Current Assets','order': 290, 'indent': 0, 'is_subtotal': True},
    
    # === CURRENT LIABILITIES ===
    'accounts_payable':  {'section': 'Current Liabilities','order': 300, 'indent': 1, 'is_subtotal': False},
    'accrued_liabilities':{'section': 'Current Liabilities','order': 310, 'indent': 1, 'is_subtotal': False},
    'deferred_revenue':  {'section': 'Current Liabilities','order': 320, 'indent': 1, 'is_subtotal': False},
    'st_debt':           {'section': 'Current Liabilities','order': 330, 'indent': 1, 'is_subtotal': False},
    'current_liabilities':{'section': 'Current Liabilities','order': 390, 'indent': 0, 'is_subtotal': True},
    
    # === NON-CURRENT LIABILITIES ===
    'lt_debt':           {'section': 'Non-Current Liabilities','order': 400, 'indent': 1, 'is_subtotal': False},
    'lease_liability':   {'section': 'Non-Current Liabilities','order': 410, 'indent': 1, 'is_subtotal': False},
    'total_liabilities': {'section': 'Non-Current Liabilities','order': 490, 'indent': 0, 'is_subtotal': True},
    
    # === EQUITY ===
    'common_stock':      {'section': 'Equity',            'order': 500, 'indent': 1, 'is_subtotal': False},
    'apic':              {'section': 'Equity',            'order': 510, 'indent': 1, 'is_subtotal': False},
    'retained_earnings': {'section': 'Equity',            'order': 520, 'indent': 1, 'is_subtotal': False},
    'treasury_stock':    {'section': 'Equity',            'order': 530, 'indent': 1, 'is_subtotal': False},
    'total_equity':      {'section': 'Equity',            'order': 590, 'indent': 0, 'is_subtotal': True},
    
    # === KEY METRICS ===
    'total_debt':        {'section': 'Key Metrics',       'order': 600, 'indent': 0, 'is_subtotal': True},
    'net_debt':          {'section': 'Key Metrics',       'order': 610, 'indent': 1, 'is_subtotal': False},
    'book_value_per_share':{'section': 'Key Metrics',     'order': 620, 'indent': 0, 'is_subtotal': False},
    'tangible_book_value':{'section': 'Key Metrics',      'order': 630, 'indent': 0, 'is_subtotal': False},
    'tangible_book_value_per_share':{'section': 'Key Metrics','order': 631, 'indent': 1, 'is_subtotal': False},
}


# =============================================================================
# CASH FLOW STRUCTURE
# =============================================================================

CASH_FLOW_STRUCTURE = {
    # === OPERATING ACTIVITIES ===
    'net_income':        {'section': 'Operating Activities','order': 100, 'indent': 1, 'is_subtotal': False},
    'depreciation':      {'section': 'Operating Activities','order': 110, 'indent': 1, 'is_subtotal': False},
    'amortization':      {'section': 'Operating Activities','order': 111, 'indent': 1, 'is_subtotal': False},
    'stock_compensation':{'section': 'Operating Activities','order': 120, 'indent': 1, 'is_subtotal': False},
    'debt_and_equity_securities_gain_loss':{'section': 'Operating Activities','order': 125, 'indent': 1, 'is_subtotal': False},
    'deferred_income_taxes_and_tax_credits':{'section': 'Operating Activities','order': 130, 'indent': 1, 'is_subtotal': False},
    'other_noncash_income_expense':{'section': 'Operating Activities','order': 135, 'indent': 1, 'is_subtotal': False},
    'receivables':       {'section': 'Operating Activities','order': 140, 'indent': 1, 'is_subtotal': False},
    'accounts_payable':  {'section': 'Operating Activities','order': 145, 'indent': 1, 'is_subtotal': False},
    'accrued_liabilities':{'section': 'Operating Activities','order': 146, 'indent': 1, 'is_subtotal': False},
    'deferred_revenue':  {'section': 'Operating Activities','order': 150, 'indent': 1, 'is_subtotal': False},
    'increase_decrease_in_income_taxes':{'section': 'Operating Activities','order': 155, 'indent': 1, 'is_subtotal': False},
    'increase_decrease_in_other_operating_assets':{'section': 'Operating Activities','order': 160, 'indent': 1, 'is_subtotal': False},
    'other_income':      {'section': 'Operating Activities','order': 165, 'indent': 1, 'is_subtotal': False},
    'operating_cf':      {'section': 'Operating Activities','order': 190, 'indent': 0, 'is_subtotal': True},
    
    # === INVESTING ACTIVITIES ===
    'ppe':               {'section': 'Investing Activities','order': 200, 'indent': 1, 'is_subtotal': False, 'label': 'Capital Expenditures'},
    'capex':             {'section': 'Investing Activities','order': 201, 'indent': 1, 'is_subtotal': False},
    'payments_to_acquire_marketable_securities':{'section': 'Investing Activities','order': 210, 'indent': 1, 'is_subtotal': False},
    'proceeds_from_sale_and_maturity_of_marketable_securities':{'section': 'Investing Activities','order': 215, 'indent': 1, 'is_subtotal': False},
    'purchase_investments':{'section': 'Investing Activities','order': 220, 'indent': 1, 'is_subtotal': False},
    'sale_investments':  {'section': 'Investing Activities','order': 225, 'indent': 1, 'is_subtotal': False},
    'intangibles':       {'section': 'Investing Activities','order': 230, 'indent': 1, 'is_subtotal': False},
    'investing_cf':      {'section': 'Investing Activities','order': 290, 'indent': 0, 'is_subtotal': True},
    
    # === FINANCING ACTIVITIES ===
    'debt_issued':       {'section': 'Financing Activities','order': 300, 'indent': 1, 'is_subtotal': False},
    'debt_repaid':       {'section': 'Financing Activities','order': 310, 'indent': 1, 'is_subtotal': False},
    'stock_repurchased': {'section': 'Financing Activities','order': 320, 'indent': 1, 'is_subtotal': False},
    'dividends_paid':    {'section': 'Financing Activities','order': 330, 'indent': 1, 'is_subtotal': False},
    'stock_issued':      {'section': 'Financing Activities','order': 340, 'indent': 1, 'is_subtotal': False},
    'operating_lease_payments':{'section': 'Financing Activities','order': 350, 'indent': 1, 'is_subtotal': False},
    'finance_lease_principal_payments':{'section': 'Financing Activities','order': 355, 'indent': 1, 'is_subtotal': False},
    'financing_cf':      {'section': 'Financing Activities','order': 390, 'indent': 0, 'is_subtotal': True},
    
    # === SUMMARY ===
    'cash':              {'section': 'Summary',            'order': 395, 'indent': 1, 'is_subtotal': False},
    
    # === FREE CASH FLOW ===
    'free_cash_flow':    {'section': 'Free Cash Flow',    'order': 400, 'indent': 0, 'is_subtotal': True},
    'fcf_margin':        {'section': 'Free Cash Flow',    'order': 410, 'indent': 1, 'is_subtotal': False},
    'fcf_per_share':     {'section': 'Free Cash Flow',    'order': 420, 'indent': 1, 'is_subtotal': False},
}


# =============================================================================
# INDUSTRY-SPECIFIC STRUCTURES
# =============================================================================

INDUSTRY_INCOME_STRUCTURES = {
    'insurance': {
        'premiums_earned_net':    {'section': 'Revenue', 'order': 102, 'indent': 1, 'is_subtotal': False, 'label': 'Premiums Earned, Net'},
        'premiums_written_gross': {'section': 'Revenue', 'order': 103, 'indent': 2, 'is_subtotal': False, 'label': 'Gross Premiums Written'},
        'premiums_written_net':   {'section': 'Revenue', 'order': 104, 'indent': 2, 'is_subtotal': False, 'label': 'Net Premiums Written'},
        'fee_income':             {'section': 'Revenue', 'order': 105, 'indent': 1, 'is_subtotal': False, 'label': 'Service Revenue / Fees'},
        'product_revenue':        {'section': 'Revenue', 'order': 106, 'indent': 1, 'is_subtotal': False, 'label': 'Product Revenue'},
        'investment_income':      {'section': 'Revenue', 'order': 107, 'indent': 1, 'is_subtotal': False, 'label': 'Investment Income'},
        'policyholder_benefits_and_claims_incurred_net': {'section': 'Cost & Gross Profit', 'order': 201, 'indent': 1, 'is_subtotal': False, 'label': 'Policyholder Benefits & Claims'},
        'policyholder_benefits':  {'section': 'Cost & Gross Profit', 'order': 202, 'indent': 1, 'is_subtotal': False, 'label': 'Policyholder Benefits'},
        'medical_costs':          {'section': 'Cost & Gross Profit', 'order': 203, 'indent': 2, 'is_subtotal': False, 'label': 'Medical Costs'},
        'policyholder_dividends': {'section': 'Cost & Gross Profit', 'order': 204, 'indent': 2, 'is_subtotal': False, 'label': 'Policyholder Dividends'},
        'policy_acquisition_costs':{'section': 'Cost & Gross Profit', 'order': 205, 'indent': 2, 'is_subtotal': False, 'label': 'Policy Acquisition Costs'},
        'insurance_expenses':     {'section': 'Cost & Gross Profit', 'order': 206, 'indent': 2, 'is_subtotal': False, 'label': 'Insurance Expenses'},
    },
    'banking': {
        'interest_income':        {'section': 'Revenue', 'order': 102, 'indent': 1, 'is_subtotal': False, 'label': 'Interest Income'},
        'interest_and_fee_income':{'section': 'Revenue', 'order': 103, 'indent': 2, 'is_subtotal': False, 'label': 'Interest & Fee Income'},
        'interest_expense':       {'section': 'Revenue', 'order': 104, 'indent': 1, 'is_subtotal': False, 'label': 'Interest Expense'},
        'net_interest_income':    {'section': 'Revenue', 'order': 105, 'indent': 1, 'is_subtotal': True, 'label': 'Net Interest Income'},
        'provision_for_loan_losses': {'section': 'Cost & Gross Profit', 'order': 201, 'indent': 1, 'is_subtotal': False, 'label': 'Provision for Loan Losses'},
        'credit_loss_expense':    {'section': 'Cost & Gross Profit', 'order': 202, 'indent': 2, 'is_subtotal': False, 'label': 'Credit Loss Expense'},
        'noninterest_income':     {'section': 'Revenue', 'order': 106, 'indent': 1, 'is_subtotal': True, 'label': 'Non-Interest Income'},
        'fee_and_commission':     {'section': 'Revenue', 'order': 107, 'indent': 2, 'is_subtotal': False, 'label': 'Fees & Commissions'},
        'trading_revenue':        {'section': 'Revenue', 'order': 108, 'indent': 2, 'is_subtotal': False, 'label': 'Trading Revenue'},
        'investment_banking':     {'section': 'Revenue', 'order': 109, 'indent': 2, 'is_subtotal': False, 'label': 'Investment Banking'},
        'noninterest_expense':    {'section': 'Operating Expenses', 'order': 301, 'indent': 1, 'is_subtotal': True, 'label': 'Non-Interest Expense'},
        'compensation_expense':   {'section': 'Operating Expenses', 'order': 302, 'indent': 2, 'is_subtotal': False, 'label': 'Compensation & Benefits'},
    },
    'real_estate': {
        'rental_revenue':         {'section': 'Revenue', 'order': 102, 'indent': 1, 'is_subtotal': False, 'label': 'Rental Revenue'},
        'tenant_reimbursements':  {'section': 'Revenue', 'order': 103, 'indent': 2, 'is_subtotal': False, 'label': 'Tenant Reimbursements'},
        'property_sales':         {'section': 'Revenue', 'order': 104, 'indent': 1, 'is_subtotal': False, 'label': 'Property Sales'},
        'property_expenses':      {'section': 'Operating Expenses', 'order': 301, 'indent': 1, 'is_subtotal': False, 'label': 'Property Operating Expenses'},
        'depreciation_real_estate':{'section': 'Operating Expenses', 'order': 302, 'indent': 2, 'is_subtotal': False, 'label': 'Real Estate Depreciation'},
        'funds_from_operations':  {'section': 'Earnings', 'order': 625, 'indent': 0, 'is_subtotal': True, 'label': 'Funds From Operations (FFO)'},
        'affo':                   {'section': 'Earnings', 'order': 626, 'indent': 1, 'is_subtotal': False, 'label': 'Adjusted FFO'},
    },
}

INDUSTRY_BALANCE_STRUCTURES = {
    'insurance': {
        'investments':            {'section': 'Non-Current Assets', 'order': 201, 'indent': 1, 'is_subtotal': False, 'label': 'Total Investments'},
        'reinsurance_recoverables':{'section': 'Non-Current Assets', 'order': 202, 'indent': 2, 'is_subtotal': False, 'label': 'Reinsurance Recoverables'},
        'deferred_acquisition_costs':{'section': 'Non-Current Assets', 'order': 203, 'indent': 2, 'is_subtotal': False, 'label': 'Deferred Acquisition Costs'},
        'policy_liabilities':     {'section': 'Non-Current Liabilities', 'order': 401, 'indent': 1, 'is_subtotal': False, 'label': 'Policy Liabilities'},
        'unearned_premiums':      {'section': 'Non-Current Liabilities', 'order': 402, 'indent': 2, 'is_subtotal': False, 'label': 'Unearned Premiums'},
        'claims_payable':         {'section': 'Non-Current Liabilities', 'order': 403, 'indent': 2, 'is_subtotal': False, 'label': 'Claims & Benefits Payable'},
    },
    'banking': {
        'loans_net':              {'section': 'Non-Current Assets', 'order': 201, 'indent': 1, 'is_subtotal': False, 'label': 'Loans & Leases, Net'},
        'allowance_loan_losses':  {'section': 'Non-Current Assets', 'order': 202, 'indent': 2, 'is_subtotal': False, 'label': 'Allowance for Loan Losses'},
        'securities_available':   {'section': 'Non-Current Assets', 'order': 203, 'indent': 1, 'is_subtotal': False, 'label': 'Securities Available for Sale'},
        'securities_held':        {'section': 'Non-Current Assets', 'order': 204, 'indent': 1, 'is_subtotal': False, 'label': 'Securities Held to Maturity'},
        'deposits':               {'section': 'Current Liabilities', 'order': 301, 'indent': 1, 'is_subtotal': False, 'label': 'Total Deposits'},
        'federal_funds':          {'section': 'Current Liabilities', 'order': 302, 'indent': 2, 'is_subtotal': False, 'label': 'Federal Funds Purchased'},
    },
}

INDUSTRY_CASHFLOW_STRUCTURES = {
    'insurance': {
        'premiums_collected':     {'section': 'Operating Activities', 'order': 100, 'indent': 1, 'is_subtotal': False, 'label': 'Premiums Collected'},
        'claims_paid':            {'section': 'Operating Activities', 'order': 105, 'indent': 1, 'is_subtotal': False, 'label': 'Claims & Benefits Paid'},
    },
    'banking': {
        'loans_originated':       {'section': 'Investing Activities', 'order': 200, 'indent': 1, 'is_subtotal': False, 'label': 'Loans Originated/Purchased'},
        'deposits_change':        {'section': 'Financing Activities', 'order': 300, 'indent': 1, 'is_subtotal': False, 'label': 'Change in Deposits'},
    },
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_structure(statement_type: str, industry: Optional[str] = None) -> Dict:
    """
    Obtener estructura combinada: base + industria específica.
    
    Args:
        statement_type: 'income', 'balance', 'cashflow'
        industry: 'insurance', 'banking', 'real_estate', etc.
    
    Returns:
        Dict con la estructura combinada
    """
    if statement_type == 'income':
        base = INCOME_STATEMENT_STRUCTURE.copy()
        industry_struct = INDUSTRY_INCOME_STRUCTURES.get(industry, {})
    elif statement_type == 'balance':
        base = BALANCE_SHEET_STRUCTURE.copy()
        industry_struct = INDUSTRY_BALANCE_STRUCTURES.get(industry, {})
    elif statement_type == 'cashflow':
        base = CASH_FLOW_STRUCTURE.copy()
        industry_struct = INDUSTRY_CASHFLOW_STRUCTURES.get(industry, {})
    else:
        return {}
    
    # Combinar: industria tiene prioridad
    base.update(industry_struct)
    return base


# Labels personalizados
CUSTOM_LABELS = {
    'ppe': 'Capital Expenditures',
    'operating_cf': 'Cash from Operations',
    'investing_cf': 'Cash from Investing',
    'financing_cf': 'Cash from Financing',
    'free_cash_flow': 'Free Cash Flow',
    'fcf_margin': 'FCF Margin %',
    'fcf_per_share': 'FCF per Share',
    'debt_and_equity_securities_gain_loss': '(Gain) Loss on Investments',
    'deferred_income_taxes_and_tax_credits': 'Deferred Taxes',
    'increase_decrease_in_income_taxes': 'Change in Income Taxes',
    'increase_decrease_in_other_operating_assets': 'Change in Other Assets',
    'payments_to_acquire_marketable_securities': 'Purchase of Securities',
    'proceeds_from_sale_and_maturity_of_marketable_securities': 'Sale of Securities',
    'book_value_per_share': 'Book Value per Share',
    'tangible_book_value': 'Tangible Book Value',
    'tangible_book_value_per_share': 'Tangible Book Value per Share',
}

