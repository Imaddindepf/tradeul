'use client';

import React, { memo } from 'react';
import { Loader2, AlertCircle, CheckCircle, Wrench, Clock } from 'lucide-react';
import { CodeBlock } from './CodeBlock';
import { DataTable } from './DataTable';
import { Chart } from './Chart';
import type { ResultBlockData, OutputBlock } from './types';

interface ResultBlockProps {
  block: ResultBlockData;
  onToggleCode: () => void;
}

export const ResultBlock = memo(function ResultBlock({ block, onToggleCode }: ResultBlockProps) {
  const { status, code, codeVisible, result } = block;

  const renderOutput = (output: OutputBlock, index: number) => {
    switch (output.type) {
      case 'table':
        return (
          <DataTable
            key={index}
            columns={output.columns || []}
            rows={output.rows || []}
            title={output.title}
            total={output.total}
          />
        );

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

      case 'stats':
        if ((output as any).content) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-gray-50 p-3">
              <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap overflow-x-auto">
                {(output as any).content}
              </pre>
            </div>
          );
        }
        if (output.stats && Object.keys(output.stats).length > 0) {
          return (
            <div key={index} className="rounded border border-gray-200 bg-white p-3">
              <h3 className="text-[12px] font-medium text-gray-700 mb-2">{output.title}</h3>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(output.stats).map(([col, stats]) => (
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
        // Research output from Grok with inline clickable citations
        const researchOutput = output as any;
        const citations = researchOutput.citations || [];
        
        // Clean markdown: remove **, *, and convert to plain text
        const cleanMarkdown = (text: string): string => {
          return text
            .replace(/\*\*([^*]+)\*\*/g, '$1')  // Remove bold **
            .replace(/\*([^*]+)\*/g, '$1')       // Remove italic *
            .replace(/^#+\s*/gm, '')             // Remove headers #
            .replace(/\[web:\d+[,\d]*\]/g, '')   // Remove [web:36,94] refs
            .replace(/\(Yahoo Finance.*?\)/g, '') // Remove (Yahoo Finance [...])
            .replace(/\(Sources?:.*?\)/gi, '')   // Remove (Source: ...)
            .trim();
        };
        
        // Render clickable citation badges inline
        const renderCitation = (num: number, key: string) => {
          const url = citations[num - 1];
          if (!url) return null;
          return (
            <a
              key={key}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center w-[18px] h-[18px] mx-0.5 text-[9px] font-bold bg-blue-500 text-white rounded-full hover:bg-blue-600 transition-colors cursor-pointer shadow-sm"
              title={url}
            >
              {num}
            </a>
          );
        };
        
        // Parse text and render with inline citations
        const renderWithCitations = (text: string) => {
          const cleaned = cleanMarkdown(text);
          // Match [number] or [number,number]
          const parts = cleaned.split(/(\[\d+(?:,\d+)*\])/g);
          
          return parts.map((part, i) => {
            const match = part.match(/\[(\d+(?:,\d+)*)\]/);
            if (match) {
              const nums = match[1].split(',').map(n => parseInt(n.trim()));
              return (
                <span key={i} className="inline-flex gap-0.5">
                  {nums.map((num, j) => renderCitation(num, `${i}-${j}`))}
                </span>
              );
            }
            return part ? <span key={i}>{part}</span> : null;
          });
        };
        
        // Render a section header
        const renderHeader = (title: string) => (
          <h4 className="font-bold text-gray-900 text-[15px] mt-5 mb-2 pb-1.5 border-b-2 border-blue-100 first:mt-0">
            {cleanMarkdown(title).replace(/:$/, '')}
          </h4>
        );
        
        // Parse content into formatted sections
        const renderContent = (content: string) => {
          if (!content) return null;
          
          // Remove the "Sources:" section at the end (we show it separately)
          let mainContent = content.replace(/---\s*\*?\*?Sources:?\*?\*?[\s\S]*$/i, '').trim();
          // Also remove standalone "Sources" line with URLs
          mainContent = mainContent.replace(/\n\s*Sources?:?\s*\n[\s\S]*$/i, '').trim();
          
          // Split into sections by headers (text followed by colon or bold text)
          const lines = mainContent.split('\n');
          const elements: JSX.Element[] = [];
          let currentSection = '';
          let currentItems: string[] = [];
          
          const flushItems = (key: number) => {
            if (currentItems.length > 0) {
              elements.push(
                <ul key={`items-${key}`} className="space-y-2 my-2 ml-1">
                  {currentItems.map((item, j) => (
                    <li key={j} className="flex gap-2 text-[13px] text-gray-700 leading-relaxed">
                      <span className="text-blue-400 mt-0.5 flex-shrink-0">•</span>
                      <span>{renderWithCitations(item)}</span>
                    </li>
                  ))}
                </ul>
              );
              currentItems = [];
            }
          };
          
          lines.forEach((line, i) => {
            const trimmed = line.trim();
            if (!trimmed) return;
            
            // Detect section headers: TLDR, News, Financial Metrics, etc.
            const headerPatterns = [
              /^(TLDR|News|Financial Metrics?|Social Sentiment|Analyst View|Sources?)[\s:]/i,
              /^\*\*(TLDR|News|Financial|Social|Analyst|Sources?)[^*]*\*\*/i
            ];
            
            const isHeader = headerPatterns.some(p => p.test(trimmed));
            
            if (isHeader) {
              flushItems(i);
              // Extract header name
              const match = trimmed.match(/^[\*]*\s*([A-Za-z\s]+?)[\*]*[\s:]/);
              if (match) {
                elements.push(<React.Fragment key={`header-${i}`}>{renderHeader(match[1])}</React.Fragment>);
                // Content after header on same line
                const afterHeader = trimmed.replace(/^[\*]*\s*[A-Za-z\s]+?[\*]*[\s:]+/, '').trim();
                if (afterHeader) {
                  elements.push(
                    <p key={`p-${i}`} className="text-[13px] text-gray-700 leading-relaxed mb-2">
                      {renderWithCitations(afterHeader)}
                    </p>
                  );
                }
              }
            } else if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
              // Bullet point
              currentItems.push(trimmed.replace(/^[-•]\s*/, ''));
            } else if (/^\d+\.\s/.test(trimmed)) {
              // Numbered item - treat as bullet
              currentItems.push(trimmed.replace(/^\d+\.\s*/, ''));
            } else {
              // Regular paragraph
              flushItems(i);
              elements.push(
                <p key={`p-${i}`} className="text-[13px] text-gray-700 leading-relaxed mb-2">
                  {renderWithCitations(trimmed)}
                </p>
              );
            }
          });
          
          flushItems(lines.length);
          return elements;
        };
        
        return (
          <div key={index} className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
            {/* Header */}
            <div className="px-5 py-4 bg-gradient-to-r from-blue-50 via-indigo-50 to-purple-50 border-b border-gray-100">
              <h3 className="text-[16px] font-bold text-gray-900">{researchOutput.title || 'Research Results'}</h3>
              {citations.length > 0 && (
                <p className="text-[12px] text-gray-500 mt-1">{citations.length} sources analyzed</p>
              )}
            </div>
            
            {/* Content with inline citations */}
            <div className="px-5 py-4">
              {renderContent(researchOutput.content)}
            </div>
            
            {/* Collapsible Sources */}
            {citations.length > 0 && (
              <details className="border-t border-gray-100 bg-gray-50">
                <summary className="px-5 py-3 cursor-pointer text-[12px] font-medium text-gray-600 hover:text-gray-900 select-none">
                  View {citations.length} sources
                </summary>
                <div className="px-5 pb-4 grid grid-cols-2 gap-2">
                  {citations.map((cite: string, i: number) => {
                    const domain = cite.replace(/^https?:\/\/(www\.)?/, '').split('/')[0];
                    return (
                      <a 
                        key={i}
                        href={cite}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-[11px] hover:bg-white rounded-lg p-2 transition-colors group border border-transparent hover:border-gray-200"
                      >
                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white flex items-center justify-center font-bold text-[9px]">
                          {i + 1}
                        </span>
                        <span className="text-gray-500 group-hover:text-blue-600 truncate">
                          {domain}
                        </span>
                      </a>
                    );
                  })}
                </div>
              </details>
            )}
          </div>
        );

      case 'error':
        return (
          <div key={index} className="rounded border border-red-200 bg-red-50 p-3">
            <div className="flex items-center gap-2 text-red-600 text-[12px]">
              <AlertCircle className="w-4 h-4" />
              <span className="font-medium">Error</span>
            </div>
            <p className="mt-1 text-[11px] text-red-500 font-mono">{output.title}</p>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-3">
      {/* Status */}
      <div className="flex items-center gap-2">
        {status === 'running' && (
          <>
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
            <span className="text-[12px] text-blue-600">Ejecutando...</span>
          </>
        )}
        {status === 'fixing' && (
          <>
            <Wrench className="w-4 h-4 text-amber-500 animate-pulse" />
            <span className="text-[12px] text-amber-600">Corrigiendo...</span>
          </>
        )}
        {status === 'success' && (
          <>
            <CheckCircle className="w-4 h-4 text-green-500" />
            <span className="text-[12px] text-green-600">Completado</span>
            {result && (
              <span className="text-[11px] text-gray-400 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {result.execution_time_ms}ms
              </span>
            )}
          </>
        )}
        {status === 'error' && (
          <>
            <AlertCircle className="w-4 h-4 text-red-500" />
            <span className="text-[12px] text-red-600">Error</span>
          </>
        )}
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
        <div className="rounded border border-red-200 bg-red-50 p-3">
          <div className="flex items-center gap-2 text-red-600 mb-2 text-[12px]">
            <AlertCircle className="w-4 h-4" />
            <span className="font-medium">Error de ejecucion</span>
          </div>
          <pre className="text-[11px] text-red-500 font-mono whitespace-pre-wrap">{result.error}</pre>
        </div>
      )}
    </div>
  );
});
