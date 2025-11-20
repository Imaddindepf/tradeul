'use client';

import { Clock, TrendingUp, Moon, Sun, Circle } from 'lucide-react';

export interface MarketStatus {
  market: 'open' | 'closed' | 'extended-hours';
  earlyHours: boolean;
  afterHours: boolean;
  exchanges?: {
    nasdaq?: string;
    nyse?: string;
    otc?: string;
  };
  serverTime?: string;
}

interface MarketStatusBadgeProps {
  status: MarketStatus | null;
  compact?: boolean;
}

export function MarketStatusBadge({ status, compact = false }: MarketStatusBadgeProps) {
  if (!status) return null;

  // Determinar el estado visual basado en la data del API
  const getMarketState = () => {
    if (status.market === 'open') {
      return {
        label: 'OPEN',
        sublabel: 'Market Open',
        icon: TrendingUp,
        bgColor: 'bg-green-100',
        textColor: 'text-green-700',
        borderColor: 'border-green-400',
        dotColor: 'bg-green-500',
        animate: true,
      };
    } else if (status.market === 'extended-hours') {
      if (status.earlyHours) {
        return {
          label: 'PRE',
          sublabel: 'Pre-Market',
          icon: Sun,
          bgColor: 'bg-blue-100',
          textColor: 'text-blue-700',
          borderColor: 'border-blue-400',
          dotColor: 'bg-blue-500',
          animate: true,
        };
      } else if (status.afterHours) {
        return {
          label: 'POST',
          sublabel: 'After Hours',
          icon: Moon,
          bgColor: 'bg-orange-100',
          textColor: 'text-orange-700',
          borderColor: 'border-orange-400',
          dotColor: 'bg-orange-500',
          animate: true,
        };
      }
      return {
        label: 'EXT',
        sublabel: 'Extended Hours',
        icon: Clock,
        bgColor: 'bg-purple-100',
        textColor: 'text-purple-700',
        borderColor: 'border-purple-400',
        dotColor: 'bg-purple-500',
        animate: true,
      };
    } else {
      return {
        label: 'CLOSED',
        sublabel: 'Market Closed',
        icon: Circle,
        bgColor: 'bg-gray-100',
        textColor: 'text-gray-700',
        borderColor: 'border-gray-300',
        dotColor: 'bg-gray-500',
        animate: false,
      };
    }
  };

  const state = getMarketState();
  const Icon = state.icon;

  // Formato compacto para espacios reducidos
  if (compact) {
    return (
      <div 
        className={`
          inline-flex items-center gap-2 px-3 py-1.5 rounded-lg
          border ${state.borderColor} ${state.bgColor}
          transition-all duration-300
        `}
        title={`${state.sublabel} • NYSE: ${status.exchanges?.nyse || 'N/A'} • NASDAQ: ${status.exchanges?.nasdaq || 'N/A'}`}
      >
        {/* Dot animado */}
        {state.animate && (
          <span className="relative flex h-2 w-2">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${state.dotColor} opacity-75`}></span>
            <span className={`relative inline-flex rounded-full h-2 w-2 ${state.dotColor}`}></span>
          </span>
        )}
        {!state.animate && (
          <span className={`inline-flex rounded-full h-2 w-2 ${state.dotColor}`}></span>
        )}
        
        {/* Label */}
        <span className={`text-sm font-bold ${state.textColor}`}>
          {state.label}
        </span>
      </div>
    );
  }

  // Formato completo con más información
  return (
    <div 
      className={`
        inline-flex items-center gap-3 px-4 py-2 rounded-lg
        border ${state.borderColor} ${state.bgColor}
        transition-all duration-300
      `}
    >
      {/* Icon */}
      <Icon className={`h-4 w-4 ${state.textColor}`} />
      
      {/* Status info */}
      <div className="flex flex-col">
        <span className={`text-sm font-bold ${state.textColor} leading-none`}>
          {state.label}
        </span>
        <span className={`text-xs ${state.textColor} opacity-75 leading-none mt-0.5`}>
          {state.sublabel}
        </span>
      </div>

      {/* Dot animado */}
      {state.animate && (
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${state.dotColor} opacity-75`}></span>
          <span className={`relative inline-flex rounded-full h-2 w-2 ${state.dotColor}`}></span>
        </span>
      )}
      {!state.animate && (
        <span className={`inline-flex rounded-full h-2 w-2 ${state.dotColor}`}></span>
      )}

      {/* Exchange status (tooltip on hover) */}
      {status.exchanges && (
        <div className={`hidden lg:flex items-center gap-1 text-xs ${state.textColor} opacity-60`}>
          <span className="font-mono">NYSE</span>
          <span className={`w-1.5 h-1.5 rounded-full ${
            status.exchanges.nyse === 'open' ? 'bg-green-500' :
            status.exchanges.nyse === 'extended-hours' ? 'bg-orange-500' :
            'bg-gray-400'
          }`}></span>
          <span className="mx-1">•</span>
          <span className="font-mono">NSDQ</span>
          <span className={`w-1.5 h-1.5 rounded-full ${
            status.exchanges.nasdaq === 'open' ? 'bg-green-500' :
            status.exchanges.nasdaq === 'extended-hours' ? 'bg-orange-500' :
            'bg-gray-400'
          }`}></span>
        </div>
      )}
    </div>
  );
}

