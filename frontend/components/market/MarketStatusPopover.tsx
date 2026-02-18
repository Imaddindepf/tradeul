'use client';

import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Circle } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { getUserTimezone } from '@/lib/date-utils';

// Tipo completo del response de Polygon
export interface PolygonMarketStatus {
  market: 'open' | 'closed' | 'extended-hours';
  serverTime: string;
  earlyHours: boolean;
  afterHours: boolean;
  exchanges?: {
    nasdaq?: string;
    nyse?: string;
    otc?: string;
  };
  currencies?: {
    crypto?: string;
    fx?: string;
  };
  indicesGroups?: {
    s_and_p?: string;
    societe_generale?: string;
    msci?: string;
    ftse_russell?: string;
    mstar?: string;
    mstarc?: string;
    nasdaq?: string;
    dow_jones?: string;
    cccy?: string;
    cgi?: string;
  };
}

interface MarketStatusPopoverProps {
  status: PolygonMarketStatus | null;
}

export function MarketStatusPopover({ status }: MarketStatusPopoverProps) {
  const [currentTime, setCurrentTime] = useState<Date | null>(null);
  const [showPopover, setShowPopover] = useState(false);
  const [popoverPosition, setPopoverPosition] = useState({ top: 0, right: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setCurrentTime(new Date());
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (showPopover && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPopoverPosition({
        top: rect.bottom + 4,
        right: window.innerWidth - rect.right,
      });
    }
  }, [showPopover]);

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      timeZone: getUserTimezone(),
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getMarketState = () => {
    if (!status) return { label: '···', color: 'text-slate-400', dot: 'bg-slate-300' };

    if (status.market === 'open') {
      return { label: 'OPEN', color: 'text-emerald-600', dot: 'bg-emerald-500' };
    } else if (status.market === 'extended-hours') {
      if (status.earlyHours) {
        return { label: 'PRE', color: 'text-blue-500', dot: 'bg-blue-400' };
      } else if (status.afterHours) {
        return { label: 'POST', color: 'text-amber-500', dot: 'bg-amber-400' };
      }
      return { label: 'EXT', color: 'text-purple-500', dot: 'bg-purple-400' };
    } else {
      return { label: 'CLOSED', color: 'text-slate-400', dot: 'bg-slate-300' };
    }
  };

  const marketState = getMarketState();

  const popoverContent = showPopover && status && mounted && (
    <div
      className="fixed w-64 bg-white/95 backdrop-blur-sm rounded-md shadow-lg border border-slate-100 p-2.5"
      style={{
        top: `${popoverPosition.top}px`,
        right: `${popoverPosition.right}px`,
        zIndex: Z_INDEX.NAVBAR_POPOVER,
      }}
      onMouseEnter={() => setShowPopover(true)}
      onMouseLeave={() => setShowPopover(false)}
    >
      {/* Header */}
      <div className="mb-2 pb-1.5 border-b border-slate-100">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Market Status</span>
          <span className={`text-[10px] font-bold ${marketState.color}`}>
            {marketState.label}
          </span>
        </div>
      </div>

      {/* US Stock Exchanges */}
      {status.exchanges && (
        <div className="mb-2">
          <h4 className="text-[9px] font-bold text-slate-400 mb-1 uppercase tracking-wider">
            US Exchanges
          </h4>
          <div className="space-y-0.5">
            <StatusItemCompact label="NYSE" status={status.exchanges.nyse} />
            <StatusItemCompact label="Nasdaq" status={status.exchanges.nasdaq} />
            <StatusItemCompact label="OTC" status={status.exchanges.otc} />
          </div>
        </div>
      )}

      {/* Currencies */}
      {status.currencies && (
        <div>
          <h4 className="text-[9px] font-bold text-slate-400 mb-1 uppercase tracking-wider">
            Currencies
          </h4>
          <div className="space-y-0.5">
            <StatusItemCompact label="Crypto" status={status.currencies.crypto} />
            <StatusItemCompact label="Forex" status={status.currencies.fx} />
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Trigger — flush with navbar, no border, no card look */}
      <div
        ref={triggerRef}
        className="flex items-center gap-2 px-2 py-1 cursor-pointer hover:bg-slate-50 rounded-sm transition-colors"
        onMouseEnter={() => setShowPopover(true)}
        onMouseLeave={() => setShowPopover(false)}
      >
        {/* Status dot */}
        <span className={`w-1.5 h-1.5 rounded-full ${marketState.dot}`} />

        {/* Time */}
        <span className="text-xs font-mono font-medium text-slate-700 leading-none tabular-nums">
          {currentTime ? formatTime(currentTime) : '--:--:--'}
        </span>

        {/* Market label */}
        <span className={`text-[9px] font-semibold uppercase tracking-wider ${marketState.color} leading-none`}>
          {marketState.label}
        </span>
      </div>

      {/* Popover */}
      {mounted && typeof document !== 'undefined' && popoverContent &&
        createPortal(popoverContent, document.getElementById('portal-root')!)}
    </>
  );
}

function StatusItemCompact({ label, status }: { label: string; status?: string }) {
  const getColor = (s?: string) => {
    switch (s) {
      case 'open': return 'text-emerald-600';
      case 'extended-hours': return 'text-amber-600';
      case 'closed': return 'text-slate-400';
      default: return 'text-slate-300';
    }
  };

  const getDot = (s?: string) => {
    switch (s) {
      case 'open': return 'bg-emerald-500';
      case 'extended-hours': return 'bg-amber-400';
      case 'closed': return 'bg-slate-300';
      default: return 'bg-slate-200';
    }
  };

  const getLabel = (s?: string) => {
    if (!s) return 'N/A';
    if (s === 'extended-hours') return 'Extended';
    if (s === 'open') return 'Open';
    if (s === 'closed') return 'Closed';
    return s;
  };

  return (
    <div className="flex items-center justify-between text-[10px] py-0.5">
      <span className="text-slate-600 font-medium">{label}</span>
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${getDot(status)}`} />
        <span className={`font-semibold ${getColor(status)} min-w-[48px] text-right`}>
          {getLabel(status)}
        </span>
      </div>
    </div>
  );
}
