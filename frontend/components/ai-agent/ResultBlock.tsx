'use client';

import React, { memo, useMemo } from 'react';
import { Search } from 'lucide-react';
import { CodeBlock } from './CodeBlock';
import { DataTable } from './DataTable';
import { SectorPerformanceTable } from './SectorPerformanceTable';
import { Chart } from './Chart';
import { TradingChart } from '@/components/chart/TradingChart';
import type { ResultBlockData, OutputBlock } from './types';

interface ResultBlockProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

/**
 * MarkdownResponse - Parses markdown with tables and renders properly
 * Converts | table | format | to real HTML tables
 */
const MarkdownResponse = memo(function MarkdownResponse({ content }: { content: string }) {
  const parsed = useMemo(() => {
    const lines = content.split('\n');
    const elements: { type: 'text' | 'table' | 'header' | 'bullet'; content: string; rows?: string[][] }[] = [];
    let currentTable: string[][] = [];
    let inTable = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // Table row detection
      if (line.startsWith('|') && line.endsWith('|')) {
        // Skip separator rows (|---|---|)
        if (line.includes('---')) continue;

        // Parse table row
        const cells = line.split('|').filter(c => c.trim()).map(c => c.trim());
        if (cells.length > 0) {
          currentTable.push(cells);
          inTable = true;
        }
      } else {
        // End of table
        if (inTable && currentTable.length > 0) {
          elements.push({ type: 'table', content: '', rows: currentTable });
          currentTable = [];
          inTable = false;
        }

        if (!line) continue;

        // Headers
        if (line.startsWith('**') && line.endsWith('**')) {
          elements.push({ type: 'header', content: line.replace(/\*\*/g, '') });
        }
        // Bullets
        else if (line.startsWith('*') && !line.startsWith('**')) {
          elements.push({ type: 'bullet', content: line.slice(1).trim() });
        }
        // Regular text
        else {
          elements.push({ type: 'text', content: line });
        }
      }
    }

    // Don't forget last table
    if (currentTable.length > 0) {
      elements.push({ type: 'table', content: '', rows: currentTable });
    }

    return elements;
  }, [content]);

  return (
    <div className="space-y-3">
      {parsed.map((el, idx) => {
        if (el.type === 'table' && el.rows && el.rows.length > 0) {
          const headers = el.rows[0];
          const dataRows = el.rows.slice(1);

          return (
            <div key={idx} className="overflow-x-auto border border-slate-200 rounded-lg">
              <table className="w-full text-[12px]">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    {headers.map((h, i) => (
                      <th key={i} className="px-3 py-2 text-left font-semibold text-slate-700">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {dataRows.map((row, rowIdx) => (
                    <tr key={rowIdx} className="hover:bg-slate-50">
                      {row.map((cell, cellIdx) => (
                        <td key={cellIdx} className="px-3 py-2 text-slate-600">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (el.type === 'header') {
          return (
            <h4 key={idx} className="font-semibold text-slate-800 text-[13px] mt-4 first:mt-0">
              {el.content}
            </h4>
          );
        }

        if (el.type === 'bullet') {
          // Parse bold within bullets
          const formatted = el.content.replace(
            /\*\*([^*]+)\*\*/g,
            '<strong class="font-semibold text-slate-700">$1</strong>'
          );
          return (
            <div key={idx} className="flex gap-2 text-[12px] text-slate-600 leading-relaxed pl-1">
              <span className="text-slate-400">-</span>
              <span dangerouslySetInnerHTML={{ __html: formatted }} />
            </div>
          );
        }

        if (el.type === 'text') {
          return (
            <p key={idx} className="text-[12px] text-slate-600 leading-relaxed">
              {el.content}
            </p>
          );
        }

        return null;
      })}
    </div>
  );
});

export const ResultBlock = memo(function ResultBlock({ block, onToggleCode }: ResultBlockProps) {
  const { status, code, codeVisible, result } = block;

  // Check if we have real data outputs (not just text stats)
  const hasDataOutputs = result?.outputs?.some(o =>
    o.type === 'table' || o.type === 'chart' || o.type === 'plotly_chart' ||
    o.type === 'research' || o.type === 'news'
  );

  const renderOutput = (output: OutputBlock, index: number) => {
    // Skip stats with content if we have real data (avoids duplication)
    if (output.type === 'stats' && (output as any).content && hasDataOutputs) {
      return null;
    }

    switch (output.type) {
      case 'table': {
        const columns = output.columns || [];
        const rows = output.rows || [];

        // Detect if this is a Sector Performance table
        const isSectorPerformance =
          columns.includes('sector') &&
          columns.includes('ticker_count') &&
          columns.includes('tickers') &&
          columns.includes('avg_change');

        if (isSectorPerformance) {
          return (
            <SectorPerformanceTable
              key={index}
              rows={rows as any}
              title={output.title}
              total={output.total}
            />
          );
        }

        return (
          <DataTable
            key={index}
            columns={columns}
            rows={rows}
            title={output.title}
            total={output.total}
          />
        );
      }

      case 'chart':
        if (output.plotly_config) {
          return <Chart key={index} title={output.title} plotlyConfig={output.plotly_config} />;
        }
        if ((output as any).image_base64) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-white overflow-hidden">
              {output.title && (
                <div className="px-3 py-2 bg-gray-50 border-b text-[12px] font-medium text-gray-600">
                  {output.title}
                </div>
              )}
              <img
                src={`data:image/png;base64,${(output as any).image_base64}`}
                alt={output.title || 'Chart'}
                className="max-w-full h-auto"
              />
            </div>
          );
        }
        return null;

      case 'plotly_chart':
        // Technical chart with Plotly (from research flow)
        if (output.plotly_config) {
          return <Chart key={index} title={output.title} plotlyConfig={output.plotly_config} />;
        }
        return null;

      case 'stats':
        if ((output as any).content) {
          // Parse markdown tables and render as real HTML tables
          return <MarkdownResponse key={index} content={(output as any).content} />;
        }
        if (output.stats && Object.keys(output.stats).length > 0) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-white p-3">
              <h3 className="text-[12px] font-medium text-gray-700 mb-2">{output.title}</h3>
              <div className="grid grid-cols-2 gap-3">
1                {Object.entries(output.stats).map(([col, stats]) => (
                  <div key={col} className="bg-gray-50 rounded p-2">
                    <div className="text-[10px] text-gray-500 uppercase">{col}</div>
                    <div className="grid grid-cols-2 gap-1 text-[11px] mt-1">
                      <span className="text-gray-400">Min:</span>
                      <span className="font-mono">{stats.min}</span>
                      <span className="text-gray-400">Max:</span>
                      <span className="font-mono">{stats.max}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        }
        return null;

      case 'research':
        // Research output - professional with inline citations
        const researchOutput = output as any;
        const citations = researchOutput.citations || [];
        const rawContent = researchOutput.content || '';
        const tickerMatch = researchOutput.title?.match(/Research:\s*([A-Z]{1,5})/i);
        const ticker = tickerMatch ? tickerMatch[1].toUpperCase() : null;

        // Render inline citation as small clickable badge
        const CitationBadge = ({ num, url }: { num: number; url?: string }) => {
          const href = url || citations[num - 1];
          if (!href) return <sup className="text-slate-400 text-[9px]">[{num}]</sup>;
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center min-w-[14px] h-[14px] px-0.5 ml-0.5 text-[9px] font-medium bg-slate-100 text-slate-600 rounded hover:bg-slate-200 cursor-pointer align-super"
              title={href}
            >
              {num}
            </a>
          );
        };

        // Parse text and render with inline citations
        const renderTextWithCitations = (text: string) => {
          // Clean artifacts
          let cleaned = text
            .replace(/\*\*:/g, ':')           // **:  → :
            .replace(/:\*\*/g, ':')           // :**  → :
            .replace(/\*\*\s*\*\*/g, '')      // ** ** → nothing
            .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')  // **text** → <b>text</b>
            .replace(/\*([^*]+)\*/g, '<i>$1</i>')       // *text* → <i>text</i>
            .trim();

          // Pattern for citations: [[1]](url), [1], [1,2,3]
          const pattern = /(\[\[\d+\]\]\([^)]+\)|\[\d+(?:,\d+)*\])/g;
          const parts = cleaned.split(pattern);

          return parts.map((part, i) => {
            // [[num]](url) format
            const inlineMatch = part.match(/\[\[(\d+)\]\]\(([^)]+)\)/);
            if (inlineMatch) {
              return <CitationBadge key={i} num={parseInt(inlineMatch[1])} url={inlineMatch[2]} />;
            }

            // [num] or [num,num] format
            const simpleMatch = part.match(/\[(\d+(?:,\d+)*)\]/);
            if (simpleMatch) {
              const nums = simpleMatch[1].split(',').map(n => parseInt(n.trim()));
              return (
                <span key={i}>
                  {nums.map((num, j) => <CitationBadge key={j} num={num} />)}
                </span>
              );
            }

            // Regular text - render HTML tags
            if (part.includes('<b>') || part.includes('<i>')) {
              return <span key={i} dangerouslySetInnerHTML={{ __html: part }} />;
            }

            return part || null;
          });
        };

        // Parse content into sections
        const parseContent = (text: string) => {
          const sections: { title: string; content: string }[] = [];

          // Section patterns with their titles
          const patterns = [
            { regex: /\*?\*?TLDR\*?\*?[:\s]+([^\n]+(?:\n(?!\*?\*?[A-Z])[^\n]*)*)/i, title: 'Summary' },
            { regex: /\*?\*?Breaking News\*?\*?[:\s]*\n?((?:[-•]?\s*[^\n]+\n?)+?)(?=\n\*?\*?[A-Z]|$)/i, title: 'Breaking News' },
            { regex: /\*?\*?X\.?com Sentiment\*?\*?[:\s]+([^\n]+(?:\n(?!\*?\*?[A-Z])[^\n]*)*)/i, title: 'Social Sentiment' },
            { regex: /\*?\*?Key (?:Numbers|Metrics)\*?\*?[:\s]*\n?((?:[-•]?\s*[^\n]+\n?)+?)(?=\n\*?\*?[A-Z]|$)/i, title: 'Key Metrics' },
            { regex: /\*?\*?Analysis\*?\*?[:\s]+([^\n]+(?:\n(?!---|📰|\*?\*?[A-Z][a-z]+\*?\*?:)[^\n]*)*)/i, title: 'Analysis' },
            { regex: /📰\s*Benzinga[^:]*:[^\n]*\n((?:[-•]\s*[^\n]+\n?)+)/i, title: 'Recent News' },
          ];

          for (const { regex, title } of patterns) {
            const match = text.match(regex);
            if (match && match[1]?.trim()) {
              sections.push({ title, content: match[1].trim() });
            }
          }

          return sections;
        };

        const sections = parseContent(rawContent);

        return (
          <div key={index} className="space-y-5">
            {/* Header */}
            <div className="pb-3 border-b border-slate-200">
              <h3 className="text-[16px] font-bold text-slate-900">
                {ticker ? `${ticker} Research` : 'Research'}
              </h3>
              <p className="text-[11px] text-slate-500 mt-1">{citations.length} sources cited</p>
            </div>

            {/* Sections */}
            {sections.map((section, idx) => (
              <div key={idx} className="space-y-2">
                <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  {section.title}
                </h4>
                <div className="text-[13px] text-slate-800 leading-[1.7] space-y-2">
                  {section.content.split('\n').filter(l => l.trim()).map((line, li) => {
                    const trimmed = line.trim();
                    // Bullet points
                    if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
                      return (
                        <div key={li} className="flex gap-2 pl-2">
                          <span className="text-slate-400 select-none">•</span>
                          <span>{renderTextWithCitations(trimmed.replace(/^[-•]\s*/, ''))}</span>
                        </div>
                      );
                    }
                    // Regular paragraph
                    return (
                      <p key={li}>{renderTextWithCitations(trimmed)}</p>
                    );
                  })}
                </div>
              </div>
            ))}

            {/* Chart */}
            {ticker && (
              <div className="border border-slate-200 rounded overflow-hidden mt-4">
                <div className="h-[350px]">
                  <TradingChart ticker={ticker} minimal />
                </div>
              </div>
            )}
          </div>
        );

      case 'news':
        // Quick news with Deep Research button
        const newsOutput = output as any;
        const newsItems = newsOutput.news || [];
        const symbol = newsOutput.symbol || '';

        return (
          <div key={index} className="rounded border border-slate-200 bg-white overflow-hidden">
            {/* Header */}
            <div className="px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-[13px] font-medium text-slate-800">
                  {symbol ? `News: ${symbol}` : 'News'}
                </h3>
                <p className="text-[10px] text-slate-500">{newsItems.length} articles</p>
              </div>
              {newsOutput.deep_research_available && (
                <button
                  onClick={() => {
                    window.dispatchEvent(new CustomEvent('agent:send', {
                      detail: { message: `deep research ${symbol}` }
                    }));
                  }}
                  className="px-2.5 py-1.5 text-[10px] text-slate-600 border border-slate-300 rounded hover:bg-slate-50 transition-colors flex items-center gap-1.5"
                >
                  <Search className="w-3 h-3" />
                  Deep Research
                </button>
              )}
            </div>

            {/* News list */}
            {newsItems.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {newsItems.map((news: any, i: number) => (
                  <div key={i} className="px-4 py-2.5 hover:bg-slate-50 transition-colors">
                    <h4 className="text-[12px] font-medium text-slate-800 leading-snug">{news.title}</h4>
                    {news.summary && (
                      <p className="text-[11px] text-slate-600 mt-1 leading-relaxed">{news.summary}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-slate-400">
                      <span>{news.source}</span>
                      {news.published && (
                        <>
                          <span>-</span>
                          <span>{new Date(news.published).toLocaleString('es-ES', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                          })}</span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="px-4 py-6 text-center">
                <p className="text-[12px] text-slate-500">No recent news for {symbol}</p>
                {newsOutput.deep_research_available && (
                  <button
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent('agent:send', {
                        detail: { message: `deep research ${symbol}` }
                      }));
                    }}
                    className="mt-3 px-4 py-2 text-[11px] text-slate-600 border border-slate-300 rounded hover:bg-slate-50 transition-colors"
                  >
                    Try Deep Research
                  </button>
                )}
              </div>
            )}
          </div>
        );

      case 'error':
        return (
          <div key={index} className="rounded border border-slate-200 p-3">
            <div className="text-[12px] font-medium text-slate-700">Error</div>
            <p className="mt-1 text-[11px] text-slate-500 font-mono">{output.title}</p>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-3">
      {/* Status - minimal */}
      <div className="flex items-center gap-2 text-[11px] text-slate-500">
        {status === 'running' && <span>Processing...</span>}
        {status === 'fixing' && <span>Retrying...</span>}
        {status === 'success' && result && <span>{result.execution_time_ms}ms</span>}
        {status === 'error' && <span>Error</span>}
      </div>

      {/* Code */}
      <CodeBlock code={code} title="Codigo" isVisible={codeVisible} onToggle={onToggleCode} />

      {/* Outputs */}
      {result?.outputs && result.outputs.length > 0 && (
        <div className="space-y-3">
          {result.outputs.map((output, index) => renderOutput(output, index))}
        </div>
      )}

      {/* Error */}
      {result?.error && status === 'error' && (
        <div className="rounded border border-slate-200 p-3">
          <div className="text-[12px] font-medium text-slate-700 mb-2">Execution Error</div>
          <pre className="text-[11px] text-slate-600 font-mono whitespace-pre-wrap">{result.error}</pre>
        </div>
      )}
    </div>
  );
});
