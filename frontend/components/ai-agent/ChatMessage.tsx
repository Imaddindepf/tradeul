'use client';

import { memo, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { Message } from './types';
import { AgentSteps } from './AgentSteps';

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const [thinkingSeconds, setThinkingSeconds] = useState(0);

  // Timer for thinking state
  useEffect(() => {
    if (message.status === 'thinking' && message.thinkingStartTime) {
      const interval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - message.thinkingStartTime!) / 1000);
        setThinkingSeconds(elapsed);
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [message.status, message.thinkingStartTime]);

  return (
    <div className={`py-5 px-4 ${isUser ? 'bg-white' : 'bg-gray-50/30'}`}>
      <div className="max-w-3xl mx-auto">
        {/* User message - clean bubble aligned right */}
        {isUser && (
          <div className="flex justify-end">
            <div className="bg-gray-100 rounded-2xl rounded-tr-sm px-4 py-3 max-w-[80%] shadow-sm">
              <p className="text-[14px] text-gray-800 leading-relaxed">{message.content}</p>
              <div className="text-[10px] text-gray-400 mt-1.5 text-right">
                {message.timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        )}

        {/* Assistant message - agent style with steps */}
        {isAssistant && (
          <div className="space-y-4">
            {/* Thinking indicator when no steps yet */}
            {message.status === 'thinking' && (!message.steps || message.steps.length === 0) && (
              <ThinkingState seconds={thinkingSeconds} />
            )}

            {/* Steps display */}
            {message.steps && message.steps.length > 0 && (
              <AgentSteps 
                steps={message.steps} 
                thinkingTime={message.status === 'complete' ? thinkingSeconds : undefined}
              />
            )}

            {/* Main text content */}
            {message.content && (
              <div className="text-[14px] leading-relaxed text-gray-700 pt-1">
                <MessageContent content={message.content} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

const ThinkingState = memo(function ThinkingState({ seconds }: { seconds: number }) {
  return (
    <div className="flex items-center gap-2.5 text-[13px] text-gray-500">
      <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
      <span className="font-medium">
        {seconds > 0 
          ? `Reasoning for ${seconds} second${seconds !== 1 ? 's' : ''}...`
          : 'Reasoning...'
        }
      </span>
    </div>
  );
});

const MessageContent = memo(function MessageContent({ content }: { content: string }) {
  if (!content) {
    return null;
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
              className="mt-2 mb-2 p-3 rounded-lg text-[12px] overflow-x-auto bg-gray-100 text-gray-800 font-mono border border-gray-200"
            >
              {codeContent.trim()}
            </pre>
          );
        }

        if (!part.trim()) return null;

        const formatted = part
          .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
          .replace(/\*(.*?)\*/g, '<em>$1</em>')
          .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 bg-gray-100 text-emerald-700 rounded text-[12px] font-mono">$1</code>')
          .replace(/\n/g, '<br />');

        return (
          <span key={index} dangerouslySetInnerHTML={{ __html: formatted }} />
        );
      })}
    </div>
  );
});

export default ChatMessage;
