'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { KeysSection } from './api-portal/KeysSection';
import { StreamSection } from './api-portal/StreamSection';
import { UsageSection } from './api-portal/UsageSection';

type TabId = 'keys' | 'stream' | 'usage';

const TABS: { id: TabId; label: string }[] = [
  { id: 'keys',   label: 'KEYS'   },
  { id: 'stream', label: 'STREAM' },
  { id: 'usage',  label: 'USAGE'  },
];

export function APIContent() {
  const [activeTab, setActiveTab] = useState<TabId>('keys');

  return (
    <div className="flex flex-col h-full">

      {/* Header */}
      <div className="px-2 py-1.5 border-b border-border flex-shrink-0">
        <div className="text-[9px] text-muted-foreground/40 tracking-wider">
          TRADEUL · DEVELOPER ACCESS · BREAKING NEWS STREAM
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border px-1 flex-shrink-0">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'px-2.5 py-[5px] text-[9px] font-medium tracking-wider border-b border-transparent',
              'transition-colors -mb-px',
              activeTab === tab.id
                ? 'text-foreground border-foreground/50'
                : 'text-muted-foreground/60 hover:text-muted-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {activeTab === 'keys'   && <KeysSection />}
        {activeTab === 'stream' && <StreamSection />}
        {activeTab === 'usage'  && <UsageSection />}
      </div>
    </div>
  );
}
