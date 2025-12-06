// ============================================================================
// TYPES - Financial Statement Structures (FMP API)
// ============================================================================

export interface FinancialPeriod {
    date: string;
    symbol: string;
    fiscal_year: string;
    period: string;  // Q1, Q2, Q3, Q4, FY
    filing_date?: string;
    currency: string;
}

export interface IncomeStatement {
    period: FinancialPeriod;
    // Revenue & Cost
    revenue?: number;
    cost_of_revenue?: number;
    gross_profit?: number;
    // Operating Expenses
    research_development?: number;
    selling_general_admin?: number;
    operating_expenses?: number;
    operating_income?: number;
    // Interest (Critical for Banks/Financial)
    interest_expense?: number;
    interest_income?: number;
    net_interest_income?: number;
    // Other Income/Expense
    other_income_expense?: number;
    income_before_tax?: number;
    income_tax?: number;
    net_income?: number;
    // Per Share
    eps?: number;
    eps_diluted?: number;
    shares_outstanding?: number;
    shares_diluted?: number;
    // Profitability Metrics
    ebitda?: number;
    ebit?: number;
    depreciation?: number;
}

export interface BalanceSheet {
    period: FinancialPeriod;
    // Assets
    total_assets?: number;
    current_assets?: number;
    cash_and_equivalents?: number;
    short_term_investments?: number;
    cash_and_short_term?: number;
    receivables?: number;
    inventory?: number;
    other_current_assets?: number;
    // Non-Current Assets
    property_plant_equipment?: number;
    goodwill?: number;
    intangible_assets?: number;
    long_term_investments?: number;
    other_noncurrent_assets?: number;
    noncurrent_assets?: number;
    // Liabilities
    total_liabilities?: number;
    current_liabilities?: number;
    accounts_payable?: number;
    short_term_debt?: number;
    deferred_revenue?: number;
    other_current_liabilities?: number;
    long_term_debt?: number;
    other_noncurrent_liabilities?: number;
    noncurrent_liabilities?: number;
    // Equity
    total_equity?: number;
    common_stock?: number;
    retained_earnings?: number;
    treasury_stock?: number;
    accumulated_other_income?: number;
    // Key Metrics
    total_debt?: number;
    net_debt?: number;
    total_investments?: number;
}

export interface CashFlow {
    period: FinancialPeriod;
    // Operating Activities
    net_income?: number;
    depreciation?: number;
    stock_compensation?: number;
    change_working_capital?: number;
    change_receivables?: number;
    change_inventory?: number;
    change_payables?: number;
    other_operating?: number;
    operating_cash_flow?: number;
    // Investing Activities
    capex?: number;
    acquisitions?: number;
    purchases_investments?: number;
    sales_investments?: number;
    other_investing?: number;
    investing_cash_flow?: number;
    // Financing Activities
    debt_issued?: number;
    debt_repaid?: number;
    stock_issued?: number;
    stock_repurchased?: number;
    dividends_paid?: number;
    other_financing?: number;
    financing_cash_flow?: number;
    // Summary
    net_change_cash?: number;
    cash_beginning?: number;
    cash_ending?: number;
    free_cash_flow?: number;
}

export interface FinancialData {
    symbol: string;
    currency: string;
    industry?: string;   // From FMP Profile API
    sector?: string;     // From FMP Profile API
    income_statements: IncomeStatement[];
    balance_sheets: BalanceSheet[];
    cash_flows: CashFlow[];
    last_updated: string;
    cached: boolean;
    cache_age_seconds?: number;
}

export type TabType = 'income' | 'balance' | 'cashflow';
export type PeriodFilter = 'annual' | 'quarter' | 'all';

// ============================================================================
// INDUSTRY TYPES
// ============================================================================

export type IndustryCategory =
    | 'software'           // Software - Application, Infrastructure, Services
    | 'semiconductor'      // Semiconductors, Equipment
    | 'hardware'           // Consumer Electronics, Computer Hardware
    | 'internet'           // Internet Content & Information
    | 'telecom'            // Telecommunications Services, Equipment
    | 'bank'               // Banks - Diversified, Regional
    | 'insurance'          // Insurance - All types
    | 'asset_management'   // Asset Management, Capital Markets
    | 'fintech'            // Financial Services, Credit, Data
    | 'reit'               // All REIT types
    | 'real_estate'        // Real Estate Services, Development
    | 'biotech'            // Biotechnology
    | 'pharma'             // Drug Manufacturers
    | 'medical_devices'    // Medical Devices, Instruments
    | 'healthcare_services'// Healthcare Plans, Facilities, Services
    | 'retail'             // Discount Stores, Department, Specialty
    | 'ecommerce'          // Internet Retail
    | 'restaurants'        // Restaurants, Food Service
    | 'consumer_products'  // Household, Personal Products, Packaged Foods
    | 'beverages'          // Alcoholic, Non-Alcoholic Beverages
    | 'apparel'            // Apparel Manufacturers, Retail
    | 'auto'               // Auto Manufacturers, Parts, Dealerships
    | 'aerospace'          // Aerospace & Defense
    | 'industrial'         // Industrial Machinery, Manufacturing
    | 'construction'       // Construction, Engineering, Materials
    | 'transportation'     // Airlines, Railroads, Trucking, Shipping
    | 'oil_gas'            // Oil & Gas - All segments
    | 'mining'             // Gold, Silver, Copper, Steel, Aluminum
    | 'utilities'          // Electric, Gas, Water, Renewable
    | 'chemicals'          // Specialty, Agricultural Chemicals
    | 'media'              // Entertainment, Broadcasting, Publishing
    | 'gaming'             // Gambling, Casinos, Electronic Gaming
    | 'travel'             // Travel Services, Lodging, Leisure
    | 'education'          // Education & Training
    | 'conglomerate'       // Conglomerates
    | 'general';           // Default/Unknown

export interface KPIDefinition {
    name: string;
    formula: string;
    calculate: (data: FinancialData) => number | undefined;
    format: 'percent' | 'ratio' | 'currency' | 'days' | 'turns';
    benchmark?: { good: number; bad: number };
    tooltip: string;
}

export interface IndustryProfile {
    category: IndustryCategory;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    description: string;
    kpis: KPIDefinition[];
}

// Table row definitions
export interface TableRowDefinition {
    key: string;
    label: string;
    isHeader?: boolean;
    isCalculated?: boolean;
    indent?: number;
}

