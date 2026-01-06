'use client';

import { memo } from 'react';
import { User, Bot, Loader2, AlertCircle, Play } from 'lucide-react';
import type { Message } from './types';

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className={`
        flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
        ${isUser ? 'bg-blue-600' : 'bg-blue-100'}
      `}>
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-blue-600" />
        )}
      </div>

      {/* Content */}
      <div className={`
        flex-1 max-w-[85%] space-y-1
        ${isUser ? 'text-right' : 'text-left'}
      `}>
        {/* Message bubble */}
        <div className={`
          inline-block px-4 py-2.5 rounded-2xl text-sm leading-relaxed
          ${isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-white text-gray-800 rounded-bl-sm border border-gray-200 shadow-sm'
          }
        `}>
          {/* Render markdown-like content */}
          <MessageContent content={message.content} isUser={isUser} />

          {/* Status indicator for assistant */}
          {isAssistant && message.status && (
            <div className="mt-2 flex items-center gap-2 text-xs">
              {message.status === 'thinking' && (
                <>
                  <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
                  <span className="text-gray-500">Pensando...</span>
                </>
              )}
              {message.status === 'executing' && (
                <>
                  <Play className="w-3 h-3 text-green-600" />
                  <span className="text-green-600">Ejecutando codigo...</span>
                </>
              )}
              {message.status === 'error' && (
                <>
                  <AlertCircle className="w-3 h-3 text-red-500" />
                  <span className="text-red-500">Error</span>
                </>
              )}
            </div>
          )}
        </div>

        {/* Timestamp */}
        <div className={`text-xs text-gray-400 ${isUser ? 'pr-1' : 'pl-1'}`}>
          {message.timestamp.toLocaleTimeString('es-ES', {
            hour: '2-digit',
            minute: '2-digit'
          })}
        </div>
      </div>
    </div>
  );
});

// Componente para renderizar contenido con formato basico
const MessageContent = memo(function MessageContent({ content, isUser }: { content: string; isUser: boolean }) {
  if (!content) {
    return <span className={isUser ? 'text-blue-200 italic' : 'text-gray-400 italic'}>...</span>;
  }

  // Dividir por bloques de codigo
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <>
      {parts.map((part, index) => {
        // Bloque de codigo
        if (part.startsWith('```')) {
          const codeContent = part.replace(/```\w*\n?/g, '').replace(/```$/, '');
          return (
            <pre
              key={index}
              className="mt-2 mb-2 p-2 bg-gray-100 rounded text-xs font-mono overflow-x-auto border border-gray-200 text-gray-800"
            >
              {codeContent.trim()}
            </pre>
          );
        }

        // Texto normal con formato basico
        const codeClass = isUser
          ? 'px-1 py-0.5 bg-blue-500 rounded text-xs font-mono text-white'
          : 'px-1 py-0.5 bg-blue-50 rounded text-xs font-mono text-blue-600';

        const formatted = part
          // Bold
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          // Italic
          .replace(/\*(.*?)\*/g, '<em>$1</em>')
          // Inline code
          .replace(/`([^`]+)`/g, `<code class="${codeClass}">$1</code>`)
          // Line breaks
          .replace(/\n/g, '<br />');

        return (
          <span
            key={index}
            dangerouslySetInnerHTML={{ __html: formatted }}
          />
        );
      })}
    </>
  );
});
