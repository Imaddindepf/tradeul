"""
SEC XBRL Structures - Estructuras jerárquicas para estados financieros.

Define el orden, secciones e indentación de cada campo.
Soporta estructuras base + específicas por industria.

SINCRONIZADO CON: services/mapping/schema.py
"""

from typing import Dict, Optional


# =============================================================================
# INCOME STATEMENT STRUCTURE (Expandido)
# =============================================================================

INCOME_STATEMENT_STRUCTURE = {
    # === REVENUE (100-199) ===
    # Para empresas donde Revenue incluye Interest Income (fintech, banking, crypto):
    'operating_revenue':    {'section': 'Revenue',              'order': 90,  'indent': 0, 'is_subtotal': False},
    'interest_income_revenue': {'section': 'Revenue',           'order': 95,  'indent': 0, 'is_subtotal': False},
    'other_revenue':        {'section': 'Revenue',              'order': 98,  'indent': 0, 'is_subtotal': False},
    'revenue':              {'section': 'Revenue',              'order': 100, 'indent': 0, 'is_subtotal': True},
    'revenue_yoy':          {'section': 'Revenue',              'order': 101, 'indent': 1, 'is_subtotal': False},
    'product_revenue':      {'section': 'Revenue',              'order': 110, 'indent': 1, 'is_subtotal': False},
    'service_revenue':      {'section': 'Revenue',              'order': 111, 'indent': 1, 'is_subtotal': False},
    'subscription_revenue': {'section': 'Revenue',              'order': 112, 'indent': 1, 'is_subtotal': False},
    'membership_fees':      {'section': 'Revenue',              'order': 113, 'indent': 1, 'is_subtotal': False},
    
    # === COST & GROSS PROFIT (200-299) ===
    'cost_of_revenue':      {'section': 'Cost & Gross Profit',  'order': 200, 'indent': 0, 'is_subtotal': False},
    'cost_of_goods_sold':   {'section': 'Cost & Gross Profit',  'order': 201, 'indent': 1, 'is_subtotal': False},
    'cost_of_services':     {'section': 'Cost & Gross Profit',  'order': 202, 'indent': 1, 'is_subtotal': False},
    'gross_profit':         {'section': 'Cost & Gross Profit',  'order': 210, 'indent': 0, 'is_subtotal': True},
    'gross_profit_yoy':     {'section': 'Cost & Gross Profit',  'order': 211, 'indent': 1, 'is_subtotal': False},
    'gross_margin':         {'section': 'Cost & Gross Profit',  'order': 212, 'indent': 1, 'is_subtotal': False},
    
    # === OPERATING EXPENSES (300-399) ===
    'rd_expenses':          {'section': 'Operating Expenses',   'order': 300, 'indent': 1, 'is_subtotal': False},
    'sga_expenses':         {'section': 'Operating Expenses',   'order': 310, 'indent': 1, 'is_subtotal': False},
    'sales_marketing':      {'section': 'Operating Expenses',   'order': 320, 'indent': 1, 'is_subtotal': False},
    'ga_expenses':          {'section': 'Operating Expenses',   'order': 325, 'indent': 1, 'is_subtotal': False},
    'fulfillment_expense':  {'section': 'Operating Expenses',   'order': 330, 'indent': 1, 'is_subtotal': False},
    'pre_opening_costs':    {'section': 'Operating Expenses',   'order': 335, 'indent': 1, 'is_subtotal': False},
    # SBC and D&A are non-cash items shown in EBITDA section (already embedded in SG&A/R&D per GAAP)
    'restructuring_charges':{'section': 'Operating Expenses',   'order': 360, 'indent': 1, 'is_subtotal': False},
    'other_operating_expenses': {'section': 'Operating Expenses', 'order': 380, 'indent': 1, 'is_subtotal': False},
    'total_operating_expenses': {'section': 'Operating Expenses', 'order': 390, 'indent': 0, 'is_subtotal': True},
    # Alias legacy
    'operating_expenses':   {'section': 'Operating Expenses',   'order': 391, 'indent': 0, 'is_subtotal': True},
    
    # === OPERATING INCOME (400-449) ===
    'operating_income':     {'section': 'Operating Income',     'order': 400, 'indent': 0, 'is_subtotal': True},
    'operating_income_yoy': {'section': 'Operating Income',     'order': 401, 'indent': 1, 'is_subtotal': False},
    'operating_margin':     {'section': 'Operating Income',     'order': 402, 'indent': 1, 'is_subtotal': False},
    
    # === EBITDA (450-499) ===
    # SBC and D&A are non-cash items - shown here as memo/supplementary data
    'stock_compensation':   {'section': 'EBITDA',               'order': 451, 'indent': 1, 'is_subtotal': False, 'label': 'Stock-Based Compensation'},
    'depreciation_amortization': {'section': 'EBITDA',          'order': 452, 'indent': 1, 'is_subtotal': False, 'label': 'Depreciation & Amortization'},
    'depreciation':         {'section': 'EBITDA',               'order': 453, 'indent': 1, 'is_subtotal': False},
    'ebitda':               {'section': 'EBITDA',               'order': 460, 'indent': 0, 'is_subtotal': True},
    'ebitda_yoy':           {'section': 'EBITDA',               'order': 461, 'indent': 1, 'is_subtotal': False},
    'ebitda_margin':        {'section': 'EBITDA',               'order': 462, 'indent': 1, 'is_subtotal': False},
    'ebitdar':              {'section': 'EBITDA',               'order': 470, 'indent': 0, 'is_subtotal': True},
    
    # === NON-OPERATING (500-599) ===
    'interest_expense':     {'section': 'Non-Operating',        'order': 500, 'indent': 1, 'is_subtotal': False},
    'interest_income':      {'section': 'Non-Operating',        'order': 510, 'indent': 1, 'is_subtotal': False},
    'interest_and_other_income': {'section': 'Non-Operating',   'order': 515, 'indent': 1, 'is_subtotal': False},
    'investment_income':    {'section': 'Non-Operating',        'order': 520, 'indent': 1, 'is_subtotal': False},
    'equity_method_income': {'section': 'Non-Operating',        'order': 525, 'indent': 1, 'is_subtotal': False},
    'foreign_exchange_gain_loss': {'section': 'Non-Operating',  'order': 530, 'indent': 1, 'is_subtotal': False},
    'gain_loss_securities': {'section': 'Non-Operating',        'order': 540, 'indent': 1, 'is_subtotal': False},
    'gain_loss_sale_assets':{'section': 'Non-Operating',        'order': 545, 'indent': 1, 'is_subtotal': False},
    'impairment_charges':   {'section': 'Non-Operating',        'order': 550, 'indent': 1, 'is_subtotal': False},
    'crypto_gains_nonoperating': {'section': 'Non-Operating',   'order': 560, 'indent': 1, 'is_subtotal': False},
    'interest_investment_income': {'section': 'Non-Operating',  'order': 565, 'indent': 1, 'is_subtotal': False},
    'other_nonoperating':   {'section': 'Non-Operating',        'order': 580, 'indent': 1, 'is_subtotal': False},
    'total_nonoperating':   {'section': 'Non-Operating',        'order': 590, 'indent': 0, 'is_subtotal': True},
    # Legacy aliases
    'other_income':         {'section': 'Non-Operating',        'order': 581, 'indent': 1, 'is_subtotal': False},
    'gain_loss_business':   {'section': 'Non-Operating',        'order': 546, 'indent': 1, 'is_subtotal': False},
    'foreign_currency_transaction_gain_loss_before_tax': {'section': 'Non-Operating', 'order': 531, 'indent': 1, 'is_subtotal': False},
    
    # === EARNINGS (600-699) ===
    'ebt_excl_unusual':     {'section': 'Earnings',             'order': 600, 'indent': 0, 'is_subtotal': True},
    # Unusual items breakdown (TIKR style)
    'merger_restructuring': {'section': 'Earnings',             'order': 601, 'indent': 1, 'is_subtotal': False},
    'restructuring_charges':{'section': 'Earnings',             'order': 602, 'indent': 1, 'is_subtotal': False},
    'gain_loss_investments':{'section': 'Earnings',             'order': 603, 'indent': 1, 'is_subtotal': False},
    'asset_writedown_unusual':{'section': 'Earnings',           'order': 604, 'indent': 1, 'is_subtotal': False},
    'legal_settlements':    {'section': 'Earnings',             'order': 605, 'indent': 1, 'is_subtotal': False},
    'other_unusual_items':  {'section': 'Earnings',             'order': 606, 'indent': 1, 'is_subtotal': False},
    'unusual_items':        {'section': 'Earnings',             'order': 607, 'indent': 1, 'is_subtotal': False},
    'income_before_tax':    {'section': 'Earnings',             'order': 610, 'indent': 0, 'is_subtotal': True},
    'income_tax':           {'section': 'Earnings',             'order': 650, 'indent': 1, 'is_subtotal': False},
    'effective_tax_rate':   {'section': 'Earnings',             'order': 651, 'indent': 2, 'is_subtotal': False},
    'income_continuing_ops':{'section': 'Earnings',             'order': 660, 'indent': 0, 'is_subtotal': True},
    'income_discontinued_ops': {'section': 'Earnings',          'order': 665, 'indent': 1, 'is_subtotal': False},
    'minority_interest':    {'section': 'Earnings',             'order': 670, 'indent': 1, 'is_subtotal': False},
    'net_income':           {'section': 'Earnings',             'order': 680, 'indent': 0, 'is_subtotal': True},
    'preferred_dividends':  {'section': 'Earnings',             'order': 682, 'indent': 1, 'is_subtotal': False},
    'net_income_to_common': {'section': 'Earnings',             'order': 685, 'indent': 0, 'is_subtotal': True},
    'net_margin':           {'section': 'Earnings',             'order': 690, 'indent': 1, 'is_subtotal': False},
    'net_income_to_common_excl':{'section': 'Earnings',         'order': 692, 'indent': 0, 'is_subtotal': True},
    'net_income_yoy':       {'section': 'Earnings',             'order': 691, 'indent': 1, 'is_subtotal': False},
    
    # === PER SHARE DATA (700-799) ===
    'eps_basic':            {'section': 'Per Share Data',       'order': 700, 'indent': 0, 'is_subtotal': False},
    'eps_diluted':          {'section': 'Per Share Data',       'order': 710, 'indent': 0, 'is_subtotal': False},
    'eps_yoy':              {'section': 'Per Share Data',       'order': 711, 'indent': 1, 'is_subtotal': False},
    'shares_basic':         {'section': 'Per Share Data',       'order': 720, 'indent': 0, 'is_subtotal': False},
    'shares_diluted':       {'section': 'Per Share Data',       'order': 730, 'indent': 0, 'is_subtotal': False},
    'dividend_per_share':   {'section': 'Per Share Data',       'order': 740, 'indent': 0, 'is_subtotal': False},
    'special_dividend':     {'section': 'Per Share Data',       'order': 745, 'indent': 0, 'is_subtotal': False},
    'payout_ratio':         {'section': 'Per Share Data',       'order': 750, 'indent': 1, 'is_subtotal': False},
}


