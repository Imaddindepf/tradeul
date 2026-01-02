'use client';

import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import { useUserPreferencesStore, selectFont } from '@/stores/useUserPreferencesStore';

// Transaction code definitions
const GLOSSARY = {
  transaction_codes: [
    { id: 'P', name: 'P - Purchase', desc: 'Open market purchase. Insider bought shares with their own money. Strong bullish signal when done by executives.' },
    { id: 'S', name: 'S - Sale', desc: 'Open market sale. Insider sold shares on the market. May indicate insider believes stock is overvalued, but can also be for diversification or personal needs.' },
    { id: 'A', name: 'A - Award/Grant', desc: 'Stock award or grant. Shares received as compensation (RSUs, stock bonuses, dividend equivalents). Neutral signal - automatic, not a personal investment decision. Note: fractional shares (e.g., 44.329) are common with dividend equivalents.' },
    { id: 'M', name: 'M - Exercise', desc: 'Option exercise. Insider exercised stock options. Often followed by immediate sale (M+S pattern) to cover taxes. Neutral unless held.' },
    { id: 'F', name: 'F - Tax Withholding', desc: 'Tax payment. Shares sold/withheld to cover tax liability on vested RSUs or exercised options. Neutral - automatic, not discretionary.' },
    { id: 'G', name: 'G - Gift', desc: 'Bona fide gift. Shares given to charity, family, or trust. Neutral - often for tax planning, not a view on stock value.' },
    { id: 'J', name: 'J - Other', desc: 'Other acquisition or disposition. Includes transfers between accounts, distributions from LLCs/trusts, inheritance. Neutral - administrative.' },
    { id: 'C', name: 'C - Conversion', desc: 'Conversion of derivative security. Converting options, warrants, or convertible securities into common stock. Neutral.' },
    { id: 'W', name: 'W - Inheritance', desc: 'Acquisition by will or laws of descent. Shares received through inheritance. Neutral.' },
    { id: 'D', name: 'D - Return to Issuer', desc: 'Disposition to issuer. Shares returned to company (forfeiture, buyback). Neutral.' },
    { id: 'E', name: 'E - Expiration', desc: 'Expiration of derivative. Options/warrants that expired worthless. Neutral.' },
    { id: 'I', name: 'I - Discretionary', desc: 'Discretionary transaction by trustee. Made by a third party under a trust agreement. Neutral.' },
    { id: 'L', name: 'L - Small Acquisition', desc: 'Small acquisition under Rule 16a-6. Very small transactions exempt from immediate reporting. Neutral.' },
  ],
  insider_types: [
    { id: 'ceo', name: 'CEO/President', desc: 'Chief Executive Officer. Most significant signal when buying - has deepest knowledge of company operations and future.' },
    { id: 'cfo', name: 'CFO', desc: 'Chief Financial Officer. Strong signal - knows financial health, cash flow, and potential issues before public disclosure.' },
    { id: 'director', name: 'Director', desc: 'Board member. Moderate signal - has strategic oversight but less operational detail than executives.' },
    { id: '10percent', name: '10% Owner', desc: 'Owns >10% of shares. Mixed signal - may be activist investor, founder, or institutional holder with different motivations.' },
    { id: 'officer', name: 'Other Officer', desc: 'VP, General Counsel, etc. Moderate signal - has inside knowledge but may have narrower view than CEO/CFO.' },
  ],
  signals: [
    { id: 'cluster', name: 'Cluster Buying', desc: 'Multiple insiders buying within short period (7-14 days). Very bullish - suggests broad internal confidence.' },
    { id: 'ceo_buy', name: 'CEO Purchase', desc: 'CEO buying with own money in open market. Strongest bullish signal - CEO puts personal capital at risk.' },
    { id: 'large_buy', name: 'Large Purchase', desc: 'Purchase >$500K or significant % of salary. More meaningful than token buys - shows real conviction.' },
    { id: 'cluster_sell', name: 'Cluster Selling', desc: 'Multiple insiders selling simultaneously. Bearish signal - may indicate shared concern about future.' },
    { id: 'insider_ratio', name: 'Buy/Sell Ratio', desc: 'Ratio of insider buys to sells over period. >1 = more buying, <1 = more selling. Context matters.' },
  ],
  form_types: [
    { id: 'form4', name: 'Form 4', desc: 'Statement of Changes. Must be filed within 2 business days of transaction. Primary source for insider trading data.' },
    { id: 'form3', name: 'Form 3', desc: 'Initial Statement. Filed when someone becomes an insider. Shows initial holdings.' },
    { id: 'form5', name: 'Form 5', desc: 'Annual Statement. Reports transactions exempt from Form 4 or not previously reported.' },
    { id: '144', name: 'Form 144', desc: 'Notice of Proposed Sale. Filed when insider intends to sell restricted securities.' },
  ],
};

