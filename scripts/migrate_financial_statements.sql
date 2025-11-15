-- Migration: Add all missing columns to financial_statements
-- This ensures we capture ALL fields from Polygon API

-- Income Statement fields
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS cost_of_revenue NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS research_development NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS selling_general_administrative NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_operating_expenses NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS total_operating_expenses NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS interest_expense NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS interest_income NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_income_expense NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS income_before_taxes NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS income_taxes NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS ebitda NUMERIC(20,2);

-- Balance Sheet - Assets
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS receivables NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS inventories NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_current_assets NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS property_plant_equipment_net NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS goodwill NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS intangible_assets_net NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_noncurrent_assets NUMERIC(20,2);

-- Balance Sheet - Liabilities
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS accounts_payable NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS debt_current NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS accrued_liabilities NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS deferred_revenue_current NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS long_term_debt NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_noncurrent_liabilities NUMERIC(20,2);

-- Balance Sheet - Equity
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS common_stock NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS additional_paid_in_capital NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS treasury_stock NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS retained_earnings NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS accumulated_other_comprehensive_income NUMERIC(20,2);

-- Cash Flow Statement
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS depreciation_amortization NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS stock_based_compensation NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS change_in_working_capital NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_operating_activities NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS capital_expenditures NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS acquisitions NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_investing_activities NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS debt_issuance_repayment NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS dividends_paid NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS stock_repurchased NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS other_financing_activities NUMERIC(20,2);
ALTER TABLE financial_statements ADD COLUMN IF NOT EXISTS change_in_cash NUMERIC(20,2);

-- Verify
SELECT 
    'Migration completed. Total columns:' as message,
    COUNT(*) as column_count
FROM information_schema.columns 
WHERE table_name = 'financial_statements';

