'use client';

/**
 * Quote Monitor - Real-time watchlist with tabs and sections
 * Pro features: multi-watchlist, sections, real-time quotes, customizable columns
 */

import { useState, useCallback, useRef, useEffect, memo } from 'react';
import {
  Plus, X, Settings, MoreHorizontal, Trash2, Edit2,
  RefreshCw, ArrowUpDown, TrendingUp, TrendingDown,
  ChevronDown, ChevronRight, FolderPlus, GripVertical
} from 'lucide-react';
import { useWatchlists, Watchlist, WatchlistTicker, WatchlistSection } from '@/hooks/useWatchlists';
import { useRealtimeQuote, QuoteData } from '@/hooks/useRealtimeQuote';

// ============================================================================
// Types
// ============================================================================

interface QuoteRowProps {
  ticker: WatchlistTicker;
  quote: QuoteData | null;
  onRemove: () => void;
  onRowClick: () => void;
  onDragStart?: (e: React.DragEvent, symbol: string) => void;
  isDragging?: boolean;
}

// ============================================================================
// Quote Row Component - Optimized with memo
// ============================================================================

const QuoteRow = memo(function QuoteRow({ ticker, quote, onRemove, onRowClick, onDragStart, isDragging }: QuoteRowProps) {
  const priceRef = useRef<HTMLSpanElement>(null);

  // Use refs for DOM updates to avoid re-renders
  useEffect(() => {
    if (!quote) return;

    if (priceRef.current) {
      priceRef.current.textContent = `${quote.bidPrice?.toFixed(2) || '-'}`;
    }
  }, [quote]);

  const handleDragStart = (e: React.DragEvent) => {
    if (onDragStart) {
      onDragStart(e, ticker.symbol);
    }
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', ticker.symbol);
    // Visual feedback
    if (e.currentTarget instanceof HTMLElement) {
      e.currentTarget.style.opacity = '0.5';
    }
  };

  const handleDragEnd = (e: React.DragEvent) => {
    if (e.currentTarget instanceof HTMLElement) {
      e.currentTarget.style.opacity = '1';
    }
  };

  return (
    <tr
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      className={`border-b border-slate-100 hover:bg-blue-50/50 cursor-pointer group h-[22px] ${isDragging ? 'opacity-50' : ''
        }`}
      onClick={onRowClick}
    >
      {/* Drag Handle */}
      <td className="w-[20px] px-0.5 py-0 cursor-grab active:cursor-grabbing">
        <GripVertical className="w-3 h-3 text-slate-300 group-hover:text-slate-500" />
      </td>

      {/* Symbol */}
      <td className="w-[60px] px-1.5 py-0">
        <span className="font-semibold text-[11px] text-blue-600">{ticker.symbol}</span>
      </td>

      {/* Last Price (midPrice) */}
      <td className="w-[55px] px-1.5 py-0 text-right">
        <span ref={priceRef} className="font-mono text-[11px] tabular-nums text-slate-800">
          {quote?.midPrice ? quote.midPrice.toFixed(2) : '-.--'}
        </span>
      </td>

      {/* Change % */}
      <td className="w-[55px] px-1.5 py-0 text-right">
        <span className={`font-mono text-[11px] tabular-nums ${(quote?.changePercent ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
          {quote?.changePercent !== undefined
            ? `${quote.changePercent >= 0 ? '+' : ''}${quote.changePercent.toFixed(2)}%`
            : '-.--'}
        </span>
      </td>

      {/* Bid */}
      <td className="w-[55px] px-1.5 py-0 text-right">
        <span className="font-mono text-[11px] tabular-nums text-green-600">
          {quote?.bidPrice ? quote.bidPrice.toFixed(2) : '-.--'}
        </span>
      </td>

      {/* Ask */}
      <td className="w-[55px] px-1.5 py-0 text-right">
        <span className="font-mono text-[11px] tabular-nums text-red-600">
          {quote?.askPrice ? quote.askPrice.toFixed(2) : '-.--'}
        </span>
      </td>

      {/* Spread */}
      <td className="w-[45px] px-1.5 py-0 text-right">
        <span className="font-mono text-[11px] tabular-nums text-slate-500">
          {quote?.spread ? quote.spread.toFixed(2) : '-.--'}
        </span>
      </td>

      {/* Volume (bidSize) */}
      <td className="w-[45px] px-1.5 py-0 text-right">
        <span className="font-mono text-[11px] tabular-nums text-slate-500">
          {quote?.bidSize ? formatVolume(quote.bidSize) : '-'}
        </span>
      </td>

      {/* Latency */}
      <td className="w-[40px] px-1.5 py-0 text-right">
        <span className={`font-mono text-[10px] tabular-nums ${(quote?._latency?.latencyMs || 0) < 100 ? 'text-green-600' :
            (quote?._latency?.latencyMs || 0) < 500 ? 'text-yellow-600' : 'text-red-600'
          }`}>
          {quote?._latency?.latencyMs ? `${quote._latency.latencyMs}` : '-'}
        </span>
      </td>

      {/* Actions */}
      <td className="w-[16px] px-0 py-0 text-center">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500"
        >
          <X className="w-3 h-3" />
        </button>
      </td>
    </tr>
  );
});

// ============================================================================
// Quote Row with Real-time Hook
// ============================================================================

function QuoteRowWithData({ ticker, onRemove, onRowClick, onDragStart, isDragging }: Omit<QuoteRowProps, 'quote'>) {
  const { quote } = useRealtimeQuote(ticker.symbol);
  return <QuoteRow ticker={ticker} quote={quote} onRemove={onRemove} onRowClick={onRowClick} onDragStart={onDragStart} isDragging={isDragging} />;
}

// ============================================================================
// Section Header Component
// ============================================================================

interface SectionHeaderProps {
  section: WatchlistSection;
  isCollapsed: boolean;
  onToggle: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
  tickerCount: number;
  onDrop?: (e: React.DragEvent, sectionId: string) => void;
  onDragOver?: (e: React.DragEvent, sectionId: string) => void;
  onDragLeave?: () => void;
  isDragOver?: boolean;
}

const SectionHeader = memo(function SectionHeader({
  section, isCollapsed, onToggle, onRename, onDelete, tickerCount, onDrop, onDragOver, onDragLeave, isDragOver
}: SectionHeaderProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(section.name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setEditName(section.name);
  }, [section.name]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSubmit = () => {
    if (editName.trim() && editName !== section.name) {
      onRename(editName.trim());
    }
    setIsEditing(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    if (onDragOver) {
      onDragOver(e, section.id);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onDragLeave) {
      onDragLeave();
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onDrop) {
      onDrop(e, section.id);
    }
  };

  return (
    <tr
      className={`bg-slate-50 border-b border-slate-200 ${isDragOver ? 'bg-blue-100 border-blue-300' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <td colSpan={10} className="px-1 py-0.5">
        <div className="flex items-center gap-1 group">
          <button
            onClick={onToggle}
            className="p-0.5 hover:bg-slate-200 rounded transition-colors"
          >
            {isCollapsed ? (
              <ChevronRight className="w-3 h-3 text-slate-500" />
            ) : (
              <ChevronDown className="w-3 h-3 text-slate-500" />
            )}
          </button>

          {section.color && (
            <div
              className="w-2 h-2 rounded-sm"
              style={{ backgroundColor: section.color }}
            />
          )}

          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onBlur={handleSubmit}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Enter') handleSubmit();
                if (e.key === 'Escape') {
                  setEditName(section.name);
                  setIsEditing(false);
                }
              }}
              className="flex-1 px-1 text-[11px] font-medium bg-white border border-blue-400 rounded outline-none"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span
              className="text-[11px] font-medium text-slate-700 cursor-pointer"
              onDoubleClick={() => setIsEditing(true)}
            >
              {section.name}
            </span>
          )}

          <span className="text-[10px] text-slate-400">
            ({tickerCount})
          </span>

          <div className="flex-1" />

          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-red-500 rounded"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </td>
    </tr>
  );
});

