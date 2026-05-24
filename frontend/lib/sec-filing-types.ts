/**
 * SEC EDGAR Filing Types - Trading-oriented metadata
 * Optimized for detecting market-moving events
 */

// ============================================================================
// CATEGORIES - 6 essential groups for traders
// ============================================================================

export const FILING_CATEGORIES = {
  offerings: {
    label: 'Offerings',
    description: 'IPOs, shelf registrations, prospectuses, ATMs',
    types: [
      // Registration statements
      'S-1', 'S-1/A', 'S-1MEF',
      'S-3', 'S-3/A', 'S-3ASR', 'S-3MEF', 'S-3D',
      'F-1', 'F-1/A', 'F-3', 'F-3ASR',
      // Prospectuses
      '424B1', '424B2', '424B3', '424B4', '424B5', '424B7', '424B8',
      // Other offering docs
      'FWP', 'POS AM', 'EFFECT',
      // Reg A
      '1-A', '1-A POS',
      // Private placements
      'D', 'D/A',
    ],
  },
  insider: {
    label: 'Insider',
    description: 'Executive transactions, Form 144 sales',
    types: ['3', '4', '5', '144'],
  },
  institutional: {
    label: 'Institutional',
    description: 'Activist 13D, passive 13G, fund holdings 13F',
    types: [
      'SC 13D', 'SC 13D/A',
      'SC 13G', 'SC 13G/A',
      '13F-HR', '13F-NT',
    ],
  },
  material: {
    label: '8-K Events',
    description: 'Material events, earnings, management changes',
    types: ['8-K', '8-K/A', '6-K', '6-K/A'],
  },
  mna: {
    label: 'M&A',
    description: 'Mergers, tender offers, going private',
    types: [
      'S-4', 'S-4/A', 'F-4', 'F-4/A',
      '425',
      'SC TO-T', 'SC TO-I', 'SC TO-C',
      'SC 14D9', 'SC 14D9/A',
      'SC 13E3',
      'DEFM14A',
    ],
  },
  distress: {
    label: 'Distress',
    description: 'Late filings, delisting, registration termination',
    types: [
      'NT 10-K', 'NT 10-Q', 'NT 20-F',
      '15-12B', '15-12G', '15-15D',
      '25-NSE',
      'RW',
    ],
  },
} as const;

// ============================================================================
// QUICK FILTERS - One-click presets for common use cases
// ============================================================================

export const QUICK_FILTERS = {
  offerings: {
    label: 'Offerings',
    categories: ['offerings'],
    items8K: [],
    description: 'All dilution-related filings',
  },
  insider: {
    label: 'Insider',
    categories: ['insider'],
    items8K: [],
    description: 'Form 3/4/5 transactions',
  },
  institutional: {
    label: '13D/13F',
    categories: ['institutional'],
    items8K: [],
    description: 'Activist and institutional holdings',
  },
  critical8K: {
    label: '8-K Critical',
    categories: [],
    items8K: ['1.03', '2.02', '2.04', '2.06', '3.01', '4.02', '5.01'],
    description: 'Bankruptcy, earnings, default, impairment, delisting, restatement, control change',
  },
  mna: {
    label: 'M&A',
    categories: ['mna'],
    items8K: [],
    description: 'Mergers and tender offers',
  },
  distress: {
    label: 'Distress',
    categories: ['distress'],
    items8K: ['1.03', '2.04', '3.01'],
    description: 'Late filings, delisting, bankruptcy',
  },
} as const;

// ============================================================================
// 8-K ITEMS - Grouped by trading relevance
// ============================================================================