const CATEGORY_NAMES: Record<string, string> = {
  transaction_codes: 'Transaction Codes',
  insider_types: 'Insider Types',
  signals: 'Trading Signals',
  form_types: 'SEC Forms',
};

const CATEGORY_ORDER = ['transaction_codes', 'signals', 'insider_types', 'form_types'];

export function InsiderGlossaryContent() {
  const font = useUserPreferencesStore(selectFont);
  const [search, setSearch] = useState('');
  const [expandedCategory, setExpandedCategory] = useState<string | null>('transaction_codes');

  const filteredGlossary = useMemo(() => {
    if (!search.trim()) return GLOSSARY;
    
    const term = search.toLowerCase();
    const filtered: typeof GLOSSARY = {} as typeof GLOSSARY;
    
    Object.entries(GLOSSARY).forEach(([category, items]) => {
      const matches = items.filter(
        item => item.name.toLowerCase().includes(term) || 
               item.desc.toLowerCase().includes(term) ||
               item.id.toLowerCase().includes(term)
      );
      if (matches.length > 0) {
        filtered[category as keyof typeof GLOSSARY] = matches;
      }
    });
    
    return filtered;
  }, [search]);

  const getSignalColor = (id: string) => {
    if (['P', 'cluster', 'ceo_buy', 'large_buy'].includes(id)) return 'text-emerald-600';
    if (['S', 'cluster_sell'].includes(id)) return 'text-red-600';
    return 'text-slate-700';
  };

  return (
    <div 
      className="h-full flex flex-col bg-white text-slate-800 overflow-hidden"
      style={{ fontFamily: `var(--font-${font})` }}
    >
      {/* Search */}
      <div className="flex-shrink-0 p-2 border-b border-slate-100">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search terms..."
            className="w-full pl-7 pr-2 py-1 text-xs bg-slate-50 border border-slate-200 rounded focus:outline-none focus:border-slate-300"
            style={{ fontFamily: `var(--font-${font})` }}
          />
        </div>
      </div>

      {/* Categories */}
      <div className="flex-1 overflow-y-auto">
        {CATEGORY_ORDER.filter(cat => filteredGlossary[cat as keyof typeof GLOSSARY]).map((category) => {
          const items = filteredGlossary[category as keyof typeof GLOSSARY];
          if (!items) return null;
          
          return (
            <div key={category} className="border-b border-slate-100 last:border-0">
              <button
                onClick={() => setExpandedCategory(expandedCategory === category ? null : category)}
                className="w-full px-3 py-1.5 flex items-center justify-between hover:bg-slate-50 transition-colors"
              >
                <span className="text-[10px] font-medium text-slate-600 uppercase tracking-wide">
                  {CATEGORY_NAMES[category] || category}
                </span>
                <span className="text-[9px] text-slate-400">
                  {items.length}
                </span>
              </button>
              
              {expandedCategory === category && (
                <div className="px-3 pb-2 space-y-2">
                  {items.map((item) => (
                    <div key={item.id} className="py-1 border-l-2 border-slate-200 pl-2">
                      <div className={`text-[10px] font-semibold ${getSignalColor(item.id)}`}>
                        {item.name}
                      </div>
                      <div className="text-[9px] text-slate-500 leading-tight mt-0.5">
                        {item.desc}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Key */}
      <div className="flex-shrink-0 px-3 py-2 border-t border-slate-100 bg-slate-50">
        <div className="flex items-center justify-center gap-4 text-[8px]">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span className="text-slate-500">Bullish Signal</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-500"></span>
            <span className="text-slate-500">Bearish Signal</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-slate-300"></span>
            <span className="text-slate-500">Neutral</span>
          </span>
        </div>
      </div>
    </div>
  );
}

