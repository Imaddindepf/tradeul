'use client';

import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Clock, Circle } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';

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

  // Montar el componente e inicializar la hora solo en cliente
  useEffect(() => {
    setMounted(true);
    setCurrentTime(new Date());
  }, []);

  // Actualizar hora cada segundo
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Calcular posición del popover basado en el trigger
  useEffect(() => {
    if (showPopover && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      setPopoverPosition({
        top: rect.bottom + 8, // 8px debajo del trigger
        right: window.innerWidth - rect.right, // Alineado a la derecha del trigger
      });
    }
  }, [showPopover]);

  // Formato de hora: HH:MM:SS
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  // Formato de fecha: Day, Mon DD
  const formatDate = (date: Date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  // Función para obtener el color del status
  const getStatusColor = (statusValue?: string) => {
    switch (statusValue) {
      case 'open':
        return 'text-green-500';
      case 'extended-hours':
        return 'text-orange-500';
      case 'closed':
        return 'text-gray-500';
      default:
        return 'text-gray-400';
    }
  };

  // Función para obtener el dot de color
  const getStatusDot = (statusValue?: string) => {
    switch (statusValue) {
      case 'open':
        return 'bg-green-500';
      case 'extended-hours':
        return 'bg-orange-500';
      case 'closed':
        return 'bg-gray-500';
      default:
        return 'bg-gray-400';
    }
  };

  // Obtener el estado general del mercado
  const getMarketState = () => {
    if (!status) return { label: 'LOADING', color: 'text-gray-500' };

    if (status.market === 'open') {
      return { label: 'OPEN', color: 'text-green-500' };
    } else if (status.market === 'extended-hours') {
      if (status.earlyHours) {
        return { label: 'PRE-MARKET', color: 'text-blue-500' };
      } else if (status.afterHours) {
        return { label: 'POST-MARKET', color: 'text-orange-500' };
      }
      return { label: 'EXTENDED HOURS', color: 'text-purple-500' };
    } else {
      return { label: 'CLOSED', color: 'text-gray-500' };
    }
  };

  const marketState = getMarketState();

  const popoverContent = showPopover && status && mounted && (
    <div
      className="fixed w-72 bg-white rounded-lg shadow-2xl border border-slate-200 p-3"
      style={{
        top: `${popoverPosition.top}px`,
        right: `${popoverPosition.right}px`,
        zIndex: Z_INDEX.NAVBAR_POPOVER
      }}
      onMouseEnter={() => setShowPopover(true)}
      onMouseLeave={() => setShowPopover(false)}
    >
      {/* Header */}
      <div className="mb-3 pb-2 border-b border-slate-200">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-600">Market Status</span>
          <span className={`text-xs font-bold ${marketState.color}`}>
            {marketState.label}
          </span>
        </div>
      </div>

      {/* US Stock Exchanges */}
      {status.exchanges && (
        <div className="mb-3">
          <h4 className="text-[10px] font-bold text-slate-500 mb-1.5 uppercase tracking-wider">
            US Exchanges
          </h4>
          <div className="space-y-1">
            <StatusItemCompact label="NYSE" status={status.exchanges.nyse} />
            <StatusItemCompact label="Nasdaq" status={status.exchanges.nasdaq} />
            <StatusItemCompact label="OTC" status={status.exchanges.otc} />
          </div>
        </div>
      )}

      {/* Currencies */}
      {status.currencies && (
        <div>
          <h4 className="text-[10px] font-bold text-slate-500 mb-1.5 uppercase tracking-wider">
            Currencies
          </h4>
          <div className="space-y-1">
            <StatusItemCompact label="Crypto" status={status.currencies.crypto} />
            <StatusItemCompact label="Forex" status={status.currencies.fx} />
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Trigger - Hora del usuario */}
      <div
        ref={triggerRef}
        className="flex items-center gap-3 px-4 py-2 rounded-lg border border-slate-200 bg-white hover:border-blue-400 hover:shadow-md transition-all cursor-pointer"
        onMouseEnter={() => setShowPopover(true)}
        onMouseLeave={() => setShowPopover(false)}
      >
        <Clock className="h-4 w-4 text-slate-600" />
        <div className="flex flex-col">
          <span className="text-sm font-mono font-bold text-slate-900 leading-none">
            {currentTime ? formatTime(currentTime) : '--:--:--'}
          </span>
          <span className="text-xs text-slate-500 leading-none mt-0.5">
            {currentTime ? formatDate(currentTime) : '---'}
          </span>
        </div>
      </div>

      {/* Popover - Renderizado en portal */}
      {mounted && typeof document !== 'undefined' && popoverContent &&
        createPortal(popoverContent, document.getElementById('portal-root')!)}
    </>
  );
}

// Componente compacto para items
function StatusItemCompact({ label, status }: { label: string; status?: string }) {
  const getStatusColor = (statusValue?: string) => {
    switch (statusValue) {
      case 'open':
        return 'text-green-600';
      case 'extended-hours':
        return 'text-orange-600';
      case 'closed':
        return 'text-gray-500';
      default:
        return 'text-gray-400';
    }
  };

  const getStatusDot = (statusValue?: string) => {
    switch (statusValue) {
      case 'open':
        return 'bg-green-500';
      case 'extended-hours':
        return 'bg-orange-500';
      case 'closed':
        return 'bg-gray-400';
      default:
        return 'bg-gray-300';
    }
  };

  const getStatusLabel = (statusValue?: string) => {
    if (!statusValue) return 'N/A';
    if (statusValue === 'extended-hours') return 'Extended';
    if (statusValue === 'open') return 'Open';
    if (statusValue === 'closed') return 'Closed';
    return statusValue;
  };

  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-700 font-medium">{label}</span>
      <div className="flex items-center gap-1.5">
        <Circle className={`h-2 w-2 fill-current ${getStatusDot(status)}`} />
        <span className={`font-semibold ${getStatusColor(status)} min-w-[55px] text-right`}>
          {getStatusLabel(status)}
        </span>
      </div>
    </div>
  );
}

