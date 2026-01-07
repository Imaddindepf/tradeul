'use client';

import { memo } from 'react';
import { Loader2 } from 'lucide-react';
import type { Message } from './types';

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';

  return (
    <div className={`py-3 px-3 ${isUser ? 'bg-white' : 'bg-gray-50'}`}>
      {/* Label */}
      <div className={`text-[11px] font-medium mb-1 ${isUser ? 'text-gray-500' : 'text-blue-600'}`}>
        {isUser ? 'Tu' : 'TradeUL'}
      </div>

      {/* Content */}
      <div className={`text-[13px] leading-relaxed ${isUser ? 'text-gray-800' : 'text-gray-700'}`}>
        <MessageContent content={message.content} />

        {/* Status */}
        {isAssistant && message.status && message.status !== 'complete' && (
          <div className="mt-2 flex items-center gap-2 text-[11px]">
            {message.status === 'thinking' && (
              <>
                <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
                <span className="text-gray-400">Analizando...</span>
              </>
            )}
            {message.status === 'executing' && (
              <>
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                <span className="text-green-600">Ejecutando...</span>
              </>
            )}
            {message.status === 'error' && (
              <span className="text-red-500">Error</span>
            )}
          </div>
        )}
      </div>

      {/* Timestamp */}
      <div className="text-[10px] text-gray-400 mt-1.5">
        {message.timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );
});

const MessageContent = memo(function MessageContent({ content }: { content: string }) {
  if (!content) {
    return <span className="text-gray-400 italic">...</span>;
  }

  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, index) => {
        if (part.startsWith('```')) {
          const codeContent = part.replace(/```\w*\n?/g, '').replace(/```$/, '');
          return (
            <pre
              key={index}
              className="mt-2 mb-2 p-2 rounded text-[11px] overflow-x-auto bg-gray-100 text-gray-800 font-mono border border-gray-200"
            >
              {codeContent.trim()}
            </pre>
          );
        }

        if (!part.trim()) return null;

        const formatted = part
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/\*(.*?)\*/g, '<em>$1</em>')
          .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-gray-100 text-blue-600 rounded text-[11px]">$1</code>')
          .replace(/\n/g, '<br />');

        return (
          <span key={index} dangerouslySetInnerHTML={{ __html: formatted }} />
        );
      })}
    </div>
  );
});
