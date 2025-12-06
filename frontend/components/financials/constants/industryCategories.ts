import type { IndustryCategory } from '../types';

// ============================================================================
// FMP INDUSTRY MAPPING
// Maps 150+ FMP industries to our analytical categories
// ============================================================================

export function mapFMPIndustryToCategory(fmpIndustry: string | undefined): IndustryCategory {
    if (!fmpIndustry) return 'general';
    const industry = fmpIndustry.toLowerCase();

    // === TECHNOLOGY ===
    if (industry.includes('software - application')) return 'software';
    if (industry.includes('software - infrastructure')) return 'software';
    if (industry.includes('software - services')) return 'software';
    if (industry.includes('information technology')) return 'software';
    if (industry.includes('semiconductor')) return 'semiconductor';
    if (industry.includes('consumer electronics')) return 'hardware';
    if (industry.includes('computer hardware')) return 'hardware';
    if (industry.includes('hardware, equipment')) return 'hardware';
    if (industry.includes('technology distributors')) return 'hardware';
    if (industry.includes('communication equipment')) return 'telecom';
    if (industry.includes('internet content')) return 'internet';
    if (industry.includes('electronic gaming')) return 'gaming';

    // === TELECOMMUNICATIONS ===
    if (industry.includes('telecommunications')) return 'telecom';

    // === FINANCIAL SERVICES ===
    if (industry.includes('banks - diversified')) return 'bank';
    if (industry.includes('banks - regional')) return 'bank';
    if (industry.includes('banks')) return 'bank';
    if (industry.includes('insurance - life')) return 'insurance';
    if (industry.includes('insurance - property')) return 'insurance';
    if (industry.includes('insurance - specialty')) return 'insurance';
    if (industry.includes('insurance - reinsurance')) return 'insurance';
    if (industry.includes('insurance - diversified')) return 'insurance';
    if (industry.includes('insurance - brokers')) return 'insurance';
    if (industry.includes('insurance')) return 'insurance';
    if (industry.includes('asset management')) return 'asset_management';
    if (industry.includes('financial - capital markets')) return 'asset_management';
    if (industry.includes('financial - credit services')) return 'fintech';
    if (industry.includes('financial - data')) return 'fintech';
    if (industry.includes('financial - diversified')) return 'fintech';
    if (industry.includes('financial - mortgages')) return 'fintech';
    if (industry.includes('financial - conglomerates')) return 'fintech';
    if (industry.includes('investment - banking')) return 'asset_management';
    if (industry.includes('shell companies')) return 'general';

    // === REAL ESTATE ===
    if (industry.includes('reit -')) return 'reit';
    if (industry.includes('reit')) return 'reit';
    if (industry.includes('real estate -')) return 'real_estate';
    if (industry.includes('real estate')) return 'real_estate';

    // === HEALTHCARE ===
    if (industry.includes('biotechnology')) return 'biotech';
    if (industry.includes('drug manufacturers - general')) return 'pharma';
    if (industry.includes('drug manufacturers - specialty')) return 'pharma';
    if (industry.includes('medical - pharmaceuticals')) return 'pharma';
    if (industry.includes('medical - devices')) return 'medical_devices';
    if (industry.includes('medical - instruments')) return 'medical_devices';
    if (industry.includes('medical - equipment')) return 'medical_devices';
    if (industry.includes('medical - diagnostics')) return 'medical_devices';
    if (industry.includes('medical - healthcare plans')) return 'healthcare_services';
    if (industry.includes('medical - healthcare information')) return 'healthcare_services';
    if (industry.includes('medical - care facilities')) return 'healthcare_services';
    if (industry.includes('medical - distribution')) return 'healthcare_services';
    if (industry.includes('medical - specialties')) return 'healthcare_services';
    if (industry.includes('medical')) return 'healthcare_services';

    // === CONSUMER CYCLICAL ===
    if (industry.includes('discount stores')) return 'retail';
    if (industry.includes('department stores')) return 'retail';
    if (industry.includes('specialty retail')) return 'retail';
    if (industry.includes('home improvement')) return 'retail';
    if (industry.includes('grocery stores')) return 'retail';
    if (industry.includes('internet retail')) return 'ecommerce';
    if (industry.includes('restaurants')) return 'restaurants';
    if (industry.includes('apparel - retail')) return 'apparel';
    if (industry.includes('apparel - manufacturers')) return 'apparel';
    if (industry.includes('apparel - footwear')) return 'apparel';
    if (industry.includes('luxury goods')) return 'apparel';
    if (industry.includes('auto - manufacturers')) return 'auto';
    if (industry.includes('auto - parts')) return 'auto';
    if (industry.includes('auto - dealerships')) return 'auto';
    if (industry.includes('auto - recreational')) return 'auto';
    if (industry.includes('furnishings')) return 'consumer_products';
    if (industry.includes('leisure')) return 'travel';
    if (industry.includes('gambling')) return 'gaming';
    if (industry.includes('resorts & casinos')) return 'gaming';
    if (industry.includes('travel lodging')) return 'travel';
    if (industry.includes('travel services')) return 'travel';
    if (industry.includes('residential construction')) return 'construction';

    // === CONSUMER DEFENSIVE ===
    if (industry.includes('packaged foods')) return 'consumer_products';
    if (industry.includes('household & personal')) return 'consumer_products';
    if (industry.includes('personal products')) return 'consumer_products';
    if (industry.includes('food distribution')) return 'consumer_products';
    if (industry.includes('food confectioners')) return 'consumer_products';
    if (industry.includes('beverages - non-alcoholic')) return 'beverages';
    if (industry.includes('beverages - alcoholic')) return 'beverages';
    if (industry.includes('beverages - wineries')) return 'beverages';
    if (industry.includes('tobacco')) return 'consumer_products';
    if (industry.includes('education')) return 'education';

    // === INDUSTRIALS ===
    if (industry.includes('aerospace & defense')) return 'aerospace';
    if (industry.includes('industrial - machinery')) return 'industrial';
    if (industry.includes('industrial - capital goods')) return 'industrial';
    if (industry.includes('industrial - specialties')) return 'industrial';
    if (industry.includes('industrial - distribution')) return 'industrial';
    if (industry.includes('industrial - infrastructure')) return 'industrial';
    if (industry.includes('industrial - pollution')) return 'industrial';
    if (industry.includes('manufacturing - tools')) return 'industrial';
    if (industry.includes('manufacturing - metal')) return 'industrial';
    if (industry.includes('manufacturing - textiles')) return 'industrial';
    if (industry.includes('manufacturing - miscellaneous')) return 'industrial';
    if (industry.includes('electrical equipment')) return 'industrial';
    if (industry.includes('engineering & construction')) return 'construction';
    if (industry.includes('construction materials')) return 'construction';
    if (industry.includes('construction')) return 'construction';
    if (industry.includes('business equipment')) return 'industrial';
    if (industry.includes('consulting services')) return 'industrial';
    if (industry.includes('staffing')) return 'industrial';
    if (industry.includes('security & protection')) return 'industrial';
    if (industry.includes('specialty business')) return 'industrial';
    if (industry.includes('rental & leasing')) return 'industrial';
    if (industry.includes('conglomerates')) return 'conglomerate';

    // === TRANSPORTATION ===
    if (industry.includes('airlines')) return 'transportation';
    if (industry.includes('railroads')) return 'transportation';
    if (industry.includes('trucking')) return 'transportation';
    if (industry.includes('marine shipping')) return 'transportation';
    if (industry.includes('integrated freight')) return 'transportation';
    if (industry.includes('general transportation')) return 'transportation';

    // === ENERGY ===
    if (industry.includes('oil & gas')) return 'oil_gas';
    if (industry.includes('coal')) return 'oil_gas';
    if (industry.includes('uranium')) return 'oil_gas';
    if (industry.includes('solar')) return 'utilities';

    // === BASIC MATERIALS ===
    if (industry.includes('gold')) return 'mining';
    if (industry.includes('silver')) return 'mining';
    if (industry.includes('copper')) return 'mining';
    if (industry.includes('aluminum')) return 'mining';
    if (industry.includes('steel')) return 'mining';
    if (industry.includes('other precious metals')) return 'mining';
    if (industry.includes('industrial materials')) return 'mining';
    if (industry.includes('paper, lumber')) return 'mining';
    if (industry.includes('chemicals - specialty')) return 'chemicals';
    if (industry.includes('chemicals')) return 'chemicals';
    if (industry.includes('agricultural inputs')) return 'chemicals';
    if (industry.includes('agricultural - machinery')) return 'industrial';
    if (industry.includes('agricultural - commodities')) return 'consumer_products';
    if (industry.includes('agricultural farm')) return 'consumer_products';
    if (industry.includes('packaging')) return 'industrial';

    // === UTILITIES ===
    if (industry.includes('regulated electric')) return 'utilities';
    if (industry.includes('regulated gas')) return 'utilities';
    if (industry.includes('regulated water')) return 'utilities';
    if (industry.includes('renewable utilities')) return 'utilities';
    if (industry.includes('diversified utilities')) return 'utilities';
    if (industry.includes('independent power')) return 'utilities';
    if (industry.includes('general utilities')) return 'utilities';
    if (industry.includes('utilities')) return 'utilities';
    if (industry.includes('waste management')) return 'utilities';
    if (industry.includes('environmental services')) return 'utilities';

    // === COMMUNICATION SERVICES ===
    if (industry.includes('media & entertainment')) return 'media';
    if (industry.includes('entertainment')) return 'media';
    if (industry.includes('broadcasting')) return 'media';
    if (industry.includes('publishing')) return 'media';
    if (industry.includes('advertising')) return 'media';

    return 'general';
}