export const EIGHT_K_GROUPS = {
  earnings: {
    label: 'Earnings',
    items: ['2.02'],
    description: 'Results of operations',
  },
  dilution: {
    label: 'Dilution',
    items: ['3.02', '2.03'],
    description: 'Unregistered sales, new debt',
  },
  management: {
    label: 'Management',
    items: ['5.01', '5.02'],
    description: 'Control change, exec departure',
  },
  distress: {
    label: 'Distress',
    items: ['1.03', '2.04', '2.06', '3.01', '4.02'],
    description: 'Bankruptcy, default, impairment, delisting, restatement',
  },
  deals: {
    label: 'Deals',
    items: ['1.01', '1.02', '2.01'],
    description: 'Material agreements, acquisitions',
  },
  cyber: {
    label: 'Cyber',
    items: ['1.05'],
    description: 'Security incidents',
  },
} as const;

export const FORM_8K_ITEMS: Record<string, { description: string; importance: 'critical' | 'high' | 'medium' | 'low' }> = {
  '1.01': { description: 'Material Agreement', importance: 'high' },
  '1.02': { description: 'Agreement Termination', importance: 'high' },
  '1.03': { description: 'Bankruptcy', importance: 'critical' },
  '1.04': { description: 'Mine Safety', importance: 'low' },
  '1.05': { description: 'Cybersecurity Incident', importance: 'critical' },
  '2.01': { description: 'Asset Acquisition/Disposition', importance: 'high' },
  '2.02': { description: 'Earnings', importance: 'critical' },
  '2.03': { description: 'New Debt', importance: 'high' },
  '2.04': { description: 'Debt Default', importance: 'critical' },
  '2.05': { description: 'Restructuring', importance: 'high' },
  '2.06': { description: 'Impairment', importance: 'critical' },
  '3.01': { description: 'Delisting Notice', importance: 'critical' },
  '3.02': { description: 'Unregistered Sale', importance: 'high' },
  '3.03': { description: 'Rights Modified', importance: 'medium' },
  '4.01': { description: 'Auditor Change', importance: 'high' },
  '4.02': { description: 'Restatement', importance: 'critical' },
  '5.01': { description: 'Control Change', importance: 'critical' },
  '5.02': { description: 'Officer/Director Change', importance: 'high' },
  '5.03': { description: 'Bylaws Change', importance: 'medium' },
  '5.07': { description: 'Vote Results', importance: 'medium' },
  '7.01': { description: 'Reg FD Disclosure', importance: 'medium' },
  '8.01': { description: 'Other Events', importance: 'low' },
  '9.01': { description: 'Exhibits', importance: 'low' },
};

// ============================================================================
// FORM TYPE INFO - Descriptions for tooltips
// ============================================================================

