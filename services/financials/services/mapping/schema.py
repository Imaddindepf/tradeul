"""
Universal Financial Schema - Taxonomía propia de Tradeul.

Este archivo define TODOS los campos canónicos que nuestro sistema reconoce.
Cada campo tiene:
- key: Identificador único (snake_case)
- label: Nombre para mostrar
- section: Sección del estado financiero
- order: Orden de presentación
- data_type: monetary, percent, perShare, shares, ratio
- statement: income, balance, cashflow
- is_subtotal: Si es un total/subtotal
- calculated: Si se calcula vs extrae directamente

Basado en: TIKR, Bloomberg, análisis de SEC dataset
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass


class DataType(str, Enum):
    MONETARY = "monetary"
    PERCENT = "percent"
    PER_SHARE = "perShare"
    SHARES = "shares"
    RATIO = "ratio"


class StatementType(str, Enum):
    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"


@dataclass
class CanonicalField:
    """Definición de un campo canónico."""
    key: str
    label: str
    section: str
    order: int
    data_type: DataType = DataType.MONETARY
    statement: StatementType = StatementType.INCOME
    indent: int = 0
    is_subtotal: bool = False
    calculated: bool = False
    importance: int = 100  # Para ordenar en caso de no tener estructura


# =============================================================================
# INCOME STATEMENT SCHEMA (50 campos)
# =============================================================================

INCOME_STATEMENT_SCHEMA: List[CanonicalField] = [
    # === REVENUE (100-199) ===
    CanonicalField("revenue", "Total Revenue", "Revenue", 100, is_subtotal=True, importance=10000),
    CanonicalField("revenue_yoy", "Revenue % YoY", "Revenue", 101, DataType.PERCENT, indent=1, calculated=True, importance=9900),
    CanonicalField("product_revenue", "Product Revenue", "Revenue", 110, indent=1, importance=9000),
    CanonicalField("service_revenue", "Service Revenue", "Revenue", 111, indent=1, importance=9000),
    CanonicalField("subscription_revenue", "Subscription Revenue", "Revenue", 112, indent=1, importance=8500),
    CanonicalField("membership_fees", "Membership Fees", "Revenue", 113, indent=1, importance=8500),
    
    # === FINANCIALS/BROKERAGE REVENUE (120-149) ===
    CanonicalField("interest_and_dividend_income", "Interest & Dividend Income", "Revenue", 120, indent=1, importance=9200),
    CanonicalField("net_interest_income", "Net Interest Income", "Revenue", 125, indent=1, importance=9100),
    CanonicalField("brokerage_revenue", "Brokerage Commission", "Revenue", 130, indent=1, importance=9000),
    CanonicalField("trading_revenue", "Trading Revenue", "Revenue", 131, indent=1, importance=8900),
    CanonicalField("advisory_fees", "Advisory Fees", "Revenue", 132, indent=1, importance=8800),
    CanonicalField("asset_management_fees", "Asset Management Fees", "Revenue", 133, indent=1, importance=8700),
    CanonicalField("underwriting_revenue", "Underwriting Revenue", "Revenue", 134, indent=1, importance=8600),
    CanonicalField("other_revenue", "Other Revenue", "Revenue", 140, indent=1, importance=8000),
    
    # === BANKING REVENUE (145-149) ===
    CanonicalField("provision_loan_losses", "Provision for Loan Losses", "Revenue", 145, indent=1, importance=9000),
    CanonicalField("noninterest_income", "Noninterest Income", "Revenue", 146, indent=1, importance=8900),
    CanonicalField("fee_income", "Fee Income", "Revenue", 147, indent=1, importance=8800),
    
    # === INSURANCE REVENUE (150-159) ===
    CanonicalField("premiums_earned", "Premiums Earned", "Revenue", 150, indent=1, importance=9200),
    CanonicalField("premiums_written", "Premiums Written", "Revenue", 151, indent=1, importance=9100),
    CanonicalField("policy_charges", "Policy Charges & Fees", "Revenue", 152, indent=1, importance=8800),
    CanonicalField("investment_income_insurance", "Investment Income", "Revenue", 153, indent=1, importance=8700),
    
    # === REITS REVENUE (160-169) ===
    CanonicalField("rental_revenue", "Rental Revenue", "Revenue", 160, indent=1, importance=9200),
    CanonicalField("property_revenue", "Property Revenue", "Revenue", 161, indent=1, importance=9100),
    CanonicalField("tenant_reimbursements", "Tenant Reimbursements", "Revenue", 162, indent=1, importance=8800),
    CanonicalField("same_store_revenue", "Same-Store Revenue", "Revenue", 163, indent=1, importance=8700),
    
    # === COST & GROSS PROFIT (200-299) ===
    CanonicalField("cost_of_revenue", "Cost of Revenue", "Cost & Gross Profit", 200, importance=9500),
    CanonicalField("cost_of_goods_sold", "Cost of Goods Sold", "Cost & Gross Profit", 201, indent=1, importance=9400),
    CanonicalField("cost_of_services", "Cost of Services", "Cost & Gross Profit", 202, indent=1, importance=9400),
    CanonicalField("gross_profit", "Gross Profit", "Cost & Gross Profit", 210, is_subtotal=True, calculated=True, importance=9300),
    CanonicalField("gross_profit_yoy", "Gross Profit % YoY", "Cost & Gross Profit", 211, DataType.PERCENT, indent=1, calculated=True, importance=9200),
    CanonicalField("gross_margin", "Gross Margin %", "Cost & Gross Profit", 212, DataType.PERCENT, indent=1, calculated=True, importance=9200),
    
    # === OPERATING EXPENSES (300-399) ===
    CanonicalField("rd_expenses", "R&D Expenses", "Operating Expenses", 300, indent=1, importance=8900),
    CanonicalField("sga_expenses", "SG&A Expenses", "Operating Expenses", 310, indent=1, importance=8900),
    CanonicalField("sales_marketing", "Sales & Marketing", "Operating Expenses", 320, indent=1, importance=8800),
    CanonicalField("ga_expenses", "G&A Expenses", "Operating Expenses", 325, indent=1, importance=8700),
    CanonicalField("fulfillment_expense", "Fulfillment Expense", "Operating Expenses", 330, indent=1, importance=8600),
    CanonicalField("pre_opening_costs", "Pre-Opening Costs", "Operating Expenses", 335, indent=1, importance=8500),
    CanonicalField("stock_compensation", "Stock-Based Compensation", "Operating Expenses", 340, indent=1, importance=8400),
    CanonicalField("depreciation_amortization", "Depreciation & Amortization", "Operating Expenses", 350, indent=1, importance=8300),
    CanonicalField("restructuring_charges", "Restructuring Charges", "Operating Expenses", 360, indent=1, importance=7500),
    CanonicalField("salaries_benefits", "Salaries & Employee Benefits", "Operating Expenses", 365, indent=1, importance=8200),
    CanonicalField("provision_bad_debts", "Provision for Bad Debts", "Operating Expenses", 370, indent=1, importance=7800),
    CanonicalField("legal_settlements", "Legal Settlements", "Operating Expenses", 375, indent=1, importance=7600),
    
    # === INSURANCE EXPENSES ===
    CanonicalField("policy_benefits", "Policy Benefits & Claims", "Operating Expenses", 376, indent=1, importance=8500),
    CanonicalField("policyholder_benefits", "Policyholder Benefits", "Operating Expenses", 377, indent=1, importance=8400),
    CanonicalField("claims_incurred", "Claims Incurred", "Operating Expenses", 378, indent=1, importance=8300),
    
    # === REITS EXPENSES ===
    CanonicalField("property_expenses", "Property Operating Expenses", "Operating Expenses", 379, indent=1, importance=8200),
    
    CanonicalField("other_operating_expenses", "Other Operating Expenses", "Operating Expenses", 380, indent=1, importance=7000),
    CanonicalField("total_lease_cost", "Total Lease Cost", "Operating Expenses", 381, indent=1, importance=6900),
    CanonicalField("operating_lease_cost", "Operating Lease Cost", "Operating Expenses", 382, indent=2, importance=6850),
    CanonicalField("finance_lease_amortization", "Finance Lease Amortization", "Operating Expenses", 383, indent=2, importance=6800),
    CanonicalField("finance_lease_interest", "Finance Lease Interest", "Operating Expenses", 384, indent=2, importance=6750),
    CanonicalField("variable_lease_cost", "Variable Lease Cost", "Operating Expenses", 385, indent=2, importance=6700),
    CanonicalField("short_term_lease_cost", "Short-term Lease Cost", "Operating Expenses", 386, indent=2, importance=6650),
    CanonicalField("total_operating_expenses", "Total Operating Expenses", "Operating Expenses", 390, is_subtotal=True, calculated=True, importance=8000),
    
    # === OPERATING INCOME (400-449) ===
    CanonicalField("operating_income", "Operating Income", "Operating Income", 400, is_subtotal=True, importance=8000),
    CanonicalField("operating_income_yoy", "Operating Income % YoY", "Operating Income", 401, DataType.PERCENT, indent=1, calculated=True, importance=7900),
    CanonicalField("operating_margin", "Operating Margin %", "Operating Income", 402, DataType.PERCENT, indent=1, calculated=True, importance=7900),
    
    # === EBITDA (450-499) ===
    CanonicalField("ebitda", "EBITDA", "EBITDA", 450, is_subtotal=True, calculated=True, importance=7800),
    CanonicalField("ebitda_yoy", "EBITDA % YoY", "EBITDA", 451, DataType.PERCENT, indent=1, calculated=True, importance=7700),
    CanonicalField("ebitda_margin", "EBITDA Margin %", "EBITDA", 452, DataType.PERCENT, indent=1, calculated=True, importance=7700),
    CanonicalField("ebitdar", "EBITDAR", "EBITDA", 460, is_subtotal=True, calculated=True, importance=7600),
    
    # === NON-OPERATING (500-599) ===
    CanonicalField("interest_expense", "Interest Expense", "Non-Operating", 500, indent=1, importance=7500),
    CanonicalField("interest_income", "Interest Income", "Non-Operating", 510, indent=1, importance=7400),
    CanonicalField("interest_and_other_income", "Interest & Other Income", "Non-Operating", 515, indent=1, importance=7350),
    CanonicalField("investment_income", "Investment Income", "Non-Operating", 520, indent=1, importance=7300),
    CanonicalField("equity_method_income", "Income from Equity Investments", "Non-Operating", 525, indent=1, importance=7200),
    CanonicalField("foreign_exchange_gain_loss", "FX Gain (Loss)", "Non-Operating", 530, indent=1, importance=7100),
    CanonicalField("gain_loss_securities", "Gain (Loss) on Securities", "Non-Operating", 540, indent=1, importance=7000),
    CanonicalField("gain_loss_sale_assets", "Gain (Loss) on Sale of Assets", "Non-Operating", 545, indent=1, importance=6900),
    CanonicalField("impairment_charges", "Impairment Charges", "Non-Operating", 550, indent=1, importance=6800),
    CanonicalField("crypto_gains_nonoperating", "Crypto Asset Gains (Losses)", "Non-Operating", 560, indent=1, importance=6700),
    CanonicalField("interest_investment_income", "Interest And Investment Income", "Non-Operating", 565, indent=1, importance=7400),
    CanonicalField("other_nonoperating", "Other Non-Operating", "Non-Operating", 580, indent=1, importance=6500),
    CanonicalField("total_nonoperating", "Total Non-Operating Income", "Non-Operating", 590, is_subtotal=True, calculated=True, importance=6400),
    
    # === EARNINGS BEFORE TAX (600-649) ===
    CanonicalField("ebt_excl_unusual", "EBT Excl. Unusual Items", "Earnings", 600, is_subtotal=True, calculated=True, importance=6300),
    # Unusual Items breakdown (TIKR style)
    CanonicalField("merger_restructuring", "Merger & Restructuring Charges", "Earnings", 601, indent=1, importance=6250),
    CanonicalField("gain_loss_investments", "Gain (Loss) On Sale Of Investments", "Earnings", 602, indent=1, importance=6240),
    CanonicalField("asset_writedown_unusual", "Asset Writedown", "Earnings", 603, indent=1, importance=6230),
    CanonicalField("other_unusual_items", "Other Unusual Items", "Earnings", 604, indent=1, importance=6220),
    CanonicalField("unusual_items", "Unusual Items", "Earnings", 605, indent=1, importance=6200),
    CanonicalField("income_before_tax", "EBT Incl. Unusual Items", "Earnings", 610, is_subtotal=True, importance=6500),
    
    # === TAX & NET INCOME (650-699) ===
    CanonicalField("income_tax", "Income Tax Expense", "Earnings", 650, indent=1, importance=6000),
    CanonicalField("effective_tax_rate", "Effective Tax Rate %", "Earnings", 651, DataType.PERCENT, indent=2, calculated=True, importance=5900),
    CanonicalField("income_continuing_ops", "Income from Continuing Ops", "Earnings", 660, is_subtotal=True, importance=5800),
    CanonicalField("income_discontinued_ops", "Income from Discontinued Ops", "Earnings", 665, indent=1, importance=5500),
    CanonicalField("minority_interest", "Minority Interest", "Earnings", 670, indent=1, importance=5400),
    CanonicalField("net_income", "Net Income to Company", "Earnings", 680, is_subtotal=True, importance=5500),
    CanonicalField("preferred_dividends", "Preferred Dividend and Other Adjustments", "Earnings", 682, indent=1, importance=5480),
    CanonicalField("net_income_to_common", "Net Income to Common Incl Extra Items", "Earnings", 685, is_subtotal=True, importance=5450),
    CanonicalField("net_margin", "% Net Income Margins", "Earnings", 690, DataType.PERCENT, indent=1, calculated=True, importance=5400),
    CanonicalField("net_income_to_common_excl", "Net Income to Common Excl. Extra Items", "Earnings", 692, is_subtotal=True, calculated=True, importance=5380),
    CanonicalField("net_income_yoy", "Net Income % YoY", "Earnings", 693, DataType.PERCENT, indent=1, calculated=True, importance=5350),
    
    # === PER SHARE DATA (700-799) ===
    CanonicalField("eps_basic", "EPS Basic", "Per Share Data", 700, DataType.PER_SHARE, importance=5000),
    CanonicalField("eps_diluted", "EPS Diluted", "Per Share Data", 710, DataType.PER_SHARE, importance=4900),
    CanonicalField("eps_yoy", "EPS % YoY", "Per Share Data", 711, DataType.PERCENT, indent=1, calculated=True, importance=4850),
    CanonicalField("shares_basic", "Shares Outstanding Basic", "Per Share Data", 720, DataType.SHARES, importance=4800),
    CanonicalField("shares_diluted", "Shares Outstanding Diluted", "Per Share Data", 730, DataType.SHARES, importance=4700),
    CanonicalField("dividend_per_share", "Dividend per Share", "Per Share Data", 740, DataType.PER_SHARE, importance=4600),
    CanonicalField("special_dividend", "Special Dividend per Share", "Per Share Data", 745, DataType.PER_SHARE, importance=4550),
    CanonicalField("payout_ratio", "Dividend Payout Ratio %", "Per Share Data", 750, DataType.PERCENT, indent=1, calculated=True, importance=4500),
]


# =============================================================================
# BALANCE SHEET SCHEMA (60 campos)
# =============================================================================

BALANCE_SHEET_SCHEMA: List[CanonicalField] = [
    # === CURRENT ASSETS (100-199) ===
    CanonicalField("cash", "Cash & Equivalents", "Current Assets", 100, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9500),
    CanonicalField("restricted_cash", "Restricted Cash", "Current Assets", 105, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9400),
    CanonicalField("st_investments", "Short-term Investments", "Current Assets", 110, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9300),
    
    # === FINANCIALS/BROKERAGE ASSETS (111-119) ===
    CanonicalField("securities_segregated", "Cash & Securities Segregated", "Current Assets", 111, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9250),
    CanonicalField("securities_owned", "Securities Owned", "Current Assets", 112, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9200),
    CanonicalField("securities_borrowed", "Securities Borrowed", "Current Assets", 113, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9150),
    CanonicalField("broker_receivables", "Receivables from Brokers/Dealers", "Current Assets", 114, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9100),
    CanonicalField("clearing_deposits", "Deposits with Clearing Organizations", "Current Assets", 115, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9050),
    CanonicalField("securities_loaned", "Securities Loaned", "Current Assets", 116, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9000),
    
    # === BANKING ASSETS ===
    CanonicalField("loans_net", "Loans, Net", "Current Assets", 117, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9300),
    CanonicalField("loans_held_for_sale", "Loans Held for Sale", "Current Assets", 118, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9100),
    CanonicalField("allowance_loan_losses", "Allowance for Loan Losses", "Current Assets", 119, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=9000),
    
    CanonicalField("receivables", "Accounts Receivable", "Current Assets", 120, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9200),
    CanonicalField("inventory", "Inventory", "Current Assets", 130, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9100),
    CanonicalField("prepaid", "Prepaid Expenses", "Current Assets", 140, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9000),
    CanonicalField("other_current_assets", "Other Current Assets", "Current Assets", 180, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8500),
    CanonicalField("current_assets", "Total Current Assets", "Current Assets", 190, DataType.MONETARY, StatementType.BALANCE, is_subtotal=True, importance=9500),
    
    # === NON-CURRENT ASSETS (200-299) ===
    CanonicalField("ppe_gross", "PP&E Gross", "Non-Current Assets", 200, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8500),
    CanonicalField("accumulated_depreciation", "Accumulated Depreciation", "Non-Current Assets", 205, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=8400),
    CanonicalField("ppe", "PP&E Net", "Non-Current Assets", 210, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8500),
    CanonicalField("goodwill", "Goodwill", "Non-Current Assets", 220, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8400),
    CanonicalField("intangibles", "Intangible Assets", "Non-Current Assets", 230, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8300),
    CanonicalField("lt_investments", "Long-term Investments", "Non-Current Assets", 240, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8200),
    CanonicalField("deferred_tax_assets", "Deferred Tax Assets", "Non-Current Assets", 250, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8000),
    CanonicalField("rou_assets", "Right-of-Use Assets", "Non-Current Assets", 255, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7950),
    CanonicalField("operating_lease_rou", "Operating Lease ROU Asset", "Non-Current Assets", 260, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=7900),
    CanonicalField("finance_lease_rou", "Finance Lease ROU Asset", "Non-Current Assets", 265, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=7850),
    CanonicalField("deferred_finance_costs", "Deferred Finance Costs", "Non-Current Assets", 270, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7800),
    CanonicalField("other_noncurrent_assets", "Other Non-Current Assets", "Non-Current Assets", 280, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7500),
    CanonicalField("total_assets", "Total Assets", "Non-Current Assets", 290, DataType.MONETARY, StatementType.BALANCE, is_subtotal=True, importance=10000),
    
    # === CURRENT LIABILITIES (300-399) ===
    CanonicalField("accounts_payable", "Accounts Payable", "Current Liabilities", 300, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7500),
    CanonicalField("accrued_liabilities", "Accrued Liabilities", "Current Liabilities", 310, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7400),
    CanonicalField("deferred_revenue", "Deferred Revenue", "Current Liabilities", 320, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7300),
    CanonicalField("st_debt", "Short-term Debt", "Current Liabilities", 330, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7200),
    CanonicalField("current_portion_lt_debt", "Current Portion of LT Debt", "Current Liabilities", 335, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=7150),
    CanonicalField("income_tax_payable", "Income Taxes Payable", "Current Liabilities", 340, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7100),
    CanonicalField("operating_lease_liability_current", "Operating Lease Liability (Current)", "Current Liabilities", 350, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7000),
    CanonicalField("broker_payables", "Payables to Brokers/Dealers", "Current Liabilities", 375, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6900),
    
    # === BANKING LIABILITIES ===
    CanonicalField("deposits", "Total Deposits", "Current Liabilities", 376, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9200),
    CanonicalField("deposits_interest_bearing", "Interest-Bearing Deposits", "Current Liabilities", 377, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=9100),
    CanonicalField("deposits_noninterest", "Noninterest-Bearing Deposits", "Current Liabilities", 378, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=9000),
    
    # === INSURANCE LIABILITIES ===
    CanonicalField("policy_liabilities", "Policy Liabilities", "Current Liabilities", 379, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=9000),
    CanonicalField("unearned_premiums", "Unearned Premiums", "Current Liabilities", 380, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8900),
    CanonicalField("claims_reserves", "Claims & Loss Reserves", "Current Liabilities", 381, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=8800),
    
    CanonicalField("other_current_liabilities", "Other Current Liabilities", "Current Liabilities", 385, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6800),
    CanonicalField("current_liabilities", "Total Current Liabilities", "Current Liabilities", 390, DataType.MONETARY, StatementType.BALANCE, is_subtotal=True, importance=7600),
    
    # === NON-CURRENT LIABILITIES (400-499) ===
    CanonicalField("lt_debt", "Long-term Debt", "Non-Current Liabilities", 400, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=7000),
    CanonicalField("lease_liabilities", "Total Lease Liabilities", "Non-Current Liabilities", 405, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6950),
    CanonicalField("operating_lease_liability", "Operating Lease Liability", "Non-Current Liabilities", 410, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=6900),
    CanonicalField("finance_lease_liability", "Finance Lease Liability", "Non-Current Liabilities", 415, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=6850),
    CanonicalField("lease_liabilities_current", "Lease Liabilities (Current)", "Current Liabilities", 351, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=6950),
    CanonicalField("lease_liabilities_noncurrent", "Lease Liabilities (Non-Current)", "Non-Current Liabilities", 416, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=6840),
    CanonicalField("finance_lease_liability_current", "Finance Lease (Current)", "Current Liabilities", 352, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=6930),
    CanonicalField("finance_lease_liability_noncurrent", "Finance Lease (Non-Current)", "Non-Current Liabilities", 417, DataType.MONETARY, StatementType.BALANCE, indent=2, importance=6830),
    CanonicalField("deferred_tax_liabilities", "Deferred Tax Liabilities", "Non-Current Liabilities", 420, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6800),
    CanonicalField("pension_liability", "Pension & Postretirement", "Non-Current Liabilities", 430, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6700),
    CanonicalField("other_noncurrent_liabilities", "Other Non-Current Liabilities", "Non-Current Liabilities", 480, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6500),
    CanonicalField("total_liabilities", "Total Liabilities", "Non-Current Liabilities", 490, DataType.MONETARY, StatementType.BALANCE, is_subtotal=True, importance=7700),
    
    # === EQUITY (500-599) ===
    CanonicalField("preferred_stock", "Preferred Stock", "Equity", 500, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6400),
    CanonicalField("common_stock", "Common Stock", "Equity", 510, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6300),
    CanonicalField("apic", "Additional Paid-in Capital", "Equity", 520, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6200),
    CanonicalField("retained_earnings", "Retained Earnings", "Equity", 530, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6500),
    CanonicalField("treasury_stock", "Treasury Stock", "Equity", 540, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6100),
    CanonicalField("accumulated_oci", "Accumulated OCI", "Equity", 550, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=6000),
    CanonicalField("noncontrolling_interest", "Noncontrolling Interest", "Equity", 560, DataType.MONETARY, StatementType.BALANCE, indent=1, importance=5900),
    CanonicalField("total_equity", "Total Equity", "Equity", 590, DataType.MONETARY, StatementType.BALANCE, is_subtotal=True, importance=6600),
    
    # === KEY METRICS (600-699) ===
    CanonicalField("total_debt", "Total Debt", "Key Metrics", 600, DataType.MONETARY, StatementType.BALANCE, is_subtotal=True, calculated=True, importance=3500),
    CanonicalField("net_debt", "Net Debt", "Key Metrics", 610, DataType.MONETARY, StatementType.BALANCE, indent=1, calculated=True, importance=3400),
    CanonicalField("working_capital", "Working Capital", "Key Metrics", 620, DataType.MONETARY, StatementType.BALANCE, calculated=True, importance=3300),
    CanonicalField("book_value_per_share", "Book Value per Share", "Key Metrics", 630, DataType.PER_SHARE, StatementType.BALANCE, calculated=True, importance=3200),
    CanonicalField("tangible_book_value", "Tangible Book Value", "Key Metrics", 640, DataType.MONETARY, StatementType.BALANCE, calculated=True, importance=3100),
    CanonicalField("tangible_book_value_per_share", "Tangible BV per Share", "Key Metrics", 641, DataType.PER_SHARE, StatementType.BALANCE, indent=1, calculated=True, importance=3000),
]


# =============================================================================
# CASH FLOW SCHEMA (40 campos)
# =============================================================================

CASH_FLOW_SCHEMA: List[CanonicalField] = [
    # === OPERATING ACTIVITIES (100-199) ===
    CanonicalField("net_income", "Net Income", "Operating Activities", 100, DataType.MONETARY, StatementType.CASHFLOW, indent=0, importance=9500),
    CanonicalField("depreciation_amortization", "Depreciation & Amortization", "Operating Activities", 110, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8500),
    CanonicalField("stock_compensation", "Stock-Based Compensation", "Operating Activities", 120, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8400),
    CanonicalField("asset_writedown", "Asset Writedown & Restructuring", "Operating Activities", 125, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8300),
    CanonicalField("gain_loss_equity_investments", "(Income) Loss on Equity Investments", "Operating Activities", 130, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8200),
    CanonicalField("deferred_taxes", "Deferred Income Taxes", "Operating Activities", 135, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8100),
    CanonicalField("change_receivables", "Change in Receivables", "Operating Activities", 150, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7500),
    CanonicalField("change_inventory", "Change in Inventories", "Operating Activities", 155, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7400),
    CanonicalField("change_payables", "Change in Accounts Payable", "Operating Activities", 160, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7300),
    CanonicalField("other_operating_cf", "Other Operating Activities", "Operating Activities", 180, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=6500),
    CanonicalField("operating_cf", "Cash from Operations", "Operating Activities", 190, DataType.MONETARY, StatementType.CASHFLOW, is_subtotal=True, importance=10000),
    CanonicalField("working_capital_change", "Memo: Change in Net Working Capital", "Operating Activities", 195, DataType.MONETARY, StatementType.CASHFLOW, indent=1, calculated=True, importance=6000),
    
    # === INVESTING ACTIVITIES (200-299) ===
    CanonicalField("capex", "Capital Expenditures", "Investing Activities", 200, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=9000),
    CanonicalField("acquisitions", "Cash Acquisitions", "Investing Activities", 210, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8500),
    CanonicalField("purchase_investments", "Purchase of Investments", "Investing Activities", 220, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7500),
    CanonicalField("sale_investments", "Sale of Investments", "Investing Activities", 225, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7400),
    CanonicalField("other_investing_cf", "Other Investing Activities", "Investing Activities", 280, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=6000),
    CanonicalField("investing_cf", "Cash from Investing", "Investing Activities", 290, DataType.MONETARY, StatementType.CASHFLOW, is_subtotal=True, importance=9500),
    
    # === FINANCING ACTIVITIES (300-399) ===
    CanonicalField("debt_issued", "Total Debt Issued", "Financing Activities", 300, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8200),
    CanonicalField("debt_repaid", "Total Debt Repaid", "Financing Activities", 310, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8100),
    CanonicalField("stock_issued", "Issuance of Common Stock", "Financing Activities", 320, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7500),
    CanonicalField("stock_repurchased", "Repurchase of Common Stock", "Financing Activities", 330, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8000),
    CanonicalField("dividends_paid", "Common Dividends Paid", "Financing Activities", 340, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=8500),
    CanonicalField("special_dividend", "Special Dividend Paid", "Financing Activities", 345, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7800),
    CanonicalField("operating_lease_payments", "Operating Lease Payments", "Financing Activities", 360, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=7000),
    CanonicalField("finance_lease_payments", "Finance Lease Payments", "Financing Activities", 365, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=6900),
    CanonicalField("payments_to_minority", "Payments to Minority Shareholders", "Financing Activities", 370, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=6500),
    CanonicalField("other_financing_cf", "Other Financing Activities", "Financing Activities", 380, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=6000),
    CanonicalField("financing_cf", "Cash from Financing", "Financing Activities", 390, DataType.MONETARY, StatementType.CASHFLOW, is_subtotal=True, importance=9000),
    
    # === NET CHANGE (400-449) ===
    CanonicalField("fx_effect", "Foreign Exchange Rate Adjustments", "Net Change", 400, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=5000),
    CanonicalField("net_change_cash", "Net Change in Cash", "Net Change", 410, DataType.MONETARY, StatementType.CASHFLOW, is_subtotal=True, importance=8000),
    CanonicalField("cash_beginning", "Cash & Equivalents, Beginning", "Net Change", 420, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=4500),
    CanonicalField("cash_ending", "Cash & Equivalents, End", "Net Change", 430, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=4600),
    
    # === SUPPLEMENTAL DATA (450-499) ===
    CanonicalField("interest_paid", "Cash Interest Paid", "Supplemental", 450, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=4000),
    CanonicalField("taxes_paid", "Cash Taxes Paid", "Supplemental", 455, DataType.MONETARY, StatementType.CASHFLOW, indent=1, importance=4100),
    
    # === FREE CASH FLOW (500-599) ===
    CanonicalField("free_cash_flow", "Free Cash Flow", "Free Cash Flow", 500, DataType.MONETARY, StatementType.CASHFLOW, is_subtotal=True, calculated=True, importance=9800),
    CanonicalField("fcf_yoy", "% Change YoY", "Free Cash Flow", 505, DataType.PERCENT, StatementType.CASHFLOW, indent=1, calculated=True, importance=9700),
    CanonicalField("fcf_margin", "% FCF Margin", "Free Cash Flow", 510, DataType.PERCENT, StatementType.CASHFLOW, indent=1, calculated=True, importance=9600),
    CanonicalField("fcf_per_share", "Cash Flow per Share", "Free Cash Flow", 520, DataType.PER_SHARE, StatementType.CASHFLOW, indent=1, calculated=True, importance=9500),
]


# =============================================================================
# HELPERS
# =============================================================================

def get_all_canonical_fields() -> Dict[str, CanonicalField]:
    """Obtener diccionario de todos los campos canónicos."""
    all_fields = {}
    for field in INCOME_STATEMENT_SCHEMA:
        all_fields[field.key] = field
    for field in BALANCE_SHEET_SCHEMA:
        all_fields[field.key] = field
    for field in CASH_FLOW_SCHEMA:
        all_fields[field.key] = field
    return all_fields


def get_canonical_keys() -> List[str]:
    """Obtener lista de todas las keys canónicas."""
    return list(get_all_canonical_fields().keys())


# Diccionario global para lookup rápido
CANONICAL_FIELDS = get_all_canonical_fields()


# =============================================================================
# XBRL → CANONICAL MAPPINGS (Los más importantes)
# =============================================================================
# Estos son los mapeos directos más comunes.
# El sistema de mapping engine expandirá esto dinámicamente.

XBRL_TO_CANONICAL: Dict[str, str] = {
    # === INCOME STATEMENT ===
    # Revenue
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    "SalesRevenueNet": "revenue",
    "NetSales": "revenue",
    
    # === FINANCIALS/BROKERAGE REVENUE ===
    "InterestAndDividendIncomeOperating": "interest_and_dividend_income",
    "InterestAndDividendIncome": "interest_and_dividend_income",
    "InterestIncomeExpenseNet": "net_interest_income",
    "InterestIncomeExpenseAfterProvisionForLoanLoss": "net_interest_income",
    "NetInterestIncome": "net_interest_income",
    "NetInterestIncomeAfterProvisionForCreditLoss": "net_interest_income",
    "BrokerageCommissionsRevenue": "brokerage_revenue",
    "CommissionRevenue": "brokerage_revenue",
    "CommissionsAndFees": "brokerage_revenue",
    "FloorBrokerageExchangeAndClearanceFees": "brokerage_revenue",
    "TradingRevenue": "trading_revenue",
    "TradingGainsLosses": "trading_revenue",
    "GainLossOnSaleOfSecuritiesNet": "trading_revenue",
    "AdvisoryFeesRevenue": "advisory_fees",
    "InvestmentAdvisoryManagementAndAdministrativeFees": "advisory_fees",
    "AssetManagementFees": "asset_management_fees",
    "InvestmentBankingRevenue": "underwriting_revenue",
    "UnderwritingIncomeLoss": "underwriting_revenue",
    "OtherOperatingIncomeExpenseNet": "other_revenue",
    "OtherRevenues": "other_revenue",
    
    # === BANKING ===
    "ProvisionForLoanLeaseAndOtherLosses": "provision_loan_losses",
    "ProvisionForLoanAndLeaseLosses": "provision_loan_losses",
    "ProvisionForCreditLosses": "provision_loan_losses",
    "NoninterestIncome": "noninterest_income",
    "FeesAndCommissions": "fee_income",
    "ServiceChargesOnDepositAccounts": "fee_income",
    "LoansAndLeasesReceivableNetReportedAmount": "loans_net",
    "LoansReceivableHeldForSaleNet": "loans_held_for_sale",
    "AllowanceForLoanAndLeaseLossesRealEstate": "allowance_loan_losses",
    "FinancingReceivableAllowanceForCreditLosses": "allowance_loan_losses",
    "Deposits": "deposits",
    "InterestBearingDepositsInDomesticOffices": "deposits_interest_bearing",
    "NoninterestBearingDepositsDomestic": "deposits_noninterest",
    
    # === INSURANCE ===
    "PremiumsEarnedNet": "premiums_earned",
    "PremiumsEarned": "premiums_earned",
    "PremiumsWrittenNet": "premiums_written",
    "GrossPremiumsWritten": "premiums_written",
    "PolicyChargesAndFeeIncome": "policy_charges",
    "NetInvestmentIncome": "investment_income_insurance",
    "PolicyholderBenefitsAndClaimsIncurredNet": "policy_benefits",
    "PolicyholderBenefits": "policyholder_benefits",
    "BenefitsLossesAndExpenses": "policy_benefits",
    "IncurredClaimsPropertyCasualtyAndLiability": "claims_incurred",
    "LiabilityForFuturePolicyBenefits": "policy_liabilities",
    "UnearnedPremiums": "unearned_premiums",
    "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpense": "claims_reserves",
    
    # === REITS ===
    "OperatingLeaseLeaseIncome": "rental_revenue",
    "OperatingLeasesIncomeStatementLeaseRevenue": "rental_revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTaxRealEstate": "property_revenue",
    "RealEstateRevenueNet": "property_revenue",
    "TenantReimbursements": "tenant_reimbursements",
    "RealEstateAndAccumulatedDepreciationCarryingAmountOfLandAndBuildingsAndImprovementsNetSameStore": "same_store_revenue",
    "CostOfRealEstateRevenue": "property_expenses",
    "DirectCostsOfLeasedAndRentedPropertyOrEquipment": "property_expenses",
    
    # Cost of Revenue
    "CostOfGoodsAndServicesSold": "cost_of_revenue",
    "CostOfGoodsSold": "cost_of_revenue",  # Consolidar con cost_of_revenue (como TIKR)
    "CostOfRevenue": "cost_of_revenue",
    "CostOfServices": "cost_of_services",
    "InformationTechnologyAndDataProcessing": "cost_of_revenue",  # Tech companies use IT costs as COGS
    
    # Operating Expenses
    "ResearchAndDevelopmentExpense": "rd_expenses",
    "TechnologyAndDevelopmentExpense": "rd_expenses",  # HOOD usa este
    "TechnologyAndContentExpense": "rd_expenses",  # Amazon usa este
    "TechnologyAndInfrastructureExpense": "rd_expenses",  # Amazon también usa este
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost": "rd_expenses",
    "OtherCostAndExpenseOperating": "other_operating_expenses",
    "MarketingExpense": "sales_marketing",
    "SellingGeneralAndAdministrativeExpense": "sga_expenses",
    "SellingAndMarketingExpense": "sales_marketing",
    "GeneralAndAdministrativeExpense": "ga_expenses",
    "FulfillmentExpense": "fulfillment_expense",
    "PreOpeningCosts": "pre_opening_costs",
    "ShareBasedCompensation": "stock_compensation",
    "AllocatedShareBasedCompensationExpense": "stock_compensation",  # Income Statement allocation
    "StockBasedCompensationExpense": "stock_compensation",
    "DepreciationAndAmortization": "depreciation_amortization",
    "DepreciationDepletionAndAmortization": "depreciation_amortization",
    "RestructuringCharges": "restructuring_charges",
    "RestructuringCosts": "restructuring_charges",
    "OperatingLeaseExpense": "rent_expense",
    "LeaseExpense": "rent_expense",
    "RentExpense": "rent_expense",
    "LaborAndRelatedExpense": "salaries_benefits",
    "SalariesAndWages": "salaries_benefits",
    "SalariesWagesAndOfficersCompensation": "salaries_benefits",
    "EmployeeBenefitsAndShareBasedCompensation": "salaries_benefits",
    "ProvisionForDoubtfulAccounts": "provision_bad_debts",
    "ProvisionForLoanLeaseAndOtherLosses": "provision_bad_debts",
    "ProvisionForCreditLosses": "provision_bad_debts",
    "AllowanceForDoubtfulAccountsReceivableWriteOffs": "provision_bad_debts",
    "LegalSettlement": "legal_settlements",
    "LegalSettlements": "legal_settlements",
    "LitigationSettlementExpense": "legal_settlements",
    
    # Unusual Items (TIKR style)
    "BusinessCombinationIntegrationRelatedCosts": "merger_restructuring",
    "BusinessCombinationAcquisitionRelatedCosts": "merger_restructuring",
    "MergerRelatedCosts": "merger_restructuring",
    "GainLossOnSaleOfInvestments": "gain_loss_investments",
    "GainLossOnInvestments": "gain_loss_investments",
    "RealizedInvestmentGainsLosses": "gain_loss_investments",
    "DebtSecuritiesAvailableForSaleRealizedGainLoss": "gain_loss_investments",
    "AssetImpairmentCharges": "asset_writedown_unusual",
    "GoodwillImpairmentLoss": "asset_writedown_unusual",
    "ImpairmentOfLongLivedAssetsHeldForUse": "asset_writedown_unusual",
    "OtherNonrecurringIncomeExpense": "other_unusual_items",
    "UnusualOrInfrequentItemNetOfTax": "other_unusual_items",
    
    # Preferred Dividends
    "PreferredStockDividendsAndOtherAdjustments": "preferred_dividends",
    "PreferredStockDividends": "preferred_dividends",
    "DividendsPreferredStock": "preferred_dividends",
    
    "OperatingExpenses": "total_operating_expenses",
    "CostsAndExpenses": "total_operating_expenses",
    
    # Operating Income
    "OperatingIncomeLoss": "operating_income",
    "IncomeLossFromOperations": "operating_income",
    
    # Non-Operating
    "InterestExpense": "interest_expense",
    "InterestExpenseNonoperating": "interest_expense",
    "InterestIncome": "interest_income",
    "InterestIncomeOperating": "interest_income",  # Operating interest income (crypto staking, etc.)
    "InterestAndOtherIncome": "interest_investment_income",  # TIKR: "Interest And Investment Income"
    "InvestmentIncomeInterest": "investment_income",
    "InvestmentIncomeInterestAndDividend": "investment_income",
    "IncomeLossFromEquityMethodInvestments": "equity_method_income",
    "ForeignCurrencyTransactionGainLossBeforeTax": "foreign_exchange_gain_loss",
    "GainLossOnSaleOfSecuritiesNet": "gain_loss_securities",
    "GainLossOnDispositionOfAssets": "gain_loss_sale_assets",
    "GoodwillImpairmentLoss": "impairment_charges",
    "AssetImpairmentCharges": "impairment_charges",
    "OtherNonoperatingIncomeExpense": "other_nonoperating",
    "CryptoAssetRealizedAndUnrealizedGainLossNonoperating": "crypto_gains_nonoperating",  # COIN crypto gains
    "NonoperatingIncomeExpense": "total_nonoperating",
    
    # Interest And Investment Income (for companies like COIN)
    "InterestAndOtherIncomeNet": "interest_investment_income",
    "InvestmentIncomeNet": "interest_investment_income",
    
    # EBT and Tax - Múltiples conceptos históricos
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "income_before_tax",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": "income_before_tax",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic": "income_before_tax",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign": "income_before_tax",
    "IncomeLossBeforeIncomeTaxExpenseBenefit": "income_before_tax",
    "IncomeLossAttributableToParent": "income_before_tax",
    "ProfitLossBeforeTax": "income_before_tax",
    "IncomeTaxExpenseBenefit": "income_tax",
    "EffectiveIncomeTaxRateContinuingOperations": "effective_tax_rate",
    
    # Net Income
    "IncomeLossFromContinuingOperations": "income_continuing_ops",
    "IncomeLossFromDiscontinuedOperationsNetOfTax": "income_discontinued_ops",
    "NetIncomeLossAttributableToNoncontrollingInterest": "minority_interest",
    "NetIncomeLoss": "net_income",
    "NetIncomeLossAvailableToCommonStockholdersBasic": "net_income_to_common",
    "ProfitLoss": "net_income",
    
    # Per Share
    "EarningsPerShareBasic": "eps_basic",
    "EarningsPerShareDiluted": "eps_diluted",
    "WeightedAverageNumberOfSharesOutstandingBasic": "shares_basic",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "shares_diluted",
    "CommonStockDividendsPerShareDeclared": "dividend_per_share",
    
    # === BALANCE SHEET ===
    "CashAndCashEquivalentsAtCarryingValue": "cash",
    "RestrictedCashAndCashEquivalentsAtCarryingValue": "restricted_cash",
    "ShortTermInvestments": "st_investments",
    "AccountsReceivableNetCurrent": "receivables",
    "ReceivablesNetCurrent": "receivables",
    "InventoryNet": "inventory",
    "PrepaidExpenseAndOtherAssetsCurrent": "prepaid",
    "OtherAssetsCurrent": "other_current_assets",
    "AssetsCurrent": "current_assets",
    
    "PropertyPlantAndEquipmentGross": "ppe_gross",
    "AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment": "accumulated_depreciation",
    "PropertyPlantAndEquipmentNet": "ppe",
    "Goodwill": "goodwill",
    "IntangibleAssetsNetExcludingGoodwill": "intangibles",
    "LongTermInvestments": "lt_investments",
    "DeferredTaxAssetsNet": "deferred_tax_assets",
    "OperatingLeaseRightOfUseAsset": "operating_lease_rou",
    "OtherAssetsNoncurrent": "other_noncurrent_assets",
    
    # === FINANCIALS/BROKERAGE ASSETS ===
    "CashAndSecuritiesSegregatedUnderFederalAndOtherRegulations": "securities_segregated",
    "SecuritiesSegregated": "securities_segregated",
    "FinancialInstrumentsOwnedAtFairValue": "securities_owned",
    "TradingSecurities": "securities_owned",
    "SecuritiesOwned": "securities_owned",
    "SecuritiesBorrowed": "securities_borrowed",
    "SecuritiesPurchasedUnderAgreementsToResell": "securities_borrowed",
    "ReceivablesFromBrokersDealersAndClearingOrganizations": "broker_receivables",
    "ReceivablesFromCustomers": "broker_receivables",
    "DepositsWithClearingOrganizationsAndOthersSecurities": "clearing_deposits",
    "SecuritiesLoaned": "securities_loaned",
    "SecuritiesSoldUnderAgreementsToRepurchase": "securities_loaned",
    "PayablesToBrokerDealersAndClearingOrganizations": "broker_payables",
    "PayablesToCustomers": "broker_payables",
    
    "Assets": "total_assets",
    
    "AccountsPayableCurrent": "accounts_payable",
    "AccruedLiabilitiesCurrent": "accrued_liabilities",
    "DeferredRevenueCurrent": "deferred_revenue",
    "ShortTermBorrowings": "st_debt",
    "LongTermDebtCurrent": "current_portion_lt_debt",
    "OperatingLeaseLiabilityCurrent": "operating_lease_liability_current",
    "OtherLiabilitiesCurrent": "other_current_liabilities",
    "LiabilitiesCurrent": "current_liabilities",
    
    "LongTermDebtNoncurrent": "lt_debt",
    "LongTermDebt": "lt_debt",
    "OperatingLeaseLiabilityNoncurrent": "operating_lease_liability",
    "DeferredTaxLiabilitiesNet": "deferred_tax_liabilities",
    "PensionAndOtherPostretirementBenefitPlansLiabilitiesNoncurrent": "pension_liability",
    "OtherLiabilitiesNoncurrent": "other_noncurrent_liabilities",
    "Liabilities": "total_liabilities",
    
    "PreferredStockValue": "preferred_stock",
    "CommonStockValue": "common_stock",
    "AdditionalPaidInCapitalCommonStock": "apic",
    "RetainedEarningsAccumulatedDeficit": "retained_earnings",
    "TreasuryStockValue": "treasury_stock",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax": "accumulated_oci",
    "MinorityInterest": "noncontrolling_interest",
    "StockholdersEquity": "total_equity",
    
    # === CASH FLOW - Operating Activities ===
    "NetCashProvidedByUsedInOperatingActivities": "operating_cf",
    "DepreciationDepletionAndAmortization": "depreciation_amortization",
    "DepreciationAndAmortization": "depreciation_amortization",
    "OperatingandFinancingLeaseRightofUseAssetAmortization": "depreciation_amortization",
    "ShareBasedCompensation": "stock_compensation",
    "ImpairmentOfAssetsAndOtherNonCashOperatingActivitiesNet": "asset_writedown",
    "AssetImpairmentCharges": "asset_writedown",
    "IncreaseDecreaseInAccountsReceivable": "change_receivables",
    "IncreaseDecreaseInInventories": "change_inventory",
    "IncreaseDecreaseInAccountsPayable": "change_payables",
    "IncreaseDecreaseInOtherOperatingCapitalNet": "other_operating_cf",
    
    # === CASH FLOW - Investing Activities ===
    "NetCashProvidedByUsedInInvestingActivities": "investing_cf",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
    "PaymentsToAcquireBusinessesNetOfCashAcquired": "acquisitions",
    "PaymentsToAcquireInvestments": "purchase_investments",
    "PaymentsToAcquireShortTermInvestments": "purchase_investments",
    "ProceedsFromSaleAndMaturityOfMarketableSecurities": "sale_investments",
    "PaymentsForProceedsFromOtherInvestingActivities": "other_investing_cf",
    
    # === CASH FLOW - Financing Activities ===
    "NetCashProvidedByUsedInFinancingActivities": "financing_cf",
    "ProceedsFromIssuanceOfLongTermDebt": "debt_issued",
    "ProceedsFromShortTermDebt": "debt_issued",
    "RepaymentsOfLongTermDebt": "debt_repaid",
    "RepaymentsOfShortTermDebt": "debt_repaid",
    "ProceedsFromIssuanceOfCommonStock": "stock_issued",
    "StockIssuedDuringPeriodValueRestrictedStockAwardGross": "stock_issued",
    "PaymentsForRepurchaseOfCommonStock": "stock_repurchased",
    "PaymentsOfDividendsCommonStock": "dividends_paid",
    "PaymentsOfDividends": "dividends_paid",
    "OperatingLeasePayments": "operating_lease_payments",
    "FinanceLeasePrincipalPayments": "finance_lease_payments",
    "FinancingLeasePaymentsAndOtherFinancingActivitiesNet": "finance_lease_payments",
    "ProceedsFromPaymentsForOtherFinancingActivities": "other_financing_cf",
    
    # === CASH FLOW - Net Change ===
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "fx_effect",
    "EffectOfExchangeRateOnCashAndCashEquivalents": "fx_effect",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect": "net_change_cash",
    "CashAndCashEquivalentsPeriodIncreaseDecrease": "net_change_cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "cash_ending",
    "CashAndCashEquivalentsAtCarryingValue": "cash_ending",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations": "cash_ending",
    # Cash Beginning - note: often calculated, not reported directly
    
    # === CASH FLOW - Supplemental ===
    "InterestPaidNet": "interest_paid",
    "InterestPaid": "interest_paid",
    "IncomeTaxesPaid": "taxes_paid",
    "IncomeTaxesPaidNet": "taxes_paid",
    
    # === Campos a filtrar (no son Cash Flow) ===
    "StockIssuedDuringPeriodSharesRestrictedStockAwardGross": "_skip_shares",
    "DividendsPayableCurrent": "_skip_balance_sheet",
    "PaymentsToMinorityShareholders": "payments_to_minority",
    "PaymentsOfDividendsMinorityInterest": "payments_to_minority",
    
    # === BALANCE SHEET - Leases (ASC 842) ===
    "OperatingLeaseRightOfUseAsset": "rou_assets",
    "OperatingLeaseandFinanceLeaserightofuseassets": "rou_assets",
    "FinanceLeaseRightOfUseAsset": "finance_lease_rou",
    "FinanceLeaseRightOfUseAssetAfterAccumulatedAmortization": "finance_lease_rou",
    "OperatingLeaseLiability": "lease_liabilities",
    "OperatingLeaseandFinanceLeaseLiabilities": "lease_liabilities",
    "OperatingLeaseLiabilityCurrent": "lease_liabilities_current",
    "OperatingLeaseLiabilityNoncurrent": "lease_liabilities_noncurrent",
    "FinanceLeaseLiability": "finance_lease_liability",
    "FinanceLeaseLiabilityCurrent": "finance_lease_liability_current",
    "FinanceLeaseLiabilityNoncurrent": "finance_lease_liability_noncurrent",
    
    # === INCOME STATEMENT - Lease Costs (ASC 842) ===
    "OperatingLeaseCost": "operating_lease_cost",
    "FinanceLeaseRightOfUseAssetAmortization": "finance_lease_amortization",
    "FinanceLeaseInterestExpense": "finance_lease_interest",
    "VariableLeaseCost": "variable_lease_cost",
    "ShortTermLeaseCost": "short_term_lease_cost",
    "LeaseCost": "total_lease_cost",
    
    # === BALANCE SHEET - Deferred Costs ===
    "DeferredFinanceCostsNet": "deferred_finance_costs",
    "DeferredFinanceCostsGross": "deferred_finance_costs",
    "UnamortizedDebtIssuanceExpense": "deferred_finance_costs",
    
    # === BALANCE SHEET - Deferred Taxes ===
    "DeferredIncomeTaxAssetsNet": "deferred_tax_assets",
    "DeferredTaxAssetsGross": "deferred_tax_assets",
    "DeferredTaxAssetsNet": "deferred_tax_assets",
    "DeferredIncomeTaxLiabilities": "deferred_tax_liabilities",
    "DeferredIncomeTaxLiabilitiesNet": "deferred_tax_liabilities",
    "DeferredTaxLiabilities": "deferred_tax_liabilities",
    
    # === INCOME STATEMENT - Other ===
    "OtherIncome": "other_nonoperating",
    "OtherIncomeExpenseNet": "other_nonoperating",
    "OtherNonoperatingIncome": "other_nonoperating",
    "OtherNonoperatingIncomeExpense": "other_nonoperating",
    
    # === Detalle de impuestos (skip - muy granular) ===
    "CurrentFederalTaxExpenseBenefit": "_skip_tax_detail",
    "CurrentForeignTaxExpenseBenefit": "_skip_tax_detail",
    "CurrentStateAndLocalTaxExpenseBenefit": "_skip_tax_detail",
    "DeferredFederalIncomeTaxExpenseBenefit": "_skip_tax_detail",
    "DeferredForeignIncomeTaxExpenseBenefit": "_skip_tax_detail",
    "DeferredStateAndLocalIncomeTaxExpenseBenefit": "_skip_tax_detail",
    "IncomeTaxReconciliationStateAndLocalIncomeTaxes": "_skip_tax_detail",
    "IncomeTaxReconciliationForeignIncomeTaxRateDifferential": "_skip_tax_detail",
    "IncomeTaxReconciliationDeductions": "_skip_tax_detail",
    "IncomeTaxReconciliationOtherReconcilingItems": "_skip_tax_detail",
    "UnrecognizedTaxBenefits": "_skip_tax_detail",
    "UnrecognizedTaxBenefitsThatWouldImpactEffectiveTaxRate": "_skip_tax_detail",
    
    # === Effective Tax Rates (skip - ratios detallados) ===
    "EffectiveIncomeTaxRateReconciliationAtFederalStatutoryIncomeTaxRate": "_skip_tax_rate",
    "EffectiveIncomeTaxRateReconciliationStateAndLocalIncomeTaxes": "_skip_tax_rate",
    "EffectiveIncomeTaxRateReconciliationForeignIncomeTaxRateDifferential": "_skip_tax_rate",
}


def get_canonical_key(xbrl_concept: str) -> Optional[str]:
    """
    Obtener key canónica para un concepto XBRL.
    
    Args:
        xbrl_concept: Nombre del concepto XBRL (CamelCase)
        
    Returns:
        Key canónica o None si no hay mapeo
    """
    return XBRL_TO_CANONICAL.get(xbrl_concept)


# =============================================================================
# XBRL CONCEPT GROUPS - Conceptos Equivalentes para Consolidación
# =============================================================================
# 
# Esta es la clave para tener datos completos como TIKR/Koyfin.
# Cuando una empresa cambia el concepto XBRL que usa (ej: CostOfGoodsSold → 
# CostOfGoodsAndServicesSold), estos grupos permiten consolidar todos los 
# valores en un solo campo canónico.
#
# Orden = Prioridad (el primero que tenga valor gana)

XBRL_CONCEPT_GROUPS: Dict[str, List[str]] = {
    # === INCOME STATEMENT ===
    
    # Revenue
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",  # ASC 606 (2018+)
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "NetRevenues",
        "TotalRevenuesAndOtherIncome",
    ],
    
    # Cost of Revenue / COGS
    "cost_of_revenue": [
        "CostOfGoodsAndServicesSold",  # Moderno - preferido
        "CostOfRevenue",
        "CostOfGoodsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
        "CostOfSales",
        "InformationTechnologyAndDataProcessing",  # Tech companies (COIN, etc) use IT costs as COGS
    ],
    
    # Gross Profit
    "gross_profit": [
        "GrossProfit",
        "GrossMargin",
    ],
    
    # Operating Expenses
    "sga_expenses": [
        "SellingGeneralAndAdministrativeExpense",
        "GeneralAndAdministrativeExpense",
        "SellingAndMarketingExpense",
    ],
    
    "rd_expenses": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "TechnologyAndContentExpense",  # Amazon
    ],
    
    # Operating Income
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromOperations",
        "IncomeLossFromContinuingOperations",
    ],
    
    # Income Before Tax - CRÍTICO (muchas variantes históricas)
    "income_before_tax": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",  # + Foreign
        "IncomeLossBeforeIncomeTaxExpenseBenefit",
        "IncomeLossAttributableToParent",
        "ProfitLossBeforeTax",
    ],
    
    # Income Tax
    "income_tax": [
        "IncomeTaxExpenseBenefit",
        "IncomeTaxExpenseBenefitContinuingOperations",
        "CurrentIncomeTaxExpenseBenefit",
    ],
    
    # Net Income
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "NetIncomeLossAttributableToParent",
    ],
    
    # EPS
    "eps_basic": [
        "EarningsPerShareBasic",
        "IncomeLossFromContinuingOperationsPerBasicShare",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
    ],
    
    # Interest
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestIncomeExpenseNet",
    ],
    "interest_income": [
        "InterestIncomeOperating",  # Operating interest (crypto staking, etc.)
        "InterestIncomeOther",
        "InterestIncome",
        "InvestmentIncomeInterest",
    ],
    
    # === BALANCE SHEET ===
    
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
        "Cash",
    ],
    
    "receivables": [
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
        "AccountsNotesAndLoansReceivableNetCurrent",
        "TradeAndOtherReceivablesCurrent",
    ],
    
    "inventory": [
        "InventoryNet",
        "InventoryFinishedGoods",
        "InventoryRawMaterialsAndSupplies",
    ],
    
    "current_assets": [
        "AssetsCurrent",
        "CurrentAssets",
    ],
    
    "ppe": [
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentGross",
        "NetPropertyPlantAndEquipment",
    ],
    
    "total_assets": [
        "Assets",
        "TotalAssets",
    ],
    
    "accounts_payable": [
        "AccountsPayableCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
    ],
    
    "current_liabilities": [
        "LiabilitiesCurrent",
        "CurrentLiabilities",
    ],
    
    "lt_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "DebtNoncurrent",
    ],
    
    "total_liabilities": [
        "Liabilities",
        "TotalLiabilities",
    ],
    
    "retained_earnings": [
        "RetainedEarningsAccumulatedDeficit",
        "RetainedEarningsUnappropriated",
    ],
    
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "TotalEquity",
    ],
    
    # === CASH FLOW ===
    
    # --- Operating Activities ---
    "operating_cf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "CashFlowsFromOperatingActivities",
    ],
    
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
        "OperatingandFinancingLeaseRightofUseAssetAmortization",
    ],
    
    "stock_compensation": [
        "ShareBasedCompensation",
        "StockBasedCompensation",
        "StockOptionPlanExpense",
    ],
    
    "asset_writedown": [
        "ImpairmentOfAssetsAndOtherNonCashOperatingActivitiesNet",
        "AssetImpairmentCharges",
        "GoodwillImpairmentLoss",
        "ImpairmentLosses",
        "RestructuringSettlementAndImpairmentProvisions",
    ],
    
    "gain_loss_equity_investments": [
        "IncomeLossFromEquityMethodInvestments",
        "GainLossOnInvestments",
        "UnrealizedGainLossOnInvestments",
    ],
    
    "change_receivables": [
        "IncreaseDecreaseInAccountsReceivable",
        "IncreaseDecreaseInReceivables",
        "IncreaseDecreaseInAccountsAndOtherReceivables",
    ],
    
    "change_inventory": [
        "IncreaseDecreaseInInventories",
        "IncreaseDecreaseInInventory",
    ],
    
    "change_payables": [
        "IncreaseDecreaseInAccountsPayable",
        "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",
    ],
    
    "other_operating_cf": [
        "IncreaseDecreaseInOtherOperatingCapitalNet",
        "IncreaseDecreaseInOtherOperatingAssets",
        "OtherOperatingActivitiesCashFlowStatement",
    ],
    
    # --- Investing Activities ---
    "investing_cf": [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    ],
    
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpenditures",
        "PurchaseOfPropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ],
    
    "acquisitions": [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndIntangibles",
        "PaymentsToAcquireBusinessTwoNetOfCashAcquired",
    ],
    
    "sale_investments": [
        "ProceedsFromSaleAndMaturityOfMarketableSecurities",
        "ProceedsFromSaleOfInvestments",
        "ProceedsFromMaturitiesOfInvestments",
        "ProceedsFromSaleOfAvailableForSaleSecurities",
    ],
    
    "purchase_investments": [
        "PaymentsToAcquireInvestments",
        "PaymentsToAcquireAvailableForSaleSecurities",
        "PaymentsToAcquireShortTermInvestments",
        "PaymentsToAcquireMarketableSecurities",
    ],
    
    "other_investing_cf": [
        "PaymentsForProceedsFromOtherInvestingActivities",
        "OtherInvestingActivities",
    ],
    
    # --- Financing Activities ---
    "financing_cf": [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    ],
    
    "debt_issued": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfDebt",
        "ProceedsFromShortTermDebt",
    ],
    
    "debt_repaid": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
        "RepaymentsOfShortTermDebt",
        "PaymentsOfDebt",
    ],
    
    "stock_issued": [
        "ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromStockOptionsExercised",
        "StockIssuedDuringPeriodValueRestrictedStockAwardGross",
    ],
    
    "stock_repurchased": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
        "StockRepurchasedDuringPeriodValue",
    ],
    
    "dividends_paid": [
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfDividends",
        "DividendsPaid",
    ],
    
    "special_dividend": [
        "PaymentsOfSpecialDividend",
        "ExtraordinaryDividendPaid",
    ],
    
    "operating_lease_payments": [
        "OperatingLeasePayments",
        "PaymentsForOperatingLeases",
    ],
    
    "finance_lease_payments": [
        "FinanceLeasePrincipalPayments",
        "FinanceLeasePayments",
        "FinancingLeasePaymentsAndOtherFinancingActivitiesNet",
    ],
    
    "other_financing_cf": [
        "ProceedsFromPaymentsForOtherFinancingActivities",
        "OtherFinancingActivities",
    ],
    
    # --- Net Change / Summary ---
    "fx_effect": [
        "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "EffectOfExchangeRateOnCashAndCashEquivalents",
        "ForeignCurrencyTranslationAdjustment",
    ],
    
    "net_change_cash": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
        "NetChangeInCash",
    ],
    
    "cash_beginning": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsStartOfPeriod",
        "CashAndCashEquivalentsAtCarryingValueBeginningOfPeriod",
    ],
    
    "cash_ending": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalentsAtCarryingValue",
    ],
    
    # --- Supplemental ---
    "interest_paid": [
        "InterestPaidNet",
        "InterestPaid",
    ],
    
    "taxes_paid": [
        "IncomeTaxesPaid",
        "IncomeTaxesPaidNet",
    ],
    
    # ==========================================================================
    # INDUSTRY-SPECIFIC CONCEPT GROUPS
    # ==========================================================================
    
    # === BANKING / FINANCIAL SERVICES ===
    
    "net_interest_income": [
        "InterestIncomeExpenseNet",
        "NetInterestIncome",
        "InterestAndDividendIncomeOperating",
        "NetInterestIncomeAfterProvisionForCreditLoss",
    ],
    
    "provision_credit_losses": [
        "ProvisionForLoanLeaseAndOtherLosses",
        "ProvisionForLoanLossesExpensed",
        "ProvisionForCreditLosses",
        "AllowanceForLoanAndLeaseLossesWriteoffsNet",
    ],
    
    "noninterest_income": [
        "NoninterestIncome",
        "FeesAndCommissions",
        "InvestmentBankingRevenue",
        "TradingRevenue",
        "AssetManagementFees",
    ],
    
    "noninterest_expense": [
        "NoninterestExpense",
        "OtherNoninterestExpense",
    ],
    
    "loans_net": [
        "LoansAndLeasesReceivableNetReportedAmount",
        "LoansReceivableNet",
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
    ],
    
    "deposits": [
        "Deposits",
        "DepositsDomestic",
        "DepositsForeign",
        "InterestBearingDepositsInBanks",
    ],
    
    # === INSURANCE ===
    
    "premiums_earned": [
        "PremiumsEarned",
        "PremiumsEarnedNet",
        "DirectPremiumsEarned",
        "NetPremiumsEarned",
        "InsurancePremiumsRevenueRecognitionPolicy",
    ],
    
    "policy_benefits": [
        "PolicyholderBenefitsAndClaimsIncurredNet",
        "BenefitsLossesAndExpenses",
        "PolicyholderBenefitsAndClaimsIncurredLifeAndAnnuity",
        "InsuranceClaimsAndPolicyholdersLiabilities",
    ],
    
    "medical_costs": [
        "MedicalCostsRatio",
        "MedicalClaimsExpense",
        "HealthCareCosts",
        "MedicalBenefitsExpense",
    ],
    
    "insurance_revenue": [
        "InsuranceServicesRevenueNet",
        "PremiumsWrittenNet",
        "NetPremiumsWritten",
    ],
    
    # === REAL ESTATE / REITs ===
    
    "rental_revenue": [
        "OperatingLeaseLeaseIncome",
        "RentalIncomeNonoperating",
        "LeaseIncome",
        "OperatingLeasesIncomeStatementMinimumLeaseRevenue",
        "RealEstateRevenueNet",
    ],
    
    "noi": [  # Net Operating Income
        "NetOperatingIncome",
        "RealEstateInvestmentPropertyNetIncomeFromProperty",
    ],
    
    "ffo": [  # Funds From Operations
        "FundsFromOperations",
        "FFONareit",
        "AdjustedFundsFromOperations",
    ],
    
    "real_estate_assets": [
        "RealEstateInvestmentPropertyNet",
        "RealEstateHeldForInvestment",
        "InvestmentBuildingAndBuildingImprovements",
    ],
    
    # === ENERGY / OIL & GAS ===
    
    "exploration_costs": [
        "ExplorationCosts",
        "ExplorationExpense",
        "OilAndGasExplorationExpense",
    ],
    
    "production_costs": [
        "ProductionCosts",
        "OilAndGasProductionExpense",
        "CostOfOilAndGasProduction",
    ],
    
    "depletion": [
        "Depletion",
        "DepreciationDepletionAndAmortizationProductiveAssets",
        "OilAndGasPropertySuccessfulEffortMethodDepreciationDepletionAndAmortization",
    ],
    
    # === UTILITIES ===
    
    "electric_revenue": [
        "ElectricUtilityRevenue",
        "ElectricDomesticRevenue",
        "RevenueFromElectricity",
        "ElectricityRevenue",
    ],
    
    "gas_revenue": [
        "NaturalGasGatheringTransportationMarketingAndProcessingRevenue",
        "NaturalGasDomesticRevenue",
        "GasAndOilRevenue",
    ],
    
    "fuel_costs": [
        "FuelCosts",
        "CostOfFuel",
        "FuelExpense",
    ],
    
    "purchased_power": [
        "CostOfPurchasedPower",
        "PurchasedPowerAndGas",
    ],
    
    # === TECHNOLOGY ===
    
    "license_revenue": [
        "LicenseRevenue",
        "LicensesRevenue",
        "SoftwareLicenseRevenue",
    ],
    
    "cloud_revenue": [
        "CloudServicesRevenue",
        "SaaSRevenue",
        "SubscriptionRevenue",
    ],
    
    "hardware_revenue": [
        "HardwareRevenue",
        "ProductRevenue",
        "DeviceSales",
    ],
    
    "content_costs": [
        "ContentCosts",
        "CostOfContent",
        "ProgrammingCosts",
    ],
    
    # === HEALTHCARE / PHARMA ===
    
    "drug_sales": [
        "PharmaceuticalRevenue",
        "DrugSales",
        "ProductSalesNet",
    ],
    
    "rd_in_process": [
        "ResearchAndDevelopmentInProcess",
        "AcquiredInProcessResearchAndDevelopment",
        "IPRDExpense",
    ],
    
    "royalty_revenue": [
        "RoyaltyRevenue",
        "LicenseAndRoyaltyRevenue",
        "Royalties",
    ],
    
    # === RETAIL ===
    
    "same_store_sales": [
        "ComparableStoreSales",
        "SameStoreSales",
    ],
    
    "e_commerce_revenue": [
        "EcommerceRevenue",
        "OnlineStoreRevenue",
        "DirectToConsumerSales",
    ],
    
    # === TELECOM ===
    
    "wireless_revenue": [
        "WirelessRevenue",
        "MobileServiceRevenue",
        "ServiceRevenue",
    ],
    
    "equipment_revenue": [
        "EquipmentRevenue",
        "EquipmentSales",
        "DeviceAndAccessoryRevenue",
    ],
    
    "subscriber_acquisition_cost": [
        "SubscriberAcquisitionCost",
        "CostToObtainContract",
    ],
    
    # === TRANSPORTATION ===
    
    "passenger_revenue": [
        "PassengerRevenue",
        "PassengerTransportationRevenue",
        "PassengerMileRevenue",
    ],
    
    "cargo_revenue": [
        "CargoRevenue",
        "FreightRevenue",
        "CargoAndOtherRevenue",
    ],
    
    "fuel_expense": [
        "AircraftFuelExpense",
        "FuelAndOilExpense",
        "FuelCost",
    ],
    
    # === GENERAL ADDITIONAL MAPPINGS ===
    
    "goodwill": [
        "Goodwill",
        "GoodwillGross",
        "GoodwillNet",
    ],
    
    "intangibles": [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
        "IndefiniteLivedIntangibleAssetsExcludingGoodwill",
        "IntangibleAssetsNetIncludingGoodwill",
    ],
    
    "lt_investments": [
        "LongTermInvestments",
        "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
        "EquityMethodInvestments",
        "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
    ],
    
    "st_investments": [
        "ShortTermInvestments",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecurities",
    ],
    
    "st_debt": [
        "ShortTermBorrowings",
        "ShortTermDebt",
        "LinesOfCreditCurrent",
        "CommercialPaper",
    ],
    
    "deferred_revenue_nc": [
        "DeferredRevenueNoncurrent",
        "ContractWithCustomerLiabilityNoncurrent",
    ],
    
    "pension_liability": [
        "PensionAndOtherPostretirementBenefitPlansLiabilitiesNoncurrent",
        "DefinedBenefitPensionPlanLiabilitiesNoncurrent",
        "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent",
    ],
    
    "accumulated_oci": [
        "AccumulatedOtherComprehensiveIncomeLossNetOfTax",
        "AccumulatedOtherComprehensiveIncomeLossForeignCurrencyTranslationAdjustmentNetOfTax",
        "AccumulatedOtherComprehensiveIncomeLossDefinedBenefitPensionAndOtherPostretirementPlansNetOfTax",
    ],
    
    "shares_basic": [
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
    ],
    
    "shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberDilutedSharesOutstandingAdjustment",
    ],
    
    "stock_compensation": [
        "ShareBasedCompensation",
        "AllocatedShareBasedCompensationExpense",
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardCompensationCost",
        "StockCompensationPlanExpense",
    ],
    
    "amortization_intangibles": [
        "AmortizationOfIntangibleAssets",
        "AmortizationOfAcquiredIntangibleAssets",
        "AmortizationOfFiniteLivedIntangibleAssets",
    ],
    
    "gain_loss_investments": [
        "GainLossOnInvestments",
        "GainLossOnSaleOfInvestments",
        "RealizedInvestmentGainsLosses",
        "UnrealizedGainLossOnInvestments",
    ],
    
    "debt_issued": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
    ],
    
    "debt_repaid": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
        "RepaymentsOfLongTermDebtAndCapitalSecurities",
    ],
    
    "acquisitions": [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliates",
        "BusinessCombinationConsiderationTransferred",
    ],
    
    "sale_investments": [
        "ProceedsFromSaleAndMaturityOfMarketableSecurities",
        "ProceedsFromSaleOfAvailableForSaleSecuritiesDebt",
        "ProceedsFromMaturitiesPrepaymentsAndCallsOfAvailableForSaleSecurities",
    ],
    
    "purchase_investments": [
        "PaymentsToAcquireAvailableForSaleSecuritiesDebt",
        "PaymentsToAcquireMarketableSecurities",
        "PaymentsToAcquireInvestments",
    ],
}


def get_concept_group(canonical_key: str) -> List[str]:
    """
    Obtener grupo de conceptos XBRL para un campo canónico.
    
    Args:
        canonical_key: Key del campo canónico
        
    Returns:
        Lista de conceptos XBRL equivalentes (en orden de prioridad)
    """
    return XBRL_CONCEPT_GROUPS.get(canonical_key, [])


def get_all_xbrl_concepts() -> Dict[str, str]:
    """
    Obtener mapeo inverso: XBRL concept → canonical key.
    Incluye tanto XBRL_TO_CANONICAL como todos los concept groups.
    """
    result = dict(XBRL_TO_CANONICAL)
    for canonical_key, concepts in XBRL_CONCEPT_GROUPS.items():
        for concept in concepts:
            if concept not in result:
                result[concept] = canonical_key
    return result


# Total de campos en el schema
SCHEMA_STATS = {
    "income_statement": len(INCOME_STATEMENT_SCHEMA),
    "balance_sheet": len(BALANCE_SHEET_SCHEMA),
    "cash_flow": len(CASH_FLOW_SCHEMA),
    "total_canonical": len(CANONICAL_FIELDS),
    "total_xbrl_mappings": len(XBRL_TO_CANONICAL),
}

if __name__ == "__main__":
    print("=== SCHEMA STATS ===")
    for k, v in SCHEMA_STATS.items():
        print(f"  {k}: {v}")