// ============================================================================
// Tab Component
// ============================================================================

interface TabProps {
  watchlist: Watchlist;
  isActive: boolean;
  onClick: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
}

const Tab = memo(function Tab({ watchlist, isActive, onClick, onRename, onDelete }: TabProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(watchlist.name);
  const inputRef = useRef<HTMLInputElement>(null);

  // Total ticker count (sections + unsorted)
  const totalTickers = (watchlist.sections?.reduce((acc, s) => acc + (s.tickers?.length || 0), 0) || 0)
    + (watchlist.tickers?.length || 0);

  useEffect(() => {
    setEditName(watchlist.name);
  }, [watchlist.name]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSubmit = () => {
    if (editName.trim() && editName !== watchlist.name) {
      onRename(editName.trim());
    }
    setIsEditing(false);
  };

  return (
    <div
      className={`group flex items-center gap-0.5 px-2 py-1 rounded-t cursor-pointer text-[11px] ${isActive
          ? 'bg-white border-t border-l border-r border-slate-200 -mb-px font-medium'
          : 'bg-slate-200/50 hover:bg-slate-200 text-slate-500'
        }`}
      style={{ borderColor: isActive && watchlist.color ? watchlist.color : undefined }}
      onClick={onClick}
    >
      {watchlist.color && (
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: watchlist.color }}
        />
      )}

      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onBlur={handleSubmit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSubmit();
            if (e.key === 'Escape') {
              setEditName(watchlist.name);
              setIsEditing(false);
            }
          }}
          className="w-16 px-0.5 text-[11px] bg-transparent border-b border-blue-500 outline-none"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span
          onDoubleClick={(e) => {
            e.stopPropagation();
            setIsEditing(true);
          }}
        >
          {watchlist.name}
        </span>
      )}

      <span className="text-[9px] text-slate-400">
        {totalTickers}
      </span>

      {isActive && !isEditing && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500"
        >
          <X className="w-2.5 h-2.5" />
        </button>
      )}
    </div>
  );
});

