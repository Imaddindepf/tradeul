'use client';

import { useEffect, useRef, useState, memo, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import type { CompanyMetadata, Ticker } from '@/lib/types';
import { getCompanyMetadata } from '@/lib/api';
import { formatNumber } from '@/lib/formatters';
import { FloatingWindowBase } from '@/components/ui/FloatingWindowBase';
import { floatingZIndexManager } from '@/lib/z-index';
import { useRxWebSocket } from '@/hooks/useRxWebSocket';

interface TickerMetadataModalProps {
  symbol: string | null;
  tickerData: Ticker | null;
  isOpen: boolean;
  onClose: () => void;
}

function TickerMetadataModal({ symbol, tickerData, isOpen, onClose }: TickerMetadataModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const [metadata, setMetadata] = useState<CompanyMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [descriptionExpanded, setDescriptionExpanded] = useState(false);

  // Estado en tiempo real del ticker
  const [livePrice, setLivePrice] = useState<number | null>(null);
  const [liveChangePercent, setLiveChangePercent] = useState<number | null>(null);

  // Obtener z-index alto para modales (DEBE estar antes de cualquier return condicional)
  const modalZIndex = useMemo(() => floatingZIndexManager.getNextModal(), []);

  // WebSocket para updates en tiempo real (SharedWorker compartido)
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:9000/ws/scanner';
  const ws = useRxWebSocket(wsUrl, false);

  // Helper para convertir URL de logo a proxy
  const getProxiedLogoUrl = (logoUrl: string | null | undefined): string | null => {
    if (!logoUrl) return null;
    // Usar proxy del API Gateway para agregar API key
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return `${apiUrl}/api/v1/proxy/logo?url=${encodeURIComponent(logoUrl)}`;
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen || !symbol) {
      // Limpiar estado cuando se cierra o no hay símbolo
      setMetadata(null);
      return;
    }

    let cancelled = false;
    // Limpiar datos anteriores inmediatamente al cambiar de ticker
    setMetadata(null);
    setLoading(true);
    setError(null);
    setDescriptionExpanded(false);

    getCompanyMetadata(symbol)
      .then((data) => {
        if (!cancelled) {
          setMetadata(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || 'Error al cargar metadatos');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, isOpen]);

  // Suscribirse a aggregates del WebSocket para updates en tiempo real
  useEffect(() => {
    if (!isOpen || !symbol || !ws.isConnected) return;
    
    const subscription = ws.aggregates$.subscribe({
      next: (message: any) => {
        // Solo actualizar si el aggregate es para este ticker
        if (message.symbol === symbol && message.data) {
          setLivePrice(message.data.c ?? message.data.close);
          // Recalcular change_percent si tenemos prev_close
          if (tickerData?.prev_close && message.data.c) {
            const change = ((message.data.c - tickerData.prev_close) / tickerData.prev_close) * 100;
            setLiveChangePercent(change);
          }
        }
      }
    });
    
    return () => subscription.unsubscribe();
  }, [isOpen, symbol, ws.isConnected, ws.aggregates$, tickerData?.prev_close]);

  // Page Visibility: Refrescar datos cuando vuelve de tab inactiva
  useEffect(() => {
    if (!isOpen || !symbol) return;
    
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        // Tab activa - refrescar metadata
        setLoading(true);
        getCompanyMetadata(symbol)
          .then(data => {
            setMetadata(data);
            setLoading(false);
          })
          .catch(() => setLoading(false));
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [isOpen, symbol]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !symbol || !mounted) return null;

  const formatPrice = (price: number | undefined | null) => {
    if (price === undefined || price === null) return '-';
    return `$${price.toFixed(2)}`;
  };

  const formatPercent = (percent: number | undefined | null) => {
    if (percent === undefined || percent === null) return '-';
    const sign = percent >= 0 ? '+' : '';
    return `${sign}${percent.toFixed(2)}%`;
  };

  const calculateFloat = (floatShares: number | null, outstandingShares: number | null) => {
    if (!floatShares || !outstandingShares) return null;
    return ((floatShares / outstandingShares) * 100).toFixed(1);
  };

  const modalContent = (
    <FloatingWindowBase
      dragHandleClassName="modal-drag-handle"
      initialSize={{ width: 500, height: 400 }}
      minWidth={400}
      minHeight={300}
      maxWidth={1200}
      maxHeight={800}
      enableResizing={true}
      focusedBorderColor="border-blue-500"
      className="bg-white"
      initialZIndex={modalZIndex}
    >
      <div ref={modalRef} className="h-full w-full overflow-hidden flex flex-col">
        {/* Header arrastrable */}
        <div className="modal-drag-handle bg-slate-800 px-3 py-1.5 flex items-center justify-between cursor-move select-none">
          <div className="flex items-center gap-4 flex-1">
            {loading ? (
              <div className="w-6 h-6 bg-slate-700 rounded animate-pulse" />
            ) : metadata?.logo_url ? (
              <img
                src={getProxiedLogoUrl(metadata.logo_url) || ''}
                alt={`${symbol} logo`}
                className="w-6 h-6 object-contain bg-white rounded p-0.5"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            ) : null}
            <div className="flex items-center gap-2 flex-1">
              <span className="text-sm font-bold text-white">{symbol}</span>
              <span className="text-xs font-semibold text-white">
                {formatPrice(livePrice ?? tickerData?.price)}
              </span>
              <span
                className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${(liveChangePercent ?? tickerData?.change_percent ?? 0) >= 0
                  ? 'bg-emerald-500 text-white'
                  : 'bg-rose-500 text-white'
                  }`}
              >
                {formatPercent(liveChangePercent ?? tickerData?.change_percent)}
              </span>
              {metadata?.is_actively_trading !== undefined && (
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${metadata.is_actively_trading
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-slate-100 text-slate-600'
                    }`}
                >
                  {metadata.is_actively_trading ? 'Active' : 'Inactive'}
                </span>
              )}
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-700 rounded transition-colors"
            title="Cerrar (Esc)"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>

        {/* Content con scroll */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-slate-900"></div>
            </div>
          )}

          {error && (
            <div className="m-2 bg-rose-50 border border-rose-200 text-rose-800 px-2 py-1 rounded">
              <p className="font-medium text-xs">Error al cargar metadatos</p>
              <p className="text-[10px] mt-0.5">{error}</p>
            </div>
          )}

          {!loading && !error && metadata && (
            <div className="p-3 space-y-2">
              {/* Company Name */}
              <div>
                <h2 className="text-base font-bold text-slate-900">{metadata.company_name || symbol}</h2>
              </div>

              {/* Classification Line */}
              <div className="flex items-center gap-1 text-[10px] text-slate-700 flex-wrap">
                {metadata.sector && (
                  <>
                    <span className="font-semibold">Sector:</span>
                    <span>{metadata.sector}</span>
                    {(metadata.industry || metadata.exchange) && <span className="text-slate-400 mx-1">|</span>}
                  </>
                )}
                {metadata.industry && (
                  <>
                    <span className="font-semibold">Industry:</span>
                    <span>{metadata.industry}</span>
                    {metadata.exchange && <span className="text-slate-400 mx-1">|</span>}
                  </>
                )}
                {metadata.exchange && (
                  <>
                    <span className="font-semibold">Exchange:</span>
                    <span>{metadata.exchange}</span>
                  </>
                )}
              </div>

              {/* Market Data Line */}
              <div className="flex items-center gap-1 text-[10px] text-slate-700 flex-wrap">
                {metadata.market_cap && (
                  <>
                    <span className="font-semibold">Mkt Cap:</span>
                    <span>${formatNumber(metadata.market_cap)}</span>
                    <span className="text-slate-400 mx-1">|</span>
                  </>
                )}
                {metadata.float_shares && metadata.shares_outstanding && (
                  <>
                    <span className="font-semibold">Float:</span>
                    <span>{formatNumber(metadata.float_shares)} ({calculateFloat(metadata.float_shares, metadata.shares_outstanding)}%)</span>
                    <span className="text-slate-400 mx-1">|</span>
                  </>
                )}
                {metadata.shares_outstanding && (
                  <>
                    <span className="font-semibold">Outstanding:</span>
                    <span>{formatNumber(metadata.shares_outstanding)}</span>
                  </>
                )}
              </div>

              {/* Additional Info Line */}
              <div className="flex items-center gap-1 text-[10px] text-slate-700 flex-wrap">
                {metadata.total_employees && (
                  <>
                    <span className="font-semibold">Employees:</span>
                    <span>{formatNumber(metadata.total_employees)}</span>
                    <span className="text-slate-400 mx-1">|</span>
                  </>
                )}
                {metadata.list_date && (
                  <>
                    <span className="font-semibold">IPO:</span>
                    <span>{metadata.list_date}</span>
                    <span className="text-slate-400 mx-1">|</span>
                  </>
                )}
                {metadata.type && (
                  <>
                    <span className="font-semibold">Type:</span>
                    <span>{metadata.type}</span>
                  </>
                )}
              </div>

              {/* Description */}
              {metadata.description && (
                <div className="pt-1 border-t border-slate-200">
                  <p
                    className={`text-[10px] text-slate-600 leading-snug ${!descriptionExpanded ? 'line-clamp-2' : ''
                      }`}
                  >
                    {metadata.description}
                  </p>
                  {metadata.description.length > 150 && (
                    <button
                      onClick={() => setDescriptionExpanded(!descriptionExpanded)}
                      className="mt-0.5 text-[10px] font-semibold text-blue-600 hover:text-blue-800"
                    >
                      {descriptionExpanded ? 'less' : 'more'}
                    </button>
                  )}
                </div>
              )}

              {/* Links */}
              <div className="flex gap-2 pt-1 border-t border-slate-200">
                <a
                  href={`https://finviz.com/quote.ashx?t=${symbol}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-blue-600 hover:text-blue-800 font-medium"
                >
                  Finviz →
                </a>
                <a
                  href={`https://finance.yahoo.com/quote/${symbol}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-blue-600 hover:text-blue-800 font-medium"
                >
                  Yahoo →
                </a>
                {metadata.homepage_url && (
                  <a
                    href={metadata.homepage_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-blue-600 hover:text-blue-800 font-medium"
                  >
                    Website →
                  </a>
                )}
              </div>

              {/* Detailed Table - Collapsible */}
              <details className="pt-1 border-t border-slate-200">
                <summary className="text-[10px] font-bold text-slate-700 uppercase cursor-pointer hover:text-slate-900">
                  Detailed Information
                </summary>
                <div className="mt-3 space-y-0 text-sm">
                  {metadata.avg_volume_30d && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Avg Volume (30d)</span>
                      <span className="font-medium text-slate-900">{formatNumber(metadata.avg_volume_30d)}</span>
                    </div>
                  )}
                  {metadata.beta !== null && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Beta</span>
                      <span className="font-medium text-slate-900">{metadata.beta.toFixed(2)}</span>
                    </div>
                  )}
                  {metadata.phone_number && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Phone</span>
                      <span className="font-medium text-slate-900">{metadata.phone_number}</span>
                    </div>
                  )}
                  {metadata.address && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Address</span>
                      <span className="font-medium text-slate-900 text-right">
                        {[metadata.address.city, metadata.address.state].filter(Boolean).join(', ') || '-'}
                      </span>
                    </div>
                  )}
                  {metadata.cik && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">CIK</span>
                      <span className="font-medium text-slate-900">{metadata.cik}</span>
                    </div>
                  )}
                  {metadata.currency_name && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Currency</span>
                      <span className="font-medium text-slate-900">{metadata.currency_name.toUpperCase()}</span>
                    </div>
                  )}
                  {metadata.market && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Market</span>
                      <span className="font-medium text-slate-900">{metadata.market}</span>
                    </div>
                  )}
                  {metadata.round_lot && (
                    <div className="flex justify-between py-0.5 border-b border-slate-100 text-[10px]">
                      <span className="text-slate-600">Round Lot</span>
                      <span className="font-medium text-slate-900">{metadata.round_lot}</span>
                    </div>
                  )}
                </div>
              </details>

              {/* Footer */}
              <div className="pt-3 border-t border-slate-200 text-xs text-slate-500 text-center">
                Last updated: {new Date(metadata.updated_at).toLocaleString()}
              </div>
            </div>
          )}
        </div>
      </div>
    </FloatingWindowBase>
  );

  return createPortal(
    modalContent,
    document.getElementById('portal-root') || document.body
  );
}

export default memo(TickerMetadataModal);
