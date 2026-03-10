/**
 * SEC Filings Utilities
 * Sistema completo de categorización y tags para SEC forms
 */

export interface Filing {
  id: number;
  filing_type: string;
  filing_date: string;
  report_date?: string;
  title: string;
  category: string;
  is_offering_related: boolean;
  is_dilutive: boolean;
  url?: string;
}

export interface FilingTag {
  label: string;
  color: string;
  priority: number;
}

export interface FilingCategory {
  name: string;
  key: string;
  description: string;
  filings: Filing[];
}

/**
 * Sistema completo de tags para identificar tipos de SEC filings
 */
export function getFilingTags(filing: Filing): FilingTag[] {
  const type = (filing.filing_type || '').toUpperCase().trim();
  const title = (filing.title || '').toLowerCase();
  const tags: FilingTag[] = [];

  // === TAGS PRINCIPALES (Categoría del Form) ===
  
  // Financial Reports
  if (type.includes("10-K") || type === "20-F" || type === "40-F") {
    tags.push({ label: "Annual Report", color: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30", priority: 1 });
  } else if (type.includes("10-Q") || type === "6-K") {
    tags.push({ label: "Quarterly Report", color: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30", priority: 1 });
  }
  
  // Current Events
  else if (type === "8-K") {
    tags.push({ label: "Current Event", color: "bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/30", priority: 1 });
  }
  
  // Ownership & Insider Trading
  else if (type === "3") {
    tags.push({ label: "Initial Ownership", color: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/30", priority: 1 });
  } else if (type === "4") {
    tags.push({ label: "Insider Trade", color: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/30", priority: 1 });
  } else if (type === "5") {
    tags.push({ label: "Annual Ownership", color: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/30", priority: 1 });
  } else if (type.includes("13G")) {
    tags.push({ label: "Ownership >5%", color: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/30", priority: 1 });
  } else if (type.includes("13D")) {
    tags.push({ label: "Activist >5%", color: "bg-green-600 text-white border-green-700", priority: 1 });
  }
  
  // Proxy Materials
  else if (type.includes("DEF14A")) {
    tags.push({ label: "Definitive Proxy", color: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30", priority: 1 });
  } else if (type.includes("PRE14A")) {
    tags.push({ label: "Preliminary Proxy", color: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30", priority: 1 });
  } else if (type.includes("DEFA14A")) {
    tags.push({ label: "Additional Proxy", color: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30", priority: 1 });
  } else if (type.includes("DEFM14A") || type.includes("PREM14A")) {
    tags.push({ label: "Merger Proxy", color: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/40", priority: 1 });
  }
  
  // Registration Statements
  else if (type.includes("S-1")) {
    tags.push({ label: "IPO Registration", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("S-3")) {
    tags.push({ label: "Shelf Registration", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("S-4")) {
    tags.push({ label: "Merger Registration", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("S-8")) {
    tags.push({ label: "Employee Plan", color: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/30", priority: 1 });
  } else if (type.includes("S-11")) {
    tags.push({ label: "REIT Registration", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  }
  
  // Prospectus
  else if (type.includes("424B1")) {
    tags.push({ label: "Prospectus (Rule 424b1)", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("424B2")) {
    tags.push({ label: "Prospectus (Rule 424b2)", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("424B3")) {
    tags.push({ label: "Prospectus (Rule 424b3)", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("424B4")) {
    tags.push({ label: "Prospectus (Rule 424b4)", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type.includes("424B5")) {
    tags.push({ label: "Prospectus (Rule 424b5)", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  } else if (type === "FWP") {
    tags.push({ label: "Free Writing Prospectus", color: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30", priority: 1 });
  }
  
  // Special Forms
  else if (type.includes("SC TO")) {
    tags.push({ label: "Tender Offer", color: "bg-pink-500/10 text-pink-700 dark:text-pink-400 border-pink-500/30", priority: 1 });
  } else if (type.includes("SC 13E")) {
    tags.push({ label: "Issuer Tender", color: "bg-pink-500/10 text-pink-700 dark:text-pink-400 border-pink-500/30", priority: 1 });
  } else if (type.includes("NT 10")) {
    tags.push({ label: "Late Filing Notice", color: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30", priority: 1 });
  } else if (type === "11-K") {
    tags.push({ label: "Employee Plan Report", color: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/30", priority: 1 });
  } else if (type === "CORRESP") {
    tags.push({ label: "SEC Correspondence", color: "bg-surface-hover text-foreground/80 border-border", priority: 1 });
  } else if (type === "EFFECT") {
    tags.push({ label: "Notice of Effectiveness", color: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 border-indigo-500/30", priority: 1 });
  } else if (type.includes("POS")) {
    tags.push({ label: "Post-Effective Amendment", color: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 border-indigo-500/30", priority: 1 });
  } else if (type === "ARS") {
    tags.push({ label: "Annual Report to Shareholders", color: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30", priority: 1 });
  }

  // === TAGS SECUNDARIOS (Contexto específico) ===
  
  // Dilutive Activity
  if (filing.is_dilutive || type.includes("S-3") || type.includes("S-1") || 
      title.includes("shelf") || title.includes("atm") || title.includes("at-the-market") ||
      title.includes("offering") || title.includes("public offering")) {
    tags.push({ label: "Dilutive", color: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30", priority: 2 });
  }
  
  // M&A Activity
  if (title.includes("acquisition") || title.includes("merger") || 
      title.includes("combination") || type === "DEFM14A" || type === "PREM14A" ||
      type === "S-4") {
    tags.push({ label: "M&A", color: "bg-violet-500/10 text-violet-700 dark:text-violet-400 border-violet-500/30", priority: 3 });
  }
  
  // Employee Compensation
  if (title.includes("employee") || title.includes("stock option") || 
      title.includes("equity incentive") || title.includes("compensation plan") ||
      type === "S-8" || type === "11-K") {
    tags.push({ label: "Employee Comp", color: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/30", priority: 3 });
  }
  
  // Financial Distress
  if (title.includes("bankruptcy") || title.includes("chapter 11") || 
      title.includes("chapter 7") || title.includes("restructuring") ||
      title.includes("going concern") || title.includes("delisting")) {
    tags.push({ label: "Financial Distress", color: "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/40", priority: 2 });
  }
  
  // Dividends
  if (title.includes("dividend") || title.includes("distribution") || 
      title.includes("special dividend")) {
    tags.push({ label: "Dividend", color: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30", priority: 3 });
  }
  
  // Share Buyback
  if (title.includes("buyback") || title.includes("repurchase") || 
      title.includes("share repurchase program")) {
    tags.push({ label: "Buyback", color: "bg-teal-500/10 text-teal-700 dark:text-teal-400 border-teal-500/30", priority: 3 });
  }
  
  // Management Changes
  if (title.includes("departure") || title.includes("resignation") || 
      title.includes("appointment") || title.includes("director") ||
      title.includes("officer") || title.includes("ceo") || title.includes("cfo")) {
    tags.push({ label: "Management Change", color: "bg-sky-500/10 text-sky-700 dark:text-sky-400 border-sky-500/30", priority: 3 });
  }
  
  // Material Agreement
  if (title.includes("material agreement") || title.includes("material definitive") ||
      title.includes("credit agreement") || title.includes("loan agreement")) {
    tags.push({ label: "Material Agreement", color: "bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 border-indigo-500/30", priority: 3 });
  }
  
  // Amendments
  if (type.includes("/A") || title.includes("amendment") || title.includes("amend")) {
    tags.push({ label: "Amendment", color: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/30", priority: 4 });
  }

  return tags.sort((a, b) => a.priority - b.priority);
}

/**
 * Categorizar filings en grupos organizados
 */
export function categorizeFilings(filings: Filing[]): FilingCategory[] {
  const categories: Record<string, Filing[]> = {
    disclosures: [],
    financials: [],
    ownership: [],
    proxy: [],
    prospectus: [],
    other: [],
  };

  filings.forEach((filing) => {
    const type = filing.filing_type.toUpperCase();
    
    if (type === "8-K") {
      categories.disclosures.push(filing);
    } else if (type.includes("10-Q") || type.includes("10-K") || type === "ARS" || 
               type === "20-F" || type === "40-F" || type === "6-K" || 
               type.includes("NT 10")) {
      categories.financials.push(filing);
    } else if (type === "3" || type === "4" || type === "5" || 
               type.includes("13G") || type.includes("13D") || 
               type.includes("13F")) {
      categories.ownership.push(filing);
    } else if (type.includes("DEF") || type.includes("PRE") || 
               type.includes("DEFA") || type.includes("PREM")) {
      categories.proxy.push(filing);
    } else if (type.includes("S-") || type.includes("424B") || 
               type === "FWP" || type === "EFFECT" || 
               type.includes("POS") || type.includes("SC TO")) {
      categories.prospectus.push(filing);
    } else {
      categories.other.push(filing);
    }
  });

  return [
    { 
      name: "Disclosures", 
      key: "disclosures", 
      description: "Current events and material changes (8-K)",
      filings: categories.disclosures 
    },
    { 
      name: "Financials", 
      key: "financials", 
      description: "Quarterly and annual financial reports",
      filings: categories.financials 
    },
    { 
      name: "Ownership", 
      key: "ownership", 
      description: "Insider trading and beneficial ownership",
      filings: categories.ownership 
    },
    { 
      name: "Proxy", 
      key: "proxy", 
      description: "Shareholder meeting materials",
      filings: categories.proxy 
    },
    { 
      name: "Prospectus", 
      key: "prospectus", 
      description: "Securities offerings and registrations",
      filings: categories.prospectus 
    },
    { 
      name: "Other", 
      key: "other", 
      description: "Correspondence and miscellaneous",
      filings: categories.other 
    },
  ].filter(cat => cat.filings.length > 0);
}

/**
 * Obtener descripción de un tipo de filing
 */
export function getFilingTypeDescription(filingType: string): string {
  const type = filingType.toUpperCase().trim();
  
  const descriptions: Record<string, string> = {
    // Financial Reports
    "10-K": "Annual report with audited financials",
    "10-Q": "Quarterly report with unaudited financials",
    "8-K": "Current report of material events",
    "20-F": "Annual report for foreign private issuers",
    "40-F": "Annual report for Canadian issuers",
    "6-K": "Current report for foreign private issuers",
    
    // Ownership
    "3": "Initial statement of beneficial ownership",
    "4": "Statement of changes in beneficial ownership",
    "5": "Annual statement of beneficial ownership",
    "13D": "Schedule 13D - Activist ownership disclosure",
    "13G": "Schedule 13G - Passive ownership disclosure",
    "13F": "Institutional investment manager holdings",
    
    // Proxy
    "DEF14A": "Definitive proxy statement",
    "PRE14A": "Preliminary proxy statement",
    "DEFA14A": "Additional proxy soliciting materials",
    "DEFM14A": "Definitive proxy - merger or acquisition",
    
    // Registration
    "S-1": "Registration statement for IPO",
    "S-3": "Shelf registration for seasoned issuers",
    "S-4": "Registration for business combinations",
    "S-8": "Registration for employee benefit plans",
    "424B5": "Prospectus filed pursuant to Rule 424(b)(5)",
    "FWP": "Free writing prospectus",
    
    // Special
    "SC TO": "Tender offer statement",
    "NT 10-K": "Notice of inability to timely file Form 10-K",
    "NT 10-Q": "Notice of inability to timely file Form 10-Q",
    "11-K": "Annual report of employee stock purchase plans",
    "EFFECT": "Notice of effectiveness",
    "CORRESP": "Correspondence with SEC",
  };
  
  return descriptions[type] || "SEC filing";
}

