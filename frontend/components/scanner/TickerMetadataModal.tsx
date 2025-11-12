'use client';

import { useEffect, useRef, useState, memo } from 'react';
import { createPortal } from 'react-dom';
import type { CompanyMetadata } from '@/lib/types';
import { getCompanyMetadata } from '@/lib/api';
import { formatNumber } from '@/lib/formatters';

interface TickerMetadataModalProps {
  symbol: string | null;
  isOpen: boolean;
  onClose: () => void;
}

function TickerMetadataModal({ symbol, isOpen, onClose }: TickerMetadataModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const [metadata, setMetadata] = useState<CompanyMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  // Solo renderizar en el cliente
  useEffect(() => {
    setMounted(true);
  }, []);

  // Cargar metadatos cuando se abre el modal
  useEffect(() => {
    if (isOpen && symbol) {
      setLoading(true);
      setError(null);
      
      getCompanyMetadata(symbol)
        .then((data) => {
          setMetadata(data);
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message || 'Error al cargar metadatos');
          setLoading(false);
        });
    }
  }, [isOpen, symbol]);

  // Cerrar al presionar Escape (SIN modificar body overflow para evitar reflow)
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

  // Cerrar al hacer clic fuera del modal
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  // No renderizar hasta que esté mounted (client-side)
  if (!mounted || !isOpen || !symbol) return null;

  // Organizar metadatos de la compañía en secciones
  const sections = metadata ? [
    {
      title: 'Company Information',
      items: [
        { label: 'Symbol', value: metadata.symbol },
        { label: 'Company Name', value: metadata.company_name || '-' },
        { label: 'Type', value: metadata.is_etf ? 'ETF' : 'Stock' },
        { label: 'Status', value: metadata.is_actively_trading ? 'Active' : 'Inactive', color: metadata.is_actively_trading ? 'text-emerald-600' : 'text-rose-600' },
      ],
    },
    {
      title: 'Exchange & Classification',
      items: [
        { label: 'Exchange', value: metadata.exchange || '-' },
        { label: 'Sector', value: metadata.sector || '-' },
        { label: 'Industry', value: metadata.industry || '-' },
      ],
    },
    {
      title: 'Market Capitalization',
      items: [
        { label: 'Market Cap', value: metadata.market_cap !== null ? `$${formatNumber(metadata.market_cap)}` : '-' },
        { label: 'Float Shares', value: metadata.float_shares !== null ? formatNumber(metadata.float_shares) : '-' },
        { label: 'Shares Outstanding', value: metadata.shares_outstanding !== null ? formatNumber(metadata.shares_outstanding) : '-' },
      ],
    },
    {
      title: 'Average Volume',
      items: [
        { label: 'Avg Volume (30d)', value: metadata.avg_volume_30d !== null ? formatNumber(metadata.avg_volume_30d) : '-' },
        { label: 'Avg Volume (10d)', value: metadata.avg_volume_10d !== null ? formatNumber(metadata.avg_volume_10d) : '-' },
      ],
    },
    {
      title: 'Price Statistics',
      items: [
        { label: 'Avg Price (30d)', value: metadata.avg_price_30d !== null ? `$${metadata.avg_price_30d.toFixed(2)}` : '-' },
        { label: 'Beta', value: metadata.beta !== null ? metadata.beta.toFixed(3) : '-' },
      ],
    },
    {
      title: 'Metadata Info',
      items: [
        { label: 'Last Updated', value: new Date(metadata.updated_at).toLocaleString() },
      ],
    },
  ] : [];

  // Usar portal para renderizar fuera del árbol DOM
  const modalContent = (
    <div 
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm animate-fadeIn" 
      style={{ 
        margin: 0,
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        pointerEvents: 'auto'
      }}
    >
      <div
        ref={modalRef}
        className="bg-white rounded-lg shadow-2xl max-w-5xl w-full mx-4 max-h-[90vh] overflow-hidden animate-slideUp"
      >
        {/* Header */}
        <div className="bg-slate-800 px-6 py-4 flex items-center justify-between border-b border-slate-700">
          <div>
            <h2 className="text-2xl font-bold text-white">{symbol}</h2>
            <p className="text-slate-300 text-sm mt-0.5">Company Metadata</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg p-2 transition-all duration-200"
            aria-label="Close"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-6 overflow-y-auto max-h-[calc(90vh-140px)] custom-scrollbar bg-slate-50">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-700"></div>
            </div>
          )}
          
          {error && (
            <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 text-rose-700">
              <p className="font-semibold">Error</p>
              <p className="text-sm">{error}</p>
            </div>
          )}
          
          {!loading && !error && metadata && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {sections.map((section) => (
                <div
                  key={section.title}
                  className="bg-white rounded-lg p-4 border border-slate-200 shadow-sm"
                >
                  <h3 className="text-sm font-bold text-slate-700 mb-3 pb-2 border-b border-slate-200 uppercase tracking-wide">
                    {section.title}
                  </h3>
                  <div className="space-y-2.5">
                    {section.items.map((item) => (
                      <div key={item.label} className="flex justify-between items-center gap-2">
                        <span className="text-xs text-slate-600 font-medium">{item.label}</span>
                        <span
                          className={`text-sm font-semibold ${
                            item.color || 'text-slate-900'
                          } font-mono text-right`}
                        >
                          {item.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-white px-6 py-4 flex justify-end border-t border-slate-200">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-slate-700 hover:bg-slate-800 text-white font-medium rounded-lg transition-colors duration-200"
          >
            Close
          </button>
        </div>
      </div>

      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        @keyframes slideUp {
          from {
            transform: translateY(20px);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }

        .animate-fadeIn {
          animation: fadeIn 0.2s ease-out;
        }

        .animate-slideUp {
          animation: slideUp 0.3s ease-out;
        }

        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }

        .custom-scrollbar::-webkit-scrollbar-track {
          background: #f1f5f9;
          border-radius: 4px;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #cbd5e1;
          border-radius: 4px;
        }

        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #94a3b8;
        }
      `}</style>
    </div>
  );

  // Renderizar en portal para evitar afectar el layout de las tablas
  return createPortal(modalContent, document.body);
}

// Memoizar para evitar re-renders innecesarios
export default memo(TickerMetadataModal);