# =============================================================================
# BALANCE SHEET STRUCTURE (Expandido)
# =============================================================================

BALANCE_SHEET_STRUCTURE = {
    # === CURRENT ASSETS (100-199) ===
    'cash':                 {'section': 'Current Assets',       'order': 100, 'indent': 1, 'is_subtotal': False},
    'restricted_cash':      {'section': 'Current Assets',       'order': 105, 'indent': 1, 'is_subtotal': False},
    'st_investments':       {'section': 'Current Assets',       'order': 110, 'indent': 1, 'is_subtotal': False},
    'receivables':          {'section': 'Current Assets',       'order': 120, 'indent': 1, 'is_subtotal': False},
    'inventory':            {'section': 'Current Assets',       'order': 130, 'indent': 1, 'is_subtotal': False},
    'prepaid':              {'section': 'Current Assets',       'order': 140, 'indent': 1, 'is_subtotal': False},
    'other_current_assets': {'section': 'Current Assets',       'order': 180, 'indent': 1, 'is_subtotal': False},
    'current_assets':       {'section': 'Current Assets',       'order': 190, 'indent': 0, 'is_subtotal': True},
    
    # === NON-CURRENT ASSETS (200-299) ===
    'ppe_gross':            {'section': 'Non-Current Assets',   'order': 200, 'indent': 1, 'is_subtotal': False},
    'accumulated_depreciation': {'section': 'Non-Current Assets', 'order': 205, 'indent': 2, 'is_subtotal': False},
    'ppe':                  {'section': 'Non-Current Assets',   'order': 210, 'indent': 1, 'is_subtotal': False},
    'goodwill':             {'section': 'Non-Current Assets',   'order': 220, 'indent': 1, 'is_subtotal': False},
    'intangibles':          {'section': 'Non-Current Assets',   'order': 230, 'indent': 1, 'is_subtotal': False},
    'lt_investments':       {'section': 'Non-Current Assets',   'order': 240, 'indent': 1, 'is_subtotal': False},
    'deferred_tax_assets':  {'section': 'Non-Current Assets',   'order': 250, 'indent': 1, 'is_subtotal': False},
    'rou_assets':           {'section': 'Non-Current Assets',   'order': 255, 'indent': 1, 'is_subtotal': False, 'label': 'Right-of-Use Assets'},
    'operating_lease_rou':  {'section': 'Non-Current Assets',   'order': 260, 'indent': 2, 'is_subtotal': False, 'label': 'Operating Lease ROU'},
    'finance_lease_rou':    {'section': 'Non-Current Assets',   'order': 265, 'indent': 2, 'is_subtotal': False, 'label': 'Finance Lease ROU'},
    'other_noncurrent_assets': {'section': 'Non-Current Assets', 'order': 280, 'indent': 1, 'is_subtotal': False},
    'total_assets':         {'section': 'Non-Current Assets',   'order': 290, 'indent': 0, 'is_subtotal': True},
    
    # === CURRENT LIABILITIES (300-399) ===
    'accounts_payable':     {'section': 'Current Liabilities',  'order': 300, 'indent': 1, 'is_subtotal': False},
    'accrued_liabilities':  {'section': 'Current Liabilities',  'order': 310, 'indent': 1, 'is_subtotal': False},
    'deferred_revenue':     {'section': 'Current Liabilities',  'order': 320, 'indent': 1, 'is_subtotal': False},
    'st_debt':              {'section': 'Current Liabilities',  'order': 330, 'indent': 1, 'is_subtotal': False},
    'current_portion_lt_debt': {'section': 'Current Liabilities', 'order': 335, 'indent': 2, 'is_subtotal': False},
    'income_tax_payable':   {'section': 'Current Liabilities',  'order': 340, 'indent': 1, 'is_subtotal': False},
    'operating_lease_liability_current': {'section': 'Current Liabilities', 'order': 350, 'indent': 1, 'is_subtotal': False},
    'other_current_liabilities': {'section': 'Current Liabilities', 'order': 380, 'indent': 1, 'is_subtotal': False},
    'current_liabilities':  {'section': 'Current Liabilities',  'order': 390, 'indent': 0, 'is_subtotal': True},
    
    # === NON-CURRENT LIABILITIES (400-499) ===
    'lt_debt':              {'section': 'Non-Current Liabilities', 'order': 400, 'indent': 1, 'is_subtotal': False},
    'lease_liabilities':    {'section': 'Non-Current Liabilities', 'order': 405, 'indent': 1, 'is_subtotal': False, 'label': 'Total Lease Liabilities'},
    'operating_lease_liability': {'section': 'Non-Current Liabilities', 'order': 410, 'indent': 2, 'is_subtotal': False},
    'finance_lease_liability': {'section': 'Non-Current Liabilities', 'order': 415, 'indent': 2, 'is_subtotal': False, 'label': 'Finance Lease Liability'},
    'lease_liabilities_noncurrent': {'section': 'Non-Current Liabilities', 'order': 416, 'indent': 2, 'is_subtotal': False, 'label': 'Lease Liabilities (Non-Current)'},
    'finance_lease_liability_noncurrent': {'section': 'Non-Current Liabilities', 'order': 417, 'indent': 2, 'is_subtotal': False, 'label': 'Finance Lease (Non-Current)'},
    'deferred_tax_liabilities': {'section': 'Non-Current Liabilities', 'order': 420, 'indent': 1, 'is_subtotal': False},
    'pension_liability':    {'section': 'Non-Current Liabilities', 'order': 430, 'indent': 1, 'is_subtotal': False},
    'other_noncurrent_liabilities': {'section': 'Non-Current Liabilities', 'order': 480, 'indent': 1, 'is_subtotal': False},
    'total_liabilities':    {'section': 'Non-Current Liabilities', 'order': 490, 'indent': 0, 'is_subtotal': True},
    # Legacy
    'lease_liability':      {'section': 'Non-Current Liabilities', 'order': 411, 'indent': 1, 'is_subtotal': False},
    
    # === EQUITY (500-599) ===
    'preferred_stock':      {'section': 'Equity',               'order': 500, 'indent': 1, 'is_subtotal': False},
    'common_stock':         {'section': 'Equity',               'order': 510, 'indent': 1, 'is_subtotal': False},
    'apic':                 {'section': 'Equity',               'order': 520, 'indent': 1, 'is_subtotal': False},
    'retained_earnings':    {'section': 'Equity',               'order': 530, 'indent': 1, 'is_subtotal': False},
    'treasury_stock':       {'section': 'Equity',               'order': 540, 'indent': 1, 'is_subtotal': False},
    'accumulated_oci':      {'section': 'Equity',               'order': 550, 'indent': 1, 'is_subtotal': False},
    'noncontrolling_interest': {'section': 'Equity',            'order': 560, 'indent': 1, 'is_subtotal': False},
    'total_equity':         {'section': 'Equity',               'order': 590, 'indent': 0, 'is_subtotal': True},
    
    # === KEY METRICS (600-699) ===
    'total_debt':           {'section': 'Key Metrics',          'order': 600, 'indent': 0, 'is_subtotal': True},
    'net_debt':             {'section': 'Key Metrics',          'order': 610, 'indent': 1, 'is_subtotal': False},
    'working_capital':      {'section': 'Key Metrics',          'order': 620, 'indent': 0, 'is_subtotal': False},
    'book_value_per_share': {'section': 'Key Metrics',          'order': 630, 'indent': 0, 'is_subtotal': False},
    'tangible_book_value':  {'section': 'Key Metrics',          'order': 640, 'indent': 0, 'is_subtotal': False},
    'tangible_book_value_per_share': {'section': 'Key Metrics', 'order': 641, 'indent': 1, 'is_subtotal': False},
}


