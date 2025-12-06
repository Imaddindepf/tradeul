import type { IndustryCategory, IndustryProfile } from '../../types';

// Import all profiles
import { softwareProfile, semiconductorProfile, hardwareProfile, internetProfile, telecomProfile } from './technology';
import { bankProfile, insuranceProfile, assetManagementProfile, fintechProfile, reitProfile, realEstateProfile } from './financial';
import { biotechProfile, pharmaProfile, medicalDevicesProfile, healthcareServicesProfile } from './healthcare';
import { retailProfile, ecommerceProfile, restaurantsProfile, consumerProductsProfile, beveragesProfile, apparelProfile, autoProfile } from './consumer';
import { aerospaceProfile, industrialProfile, constructionProfile, transportationProfile, mediaProfile, gamingProfile, travelProfile, educationProfile, conglomerateProfile } from './industrial';
import { oilGasProfile, miningProfile, utilitiesProfile, chemicalsProfile, generalProfile } from './energy';

// ============================================================================
// INDUSTRY PROFILES REGISTRY
// ============================================================================

export const INDUSTRY_PROFILES: Record<IndustryCategory, IndustryProfile> = {
    // Technology
    software: softwareProfile,
    semiconductor: semiconductorProfile,
    hardware: hardwareProfile,
    internet: internetProfile,
    telecom: telecomProfile,

    // Financial
    bank: bankProfile,
    insurance: insuranceProfile,
    asset_management: assetManagementProfile,
    fintech: fintechProfile,
    reit: reitProfile,
    real_estate: realEstateProfile,

    // Healthcare
    biotech: biotechProfile,
    pharma: pharmaProfile,
    medical_devices: medicalDevicesProfile,
    healthcare_services: healthcareServicesProfile,

    // Consumer
    retail: retailProfile,
    ecommerce: ecommerceProfile,
    restaurants: restaurantsProfile,
    consumer_products: consumerProductsProfile,
    beverages: beveragesProfile,
    apparel: apparelProfile,
    auto: autoProfile,

    // Industrial & Services
    aerospace: aerospaceProfile,
    industrial: industrialProfile,
    construction: constructionProfile,
    transportation: transportationProfile,
    media: mediaProfile,
    gaming: gamingProfile,
    travel: travelProfile,
    education: educationProfile,
    conglomerate: conglomerateProfile,

    // Energy & Materials
    oil_gas: oilGasProfile,
    mining: miningProfile,
    utilities: utilitiesProfile,
    chemicals: chemicalsProfile,

    // Default
    general: generalProfile,
};