// ============================================================================
// Main Component
// ============================================================================

export function QuoteMonitor() {
  const {
    watchlists,
    activeWatchlist,
    activeWatchlistId,
    setActiveWatchlistId,
    loading,
    createWatchlist,
    updateWatchlist,
    deleteWatchlist,
    addTicker,
    removeTicker,
    createSection,
    updateSection,
    deleteSection,
    toggleSectionCollapsed,
    moveTickersToSection,
    refetch,
  } = useWatchlists();

  const [newTickerInput, setNewTickerInput] = useState('');
  const [isAddingWatchlist, setIsAddingWatchlist] = useState(false);
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [isAddingSection, setIsAddingSection] = useState(false);
  const [newSectionName, setNewSectionName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const sectionInputRef = useRef<HTMLInputElement>(null);

  // Drag & Drop state
  const [draggedSymbol, setDraggedSymbol] = useState<string | null>(null);
  const [dragOverSectionId, setDragOverSectionId] = useState<string | null>(null);

  // Handle adding ticker
  const handleAddTicker = async () => {
    if (!activeWatchlistId || !newTickerInput.trim()) return;

    const symbols = newTickerInput
      .split(/[,\s]+/)
      .map(s => s.trim().toUpperCase())
      .filter(Boolean);

    for (const symbol of symbols) {
      await addTicker(activeWatchlistId, symbol);
    }

    setNewTickerInput('');
    inputRef.current?.focus();
  };

  // Handle creating watchlist
  const handleCreateWatchlist = async () => {
    if (!newWatchlistName.trim()) return;

    await createWatchlist({
      name: newWatchlistName.trim(),
      color: getRandomColor(),
    });

    setNewWatchlistName('');
    setIsAddingWatchlist(false);
  };

  // Handle creating section
  const handleCreateSection = async () => {
    if (!activeWatchlistId || !newSectionName.trim()) return;

    await createSection(activeWatchlistId, {
      name: newSectionName.trim(),
      color: getSectionColor(),
    });

    setNewSectionName('');
    setIsAddingSection(false);
  };

  // Handle row click - open DES
  const handleRowClick = (symbol: string) => {
    console.log('Open DES for', symbol);
  };

  // Drag & Drop handlers
  const handleDragStart = (e: React.DragEvent, symbol: string) => {
    setDraggedSymbol(symbol);
  };

  const handleDropOnSection = async (e: React.DragEvent, sectionId: string) => {
    e.preventDefault();
    e.stopPropagation();

    if (!draggedSymbol || !activeWatchlistId) return;

    // Don't move if already in this section
    const section = activeWatchlist?.sections?.find(s => s.id === sectionId);
    if (section?.tickers?.some(t => t.symbol === draggedSymbol)) {
      setDraggedSymbol(null);
      setDragOverSectionId(null);
      return;
    }

    // Move ticker to section
    await moveTickersToSection(activeWatchlistId, sectionId, [draggedSymbol]);

    setDraggedSymbol(null);
    setDragOverSectionId(null);
  };

  const handleDropOnUnsorted = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!draggedSymbol || !activeWatchlistId) return;

    // Move ticker to unsorted (no section)
    await moveTickersToSection(activeWatchlistId, 'unsorted', [draggedSymbol]);

    setDraggedSymbol(null);
    setDragOverSectionId(null);
  };

  const handleDragOverUnsorted = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDragOverSection = (e: React.DragEvent, sectionId: string) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    setDragOverSectionId(sectionId);
  };

  const handleDragLeave = () => {
    setDragOverSectionId(null);
  };

  // Cleanup drag state on unmount or when watchlist changes
  useEffect(() => {
    return () => {
      setDraggedSymbol(null);
      setDragOverSectionId(null);
    };
  }, [activeWatchlistId]);

  // Focus section input when shown
  useEffect(() => {
    if (isAddingSection && sectionInputRef.current) {
      sectionInputRef.current.focus();
    }
  }, [isAddingSection]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-white">
        <RefreshCw className="w-6 h-6 text-blue-500 animate-spin" />
      </div>
    );
  }

  // Compute all tickers (sections + unsorted)
  const hasSections = activeWatchlist?.sections && activeWatchlist.sections.length > 0;
  const hasUnsortedTickers = activeWatchlist?.tickers && activeWatchlist.tickers.length > 0;
  const totalItems = hasSections || hasUnsortedTickers;

  return (
    <div className="h-full flex flex-col bg-white relative">
      {/* Tab Bar - Compact */}
      <div className="flex items-center gap-0.5 px-1 pt-1 bg-slate-100 border-b border-slate-200">
        {watchlists.map((wl) => (
          <Tab
            key={wl.id}
            watchlist={wl}
            isActive={wl.id === activeWatchlistId}
            onClick={() => setActiveWatchlistId(wl.id)}
            onRename={(name) => updateWatchlist(wl.id, { name })}
            onDelete={() => deleteWatchlist(wl.id)}
          />
        ))}

        {/* Add Tab Button */}
        {isAddingWatchlist ? (
          <div className="flex items-center gap-0.5 px-1.5 py-1 bg-white rounded-t border border-slate-200">
            <input
              type="text"
              value={newWatchlistName}
              onChange={(e) => setNewWatchlistName(e.target.value)}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleCreateWatchlist();
                }
                if (e.key === 'Escape') {
                  setNewWatchlistName('');
                  setIsAddingWatchlist(false);
                }
              }}
              onBlur={() => {
                if (newWatchlistName.trim()) {
                  handleCreateWatchlist();
                } else {
                  setIsAddingWatchlist(false);
                }
              }}
              placeholder="Name"
              className="w-20 px-0.5 text-[11px] bg-transparent border-b border-blue-500 outline-none text-slate-800"
              autoFocus
            />
          </div>
        ) : (
          <button
            onClick={() => setIsAddingWatchlist(true)}
            className="flex items-center px-1.5 py-1 text-slate-400 hover:text-blue-600 hover:bg-slate-200 rounded-t"
            title="Add watchlist"
          >
            <Plus className="w-3 h-3" />
          </button>
        )}

        <div className="flex-1" />

        {/* Add Section Button */}
        {activeWatchlist && (
          <button
            onClick={() => setIsAddingSection(true)}
            className="flex items-center gap-0.5 px-1.5 py-1 text-slate-400 hover:text-blue-600 hover:bg-slate-200 rounded text-[10px]"
            title="Add section"
          >
            <FolderPlus className="w-3 h-3" />
            <span>Section</span>
          </button>
        )}
      </div>

      {/* New Section Input */}
      {isAddingSection && (
        <div className="flex items-center gap-2 px-2 py-1.5 bg-blue-50 border-b border-blue-200">
          <FolderPlus className="w-3.5 h-3.5 text-blue-500" />
          <input
            ref={sectionInputRef}
            type="text"
            value={newSectionName}
            onChange={(e) => setNewSectionName(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                handleCreateSection();
              }
              if (e.key === 'Escape') {
                setNewSectionName('');
                setIsAddingSection(false);
              }
            }}
            placeholder="Section name..."
            className="flex-1 px-2 py-0.5 bg-white text-slate-800 text-[11px] rounded border border-blue-300 
                       placeholder-slate-400 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleCreateSection}
            disabled={!newSectionName.trim()}
            className="px-2 py-0.5 bg-blue-600 text-white text-[10px] font-medium rounded 
                       hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
          >
            Create
          </button>
          <button
            onClick={() => {
              setNewSectionName('');
              setIsAddingSection(false);
            }}
            className="text-slate-400 hover:text-slate-600"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto bg-white">
        {activeWatchlist ? (
          <table className="w-full border-collapse table-fixed">
            <thead className="sticky top-0 bg-slate-100 border-b border-slate-200 z-10">
              <tr className="h-[20px]">
                <th className="w-[20px] px-0.5 py-0"></th>
                <th className="w-[60px] px-1.5 py-0 text-left text-[10px] font-semibold text-slate-500 uppercase">Ticker</th>
                <th className="w-[55px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Last</th>
                <th className="w-[55px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Chg%</th>
                <th className="w-[55px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Bid</th>
                <th className="w-[55px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Ask</th>
                <th className="w-[45px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Sprd</th>
                <th className="w-[45px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Vol</th>
                <th className="w-[40px] px-1.5 py-0 text-right text-[10px] font-semibold text-slate-500 uppercase">Lat</th>
                <th className="w-[16px]"></th>
              </tr>
            </thead>
            <tbody>
              {/* Render sections with their tickers */}
              {activeWatchlist.sections?.map((section) => (
                <SectionGroup
                  key={section.id}
                  section={section}
                  watchlistId={activeWatchlist.id}
                  onToggle={() => toggleSectionCollapsed(activeWatchlist.id, section.id)}
                  onRename={(name) => updateSection(activeWatchlist.id, section.id, { name })}
                  onDelete={() => deleteSection(activeWatchlist.id, section.id)}
                  onRemoveTicker={(symbol) => removeTicker(activeWatchlist.id, symbol)}
                  onRowClick={handleRowClick}
                  onDrop={handleDropOnSection}
                  onDragOver={handleDragOverSection}
                  onDragLeave={handleDragLeave}
                  isDragOver={dragOverSectionId === section.id}
                  onDragStart={handleDragStart}
                  draggedSymbol={draggedSymbol}
                />
              ))}

              {/* Render unsorted tickers */}
              {hasUnsortedTickers && hasSections && (
                <tr
                  className="bg-slate-50/50 border-b border-slate-200"
                  onDragOver={handleDragOverUnsorted}
                  onDrop={handleDropOnUnsorted}
                >
                  <td colSpan={10} className="px-1.5 py-0.5">
                    <span className="text-[10px] text-slate-400 italic">
                      Unsorted ({activeWatchlist.tickers.length})
                    </span>
                  </td>
                </tr>
              )}

              {activeWatchlist.tickers?.map((ticker) => (
                <QuoteRowWithData
                  key={ticker.symbol}
                  ticker={ticker}
                  onRemove={() => removeTicker(activeWatchlist.id, ticker.symbol)}
                  onRowClick={() => handleRowClick(ticker.symbol)}
                  onDragStart={handleDragStart}
                  isDragging={draggedSymbol === ticker.symbol}
                />
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex items-center justify-center h-full text-slate-400">
            No watchlist selected
          </div>
        )}
      </div>

      {/* Add Ticker Input - Compact */}
      {activeWatchlist && (
        <div className="flex items-center gap-2 px-2 py-1.5 bg-slate-50 border-t border-slate-200">
          <input
            ref={inputRef}
            type="text"
            value={newTickerInput}
            onChange={(e) => setNewTickerInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                handleAddTicker();
              }
            }}
            placeholder="Add ticker..."
            className="flex-1 px-2 py-1 bg-white text-slate-800 text-[11px] rounded border border-slate-200 
                       placeholder-slate-400 focus:outline-none focus:border-blue-400"
          />
          <button
            onClick={handleAddTicker}
            disabled={!newTickerInput.trim()}
            className="px-2 py-1 bg-blue-600 text-white text-[10px] font-medium rounded 
                       hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
          >
            Add
          </button>
        </div>
      )}

      {/* Empty State */}
      {activeWatchlist && !totalItems && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: '60px' }}>
          <div className="text-center text-slate-300">
            <p className="text-sm">Empty watchlist</p>
            <p className="text-xs mt-1">Add tickers or create sections</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Section Group Component