# =============================================================================
# CASH FLOW STRUCTURE (Expandido)
# =============================================================================

CASH_FLOW_STRUCTURE = {
    # === OPERATING ACTIVITIES (100-199) ===
    'net_income':           {'section': 'Operating Activities', 'order': 100, 'indent': 0, 'is_subtotal': False, 'label': 'Net Income'},
    'depreciation_amortization': {'section': 'Operating Activities', 'order': 110, 'indent': 1, 'is_subtotal': False, 'label': 'Depreciation & Amortization'},
    'depreciation':         {'section': 'Operating Activities', 'order': 111, 'indent': 1, 'is_subtotal': False, 'label': 'Depreciation'},
    'amortization':         {'section': 'Operating Activities', 'order': 112, 'indent': 1, 'is_subtotal': False, 'label': 'Amortization'},
    'stock_compensation':   {'section': 'Operating Activities', 'order': 120, 'indent': 1, 'is_subtotal': False, 'label': 'Stock-Based Compensation'},
    'asset_writedown':      {'section': 'Operating Activities', 'order': 125, 'indent': 1, 'is_subtotal': False, 'label': 'Asset Writedown & Restructuring'},
    'gain_loss_equity_investments': {'section': 'Operating Activities', 'order': 130, 'indent': 1, 'is_subtotal': False, 'label': '(Income) Loss on Equity Investments'},
    'deferred_taxes':       {'section': 'Operating Activities', 'order': 135, 'indent': 1, 'is_subtotal': False, 'label': 'Deferred Income Taxes'},
    'change_receivables':   {'section': 'Operating Activities', 'order': 150, 'indent': 1, 'is_subtotal': False, 'label': 'Change in Receivables'},
    'change_inventory':     {'section': 'Operating Activities', 'order': 155, 'indent': 1, 'is_subtotal': False, 'label': 'Change in Inventories'},
    'change_payables':      {'section': 'Operating Activities', 'order': 160, 'indent': 1, 'is_subtotal': False, 'label': 'Change in Accounts Payable'},
    'other_operating_cf':   {'section': 'Operating Activities', 'order': 180, 'indent': 1, 'is_subtotal': False, 'label': 'Other Operating Activities'},
    'operating_cf':         {'section': 'Operating Activities', 'order': 190, 'indent': 0, 'is_subtotal': True, 'label': 'Cash from Operations'},
    'working_capital_change': {'section': 'Operating Activities', 'order': 195, 'indent': 1, 'is_subtotal': False, 'label': 'Memo: Change in Net Working Capital'},
    
    # === INVESTING ACTIVITIES (200-299) ===
    'capex':                {'section': 'Investing Activities', 'order': 200, 'indent': 1, 'is_subtotal': False, 'label': 'Capital Expenditures'},
    'acquisitions':         {'section': 'Investing Activities', 'order': 210, 'indent': 1, 'is_subtotal': False, 'label': 'Cash Acquisitions'},
    'purchase_investments': {'section': 'Investing Activities', 'order': 220, 'indent': 1, 'is_subtotal': False, 'label': 'Purchase of Investments'},
    'sale_investments':     {'section': 'Investing Activities', 'order': 225, 'indent': 1, 'is_subtotal': False, 'label': 'Sale of Investments'},
    'other_investing_cf':   {'section': 'Investing Activities', 'order': 280, 'indent': 1, 'is_subtotal': False, 'label': 'Other Investing Activities'},
    'investing_cf':         {'section': 'Investing Activities', 'order': 290, 'indent': 0, 'is_subtotal': True, 'label': 'Cash from Investing'},
    
    # === FINANCING ACTIVITIES (300-399) ===
    'debt_issued':          {'section': 'Financing Activities', 'order': 300, 'indent': 1, 'is_subtotal': False, 'label': 'Total Debt Issued'},
    'debt_repaid':          {'section': 'Financing Activities', 'order': 310, 'indent': 1, 'is_subtotal': False, 'label': 'Total Debt Repaid'},
    'stock_issued':         {'section': 'Financing Activities', 'order': 320, 'indent': 1, 'is_subtotal': False, 'label': 'Issuance of Common Stock'},
    'stock_repurchased':    {'section': 'Financing Activities', 'order': 330, 'indent': 1, 'is_subtotal': False, 'label': 'Repurchase of Common Stock'},
    'dividends_paid':       {'section': 'Financing Activities', 'order': 340, 'indent': 1, 'is_subtotal': False, 'label': 'Common Dividends Paid'},
    'special_dividend':     {'section': 'Financing Activities', 'order': 345, 'indent': 1, 'is_subtotal': False, 'label': 'Special Dividend Paid'},
    'operating_lease_payments': {'section': 'Financing Activities', 'order': 360, 'indent': 1, 'is_subtotal': False, 'label': 'Operating Lease Payments'},
    'finance_lease_payments': {'section': 'Financing Activities', 'order': 365, 'indent': 1, 'is_subtotal': False, 'label': 'Finance Lease Payments'},
    'payments_to_minority': {'section': 'Financing Activities', 'order': 370, 'indent': 1, 'is_subtotal': False, 'label': 'Payments to Minority Shareholders'},
    'other_financing_cf':   {'section': 'Financing Activities', 'order': 380, 'indent': 1, 'is_subtotal': False, 'label': 'Other Financing Activities'},
    'financing_cf':         {'section': 'Financing Activities', 'order': 390, 'indent': 0, 'is_subtotal': True, 'label': 'Cash from Financing'},
    
    # === NET CHANGE (400-449) ===
    'fx_effect':            {'section': 'Net Change', 'order': 400, 'indent': 1, 'is_subtotal': False, 'label': 'Foreign Exchange Rate Adjustments'},
    'net_change_cash':      {'section': 'Net Change', 'order': 410, 'indent': 0, 'is_subtotal': True, 'label': 'Net Change in Cash'},
    'cash_beginning':       {'section': 'Net Change', 'order': 420, 'indent': 1, 'is_subtotal': False, 'label': 'Cash & Equivalents, Beginning'},
    'cash_ending':          {'section': 'Net Change', 'order': 430, 'indent': 1, 'is_subtotal': False, 'label': 'Cash & Equivalents, End'},
    
    # === SUPPLEMENTAL (450-499) ===
    'interest_paid':        {'section': 'Supplemental', 'order': 450, 'indent': 1, 'is_subtotal': False, 'label': 'Cash Interest Paid'},
    'taxes_paid':           {'section': 'Supplemental', 'order': 455, 'indent': 1, 'is_subtotal': False, 'label': 'Cash Taxes Paid'},
    
    # === FREE CASH FLOW (500-599) ===
    'free_cash_flow':       {'section': 'Free Cash Flow', 'order': 500, 'indent': 0, 'is_subtotal': True, 'label': 'Free Cash Flow'},
    'fcf_yoy':              {'section': 'Free Cash Flow', 'order': 505, 'indent': 1, 'is_subtotal': False, 'label': '% Change YoY'},
    'fcf_margin':           {'section': 'Free Cash Flow', 'order': 510, 'indent': 1, 'is_subtotal': False, 'label': '% FCF Margin'},
    'fcf_per_share':        {'section': 'Free Cash Flow',       'order': 520, 'indent': 1, 'is_subtotal': False},
    'fcf_yoy':              {'section': 'Free Cash Flow',       'order': 530, 'indent': 1, 'is_subtotal': False},
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
        # === INTEREST INCOME (como TIKR) ===
        'interest_income':          {'section': 'Interest Income', 'order': 100, 'indent': 0, 'is_subtotal': False, 'label': 'Interest and Dividend Income'},
        'interest_and_fee_income':  {'section': 'Interest Income', 'order': 101, 'indent': 1, 'is_subtotal': False, 'label': 'Interest Income On Loans'},
        'interest_and_fee_income_loans_and_leases': {'section': 'Interest Income', 'order': 101, 'indent': 1, 'is_subtotal': False, 'label': 'Interest Income On Loans'},
        'interest_expense':         {'section': 'Interest Income', 'order': 110, 'indent': 0, 'is_subtotal': False, 'label': 'Interest Expense'},
        'net_interest_income':      {'section': 'Interest Income', 'order': 120, 'indent': 0, 'is_subtotal': True, 'label': 'Net Interest Income'},
        'net_interest_income_yoy':  {'section': 'Interest Income', 'order': 121, 'indent': 1, 'is_subtotal': False, 'label': '% Change YoY'},
        
        # === NON-INTEREST REVENUE ===
        'brokerage_revenue':        {'section': 'Revenue', 'order': 200, 'indent': 0, 'is_subtotal': False, 'label': 'Brokerage Commission'},
        'fees_and_commissions1':    {'section': 'Revenue', 'order': 201, 'indent': 0, 'is_subtotal': False, 'label': 'Commission Revenue'},
        'trading_revenue':          {'section': 'Revenue', 'order': 210, 'indent': 0, 'is_subtotal': False, 'label': 'Trading and Principal Transactions'},
        'principal_transactions_revenue': {'section': 'Revenue', 'order': 211, 'indent': 0, 'is_subtotal': False, 'label': 'Principal Transactions'},
        'asset_management_fee':     {'section': 'Revenue', 'order': 220, 'indent': 0, 'is_subtotal': False, 'label': 'Asset Management Fee'},
        'asset_management_fees':    {'section': 'Revenue', 'order': 221, 'indent': 0, 'is_subtotal': False, 'label': 'Asset Management Fees'},
        'service_revenue':          {'section': 'Revenue', 'order': 230, 'indent': 0, 'is_subtotal': False, 'label': 'Service Charges'},
        'feesand_commissions_depositor_accounts1': {'section': 'Revenue', 'order': 231, 'indent': 0, 'is_subtotal': False, 'label': 'Service Charges On Deposits'},
        'fees_and_commissions_credit_and_debit_cards1': {'section': 'Revenue', 'order': 232, 'indent': 0, 'is_subtotal': False, 'label': 'Credit Card Fee'},
        'lending_and_deposit_related_fees': {'section': 'Revenue', 'order': 233, 'indent': 0, 'is_subtotal': False, 'label': 'Lending & Deposit Fees'},
        'mortgage_fees_and_related_income': {'section': 'Revenue', 'order': 234, 'indent': 0, 'is_subtotal': False, 'label': 'Mortgage Banking Activities'},
        'underwriting_revenue':     {'section': 'Revenue', 'order': 240, 'indent': 0, 'is_subtotal': False, 'label': 'Underwriting Revenue'},
        'other_revenue':            {'section': 'Revenue', 'order': 250, 'indent': 0, 'is_subtotal': False, 'label': 'Other Revenues'},
        'noninterest_income_other': {'section': 'Revenue', 'order': 251, 'indent': 0, 'is_subtotal': False, 'label': 'Other Non-Interest Income'},
        'noninterest_income':       {'section': 'Revenue', 'order': 260, 'indent': 0, 'is_subtotal': True, 'label': 'Non-Interest Income Total'},
        'revenue_before_provision': {'section': 'Revenue', 'order': 270, 'indent': 0, 'is_subtotal': True, 'label': 'Revenues Before Provision For Loan Losses'},
        'revenues_net_of_interest_expense': {'section': 'Revenue', 'order': 271, 'indent': 1, 'is_subtotal': False, 'label': 'Revenues Net of Interest Expense'},
        
        # === PROVISIONS ===
        'provision_for_loan_losses':{'section': 'Provisions', 'order': 300, 'indent': 0, 'is_subtotal': False, 'label': 'Provision For Loan Losses'},
        'provision_bad_debts':      {'section': 'Provisions', 'order': 301, 'indent': 0, 'is_subtotal': False, 'label': 'Provision for Bad Debts'},
        'credit_loss_expense':      {'section': 'Provisions', 'order': 302, 'indent': 1, 'is_subtotal': False, 'label': 'Credit Loss Expense'},
        'revenue':                  {'section': 'Revenue', 'order': 280, 'indent': 0, 'is_subtotal': True, 'label': 'Total Revenues'},
        'revenue_yoy':              {'section': 'Revenue', 'order': 281, 'indent': 1, 'is_subtotal': False, 'label': '% Change YoY'},
        
        # === OPERATING EXPENSES ===
        'salaries_benefits':        {'section': 'Operating Expenses', 'order': 400, 'indent': 0, 'is_subtotal': False, 'label': 'Salaries And Other Employee Benefits'},
        'compensation_expense':     {'section': 'Operating Expenses', 'order': 401, 'indent': 0, 'is_subtotal': False, 'label': 'Compensation & Benefits'},
        'cost_of_services':         {'section': 'Operating Expenses', 'order': 410, 'indent': 0, 'is_subtotal': False, 'label': 'Cost of Services Provided'},
        'rd_expenses':              {'section': 'Operating Expenses', 'order': 415, 'indent': 0, 'is_subtotal': False, 'label': 'Technology & Development'},
        'occupancy_net':            {'section': 'Operating Expenses', 'order': 420, 'indent': 0, 'is_subtotal': False, 'label': 'Occupancy Expense'},
        'depreciation_amortization':{'section': 'Operating Expenses', 'order': 430, 'indent': 0, 'is_subtotal': False, 'label': 'Depreciation & Amortization'},
        'communications_and_information_technology': {'section': 'Operating Expenses', 'order': 431, 'indent': 0, 'is_subtotal': False, 'label': 'Communications & IT'},
        'professional_and_contract_services_expense': {'section': 'Operating Expenses', 'order': 432, 'indent': 0, 'is_subtotal': False, 'label': 'Professional Services'},
        'marketing_and_advertising_expense': {'section': 'Operating Expenses', 'order': 433, 'indent': 0, 'is_subtotal': False, 'label': 'Marketing & Advertising'},
        'sales_marketing':          {'section': 'Operating Expenses', 'order': 434, 'indent': 0, 'is_subtotal': False, 'label': 'Sales & Marketing'},
        'ga_expenses':              {'section': 'Operating Expenses', 'order': 435, 'indent': 0, 'is_subtotal': False, 'label': 'G&A Expenses'},
        'other_noninterest_expense':{'section': 'Operating Expenses', 'order': 440, 'indent': 0, 'is_subtotal': False, 'label': 'Other Non-Interest Expense'},
        'other_operating_expenses': {'section': 'Operating Expenses', 'order': 441, 'indent': 0, 'is_subtotal': False, 'label': 'Other Operating Expenses'},
        'federal_deposit_insurance_corporation_premium_expense': {'section': 'Operating Expenses', 'order': 445, 'indent': 0, 'is_subtotal': False, 'label': 'FDIC Premium Expense'},
        'noninterest_expense':      {'section': 'Operating Expenses', 'order': 450, 'indent': 0, 'is_subtotal': True, 'label': 'Non-Interest Expense'},
        'total_operating_expenses': {'section': 'Operating Expenses', 'order': 460, 'indent': 0, 'is_subtotal': True, 'label': 'Total Operating Expenses'},
        'stock_compensation':       {'section': 'Operating Expenses', 'order': 461, 'indent': 0, 'is_subtotal': False, 'label': 'Stock-Based Compensation'},
        
        # === OPERATING INCOME ===
        'operating_income':         {'section': 'Operating Income', 'order': 500, 'indent': 0, 'is_subtotal': True, 'label': 'Operating Income'},
        'operating_margin':         {'section': 'Operating Income', 'order': 501, 'indent': 1, 'is_subtotal': False, 'label': '% Operating Margins'},
        
        # === NON-OPERATING ===
        'other_nonoperating':       {'section': 'Non-Operating', 'order': 510, 'indent': 0, 'is_subtotal': False, 'label': 'Other Non Operating Income (Expenses)'},
        'impairment_charges':       {'section': 'Non-Operating', 'order': 511, 'indent': 0, 'is_subtotal': False, 'label': 'Impairment Charges'},
        
        # === EBT & UNUSUAL ITEMS ===
        'ebt_excl_unusual':         {'section': 'Earnings', 'order': 600, 'indent': 0, 'is_subtotal': True, 'label': 'EBT Excl. Unusual Items'},
        'merger_restructuring':     {'section': 'Earnings', 'order': 601, 'indent': 0, 'is_subtotal': False, 'label': 'Merger & Restructuring Charges'},
        'restructuring_charges':    {'section': 'Earnings', 'order': 602, 'indent': 1, 'is_subtotal': False, 'label': 'Restructuring Charges'},
        'business_combination_integration_related_costs': {'section': 'Earnings', 'order': 603, 'indent': 1, 'is_subtotal': False, 'label': 'Integration Costs'},
        'gain_loss_sale_investments':{'section': 'Earnings', 'order': 604, 'indent': 0, 'is_subtotal': False, 'label': 'Gain (Loss) on Sale of Investments'},
        'asset_writedown':          {'section': 'Earnings', 'order': 605, 'indent': 0, 'is_subtotal': False, 'label': 'Asset Writedown'},
        'legal_settlements':        {'section': 'Earnings', 'order': 606, 'indent': 0, 'is_subtotal': False, 'label': 'Legal Settlements'},
        'other_unusual_items':      {'section': 'Earnings', 'order': 607, 'indent': 0, 'is_subtotal': False, 'label': 'Other Unusual Items'},
        'income_before_tax':        {'section': 'Earnings', 'order': 610, 'indent': 0, 'is_subtotal': True, 'label': 'EBT Incl. Unusual Items'},
        'income_tax':               {'section': 'Earnings', 'order': 620, 'indent': 0, 'is_subtotal': False, 'label': 'Income Tax Expense'},
        'income_continuing_ops':    {'section': 'Earnings', 'order': 630, 'indent': 0, 'is_subtotal': True, 'label': 'Earnings From Continuing Operations'},
        'income_discontinued_ops':  {'section': 'Earnings', 'order': 631, 'indent': 0, 'is_subtotal': False, 'label': 'Earnings Of Discontinued Operations'},
        'net_income':               {'section': 'Earnings', 'order': 640, 'indent': 0, 'is_subtotal': True, 'label': 'Net Income to Company'},
        'minority_interest':        {'section': 'Earnings', 'order': 641, 'indent': 0, 'is_subtotal': False, 'label': 'Minority Interest'},
        'net_income_after_minority':{'section': 'Earnings', 'order': 642, 'indent': 0, 'is_subtotal': True, 'label': 'Net Income'},
        'preferred_dividends':      {'section': 'Earnings', 'order': 645, 'indent': 0, 'is_subtotal': False, 'label': 'Preferred Dividend and Other Adjustments'},
        'dividends_preferred_stock':{'section': 'Earnings', 'order': 646, 'indent': 1, 'is_subtotal': False, 'label': 'Preferred Dividends'},
        'net_income_to_common':     {'section': 'Earnings', 'order': 650, 'indent': 0, 'is_subtotal': True, 'label': 'Net Income to Common Incl Extra Items'},
        'net_margin':               {'section': 'Earnings', 'order': 651, 'indent': 1, 'is_subtotal': False, 'label': '% Net Income to Common Margins'},
        'net_income_yoy':           {'section': 'Earnings', 'order': 652, 'indent': 1, 'is_subtotal': False, 'label': '% Change YoY'},
        
        # === PER SHARE DATA ===
        'eps_basic':                {'section': 'Per Share Data', 'order': 700, 'indent': 0, 'is_subtotal': False, 'label': 'Basic EPS'},
        'eps_diluted':              {'section': 'Per Share Data', 'order': 710, 'indent': 0, 'is_subtotal': False, 'label': 'Diluted EPS Excl Extra Items'},
        'eps_yoy':                  {'section': 'Per Share Data', 'order': 711, 'indent': 1, 'is_subtotal': False, 'label': '% Change YoY'},
        'shares_diluted':           {'section': 'Per Share Data', 'order': 720, 'indent': 0, 'is_subtotal': False, 'label': 'Weighted Average Diluted Shares Outstanding'},
        'shares_basic':             {'section': 'Per Share Data', 'order': 730, 'indent': 0, 'is_subtotal': False, 'label': 'Weighted Average Basic Shares Outstanding'},
        'dividend_per_share':       {'section': 'Per Share Data', 'order': 740, 'indent': 0, 'is_subtotal': False, 'label': 'Dividends per share'},
        'special_dividend':         {'section': 'Per Share Data', 'order': 745, 'indent': 0, 'is_subtotal': False, 'label': 'Special Dividends Per Share'},
        'payout_ratio':             {'section': 'Per Share Data', 'order': 750, 'indent': 0, 'is_subtotal': False, 'label': 'Payout Ratio %'},
        'effective_tax_rate':       {'section': 'Per Share Data', 'order': 760, 'indent': 0, 'is_subtotal': False, 'label': 'Effective Tax Rate %'},
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
    'retail': {
        'membership_fees':        {'section': 'Revenue', 'order': 114, 'indent': 1, 'is_subtotal': False, 'label': 'Membership Fees'},
        'pre_opening_costs':      {'section': 'Operating Expenses', 'order': 335, 'indent': 1, 'is_subtotal': False, 'label': 'Pre-Opening Costs'},
        'store_closing_costs':    {'section': 'Operating Expenses', 'order': 336, 'indent': 1, 'is_subtotal': False, 'label': 'Store Closing Costs'},
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
        industry: 'insurance', 'banking', 'real_estate', 'retail', etc.
    
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
    'pre_opening_costs': 'Pre-Opening Costs',
    'equity_method_income': 'Income (Loss) on Equity Investments',
    'interest_and_other_income': 'Interest & Other Income',
    'ebt_excl_unusual': 'EBT Excl. Unusual Items',
    'net_income_to_common': 'Net Income to Common',
    'total_operating_expenses': 'Total Operating Expenses',
    'total_nonoperating': 'Total Non-Operating Income',
    'foreign_exchange_gain_loss': 'FX Gain (Loss)',
}