export const FORM_TYPE_INFO: Record<string, { description: string; importance: 'high' | 'medium' | 'low' }> = {
  // Offerings
  'S-1': { description: 'IPO Registration', importance: 'high' },
  'S-1/A': { description: 'IPO Amendment', importance: 'high' },
  'S-3': { description: 'Shelf Registration', importance: 'high' },
  'S-3ASR': { description: 'Auto Shelf Registration', importance: 'high' },
  'F-1': { description: 'Foreign IPO', importance: 'high' },
  'F-3': { description: 'Foreign Shelf', importance: 'high' },
  '424B1': { description: 'Final Prospectus', importance: 'high' },
  '424B2': { description: 'Prospectus Supplement', importance: 'high' },
  '424B3': { description: 'Prospectus Update', importance: 'medium' },
  '424B4': { description: 'IPO Prospectus', importance: 'high' },
  '424B5': { description: 'Follow-on Prospectus', importance: 'high' },
  'FWP': { description: 'Free Writing Prospectus', importance: 'high' },
  'EFFECT': { description: 'Registration Effective', importance: 'high' },
  'POS AM': { description: 'Post-Effective Amendment', importance: 'medium' },
  'D': { description: 'Private Placement', importance: 'medium' },
  '1-A': { description: 'Reg A Offering', importance: 'high' },
  
  // Insider
  '3': { description: 'Initial Ownership', importance: 'medium' },
  '4': { description: 'Insider Transaction', importance: 'high' },
  '5': { description: 'Annual Ownership', importance: 'low' },
  '144': { description: 'Restricted Stock Sale', importance: 'medium' },
  
  // Institutional
  'SC 13D': { description: 'Activist >5%', importance: 'high' },
  'SC 13D/A': { description: 'Activist Amendment', importance: 'high' },
  'SC 13G': { description: 'Passive >5%', importance: 'medium' },
  'SC 13G/A': { description: 'Passive Amendment', importance: 'medium' },
  '13F-HR': { description: 'Fund Holdings', importance: 'medium' },
  
  // Material Events
  '8-K': { description: 'Material Event', importance: 'high' },
  '8-K/A': { description: 'Amended 8-K', importance: 'medium' },
  '6-K': { description: 'Foreign Report', importance: 'medium' },
  '10-K': { description: 'Annual Report', importance: 'high' },
  '10-Q': { description: 'Quarterly Report', importance: 'high' },
  '20-F': { description: 'Foreign Annual', importance: 'high' },
  
  // M&A
  'S-4': { description: 'M&A Registration', importance: 'high' },
  'F-4': { description: 'Foreign M&A Reg', importance: 'high' },
  '425': { description: 'Merger Communication', importance: 'medium' },
  'SC TO-T': { description: 'Tender Offer', importance: 'high' },
  'SC TO-I': { description: 'Issuer Tender', importance: 'high' },
  'SC 14D9': { description: 'Tender Response', importance: 'high' },
  'DEFM14A': { description: 'Merger Proxy', importance: 'high' },
  'SC 13E3': { description: 'Going Private', importance: 'high' },
  
  // Distress
  'NT 10-K': { description: 'Late Annual', importance: 'high' },
  'NT 10-Q': { description: 'Late Quarterly', importance: 'high' },
  '25-NSE': { description: 'Delisting', importance: 'high' },
  'RW': { description: 'Registration Withdrawal', importance: 'medium' },
  
  // Proxy
  'DEF 14A': { description: 'Proxy Statement', importance: 'medium' },
  'PRE 14A': { description: 'Preliminary Proxy', importance: 'low' },
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

export function getFormTypeColor(formType: string): string {
  // Check each category and return appropriate color
  for (const [key, category] of Object.entries(FILING_CATEGORIES)) {
    if (category.types.some(t => formType === t || formType.startsWith(t + '/'))) {
      switch (key) {
        case 'offerings': return 'rose';
        case 'insider': return 'amber';
        case 'institutional': return 'emerald';
        case 'material': return 'blue';
        case 'mna': return 'purple';
        case 'distress': return 'red';
        default: return 'slate';
      }
    }
  }
  return 'slate';
}

export function get8KItemImportance(items: string[] | null): 'critical' | 'high' | 'medium' | 'low' | null {
  if (!items || items.length === 0) return null;
  
  let highest: 'critical' | 'high' | 'medium' | 'low' = 'low';
  const priority = { critical: 4, high: 3, medium: 2, low: 1 };
  
  for (const item of items) {
    const match = item.match(/Item\s+(\d+\.\d+)/i);
    if (match) {
      const itemInfo = FORM_8K_ITEMS[match[1]];
      if (itemInfo && priority[itemInfo.importance] > priority[highest]) {
        highest = itemInfo.importance;
      }
    }
  }
  
  return highest;
}

export function format8KItems(items: string[] | null): string {
  if (!items || items.length === 0) return '';
  
  return items
    .map(item => {
      const match = item.match(/Item\s+(\d+\.\d+)/i);
      return match ? match[1] : null;
    })
    .filter(Boolean)
    .join(', ');
}

// Get all form types for a quick filter
export function getQuickFilterTypes(filterKey: keyof typeof QUICK_FILTERS): string[] {
  const filter = QUICK_FILTERS[filterKey];
  const types: string[] = [];
  
  filter.categories.forEach(catKey => {
    const cat = FILING_CATEGORIES[catKey as keyof typeof FILING_CATEGORIES];
    if (cat) types.push(...cat.types);
  });
  
  return [...new Set(types)];
}
