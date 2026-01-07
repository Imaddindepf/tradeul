'use client';

import { memo, useEffect, useState } from 'react';
import { Brain } from 'lucide-react';
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
    <div className={`py-4 px-4 ${isUser ? 'bg-white' : 'bg-gray-50/50'}`}>
      <div className="max-w-3xl mx-auto">
        {/* User message - simple bubble style */}
        {isUser && (
          <div className="flex justify-end">
            <div className="bg-gray-100 rounded-2xl rounded-tr-md px-4 py-2.5 max-w-[85%]">
              <p className="text-[14px] text-gray-800">{message.content}</p>
              <div className="text-[10px] text-gray-400 mt-1 text-right">
                {message.timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        )}

        {/* Assistant message - agent style with steps */}
        {isAssistant && (
          <div className="space-y-3">
            {/* Steps display */}
            {message.steps && message.steps.length > 0 && (
              <AgentSteps 
                steps={message.steps} 
                thinkingTime={message.status === 'complete' ? thinkingSeconds : undefined}
              />
            )}

            {/* Thinking indicator when no steps yet */}
            {message.status === 'thinking' && (!message.steps || message.steps.length === 0) && (
              <ThinkingState seconds={thinkingSeconds} />
            )}

            {/* Main text content */}
            {message.content && (
              <div className="text-[14px] leading-relaxed text-gray-700">
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
    <div className="flex items-center gap-2 text-sm text-gray-500">
      <Brain className="w-4 h-4 animate-pulse" />
      <span>
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
              className="mt-2 mb-2 p-3 rounded-lg text-[12px] overflow-x-auto bg-gray-900 text-gray-100 font-mono"
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