// ============================================================================

interface SectionGroupProps {
  section: WatchlistSection;
  watchlistId: string;
  onToggle: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
  onRemoveTicker: (symbol: string) => void;
  onRowClick: (symbol: string) => void;
  onDrop?: (e: React.DragEvent, sectionId: string) => void;
  onDragOver?: (e: React.DragEvent, sectionId: string) => void;
  onDragLeave?: () => void;
  isDragOver?: boolean;
  onDragStart?: (e: React.DragEvent, symbol: string) => void;
  draggedSymbol?: string | null;
}

function SectionGroup({
  section, watchlistId, onToggle, onRename, onDelete, onRemoveTicker, onRowClick, onDrop, onDragOver, onDragLeave, isDragOver, onDragStart, draggedSymbol
}: SectionGroupProps) {
  const tickerCount = section.tickers?.length || 0;

  return (
    <>
      <SectionHeader
        section={section}
        isCollapsed={section.is_collapsed}
        onToggle={onToggle}
        onRename={onRename}
        onDelete={onDelete}
        tickerCount={tickerCount}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        isDragOver={isDragOver}
      />

      {!section.is_collapsed && section.tickers?.map((ticker) => (
        <QuoteRowWithData
          key={ticker.symbol}
          ticker={ticker}
          onRemove={() => onRemoveTicker(ticker.symbol)}
          onRowClick={() => onRowClick(ticker.symbol)}
          onDragStart={onDragStart}
          isDragging={draggedSymbol === ticker.symbol}
        />
      ))}
    </>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function formatVolume(volume: number): string {
  if (volume >= 1_000_000_000) return `${(volume / 1_000_000_000).toFixed(1)}B`;
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(1)}M`;
  if (volume >= 1_000) return `${(volume / 1_000).toFixed(1)}K`;
  return volume.toString();
}

function getRandomColor(): string {
  const colors = [
    '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
    '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
  ];
  return colors[Math.floor(Math.random() * colors.length)];
}

function getSectionColor(): string {
  const colors = [
    '#64748B', '#475569', '#6B7280', '#78716C', '#71717A',
    '#059669', '#0891B2', '#7C3AED', '#DB2777', '#EA580C',
  ];
  return colors[Math.floor(Math.random() * colors.length)];
}

export default QuoteMonitor;
