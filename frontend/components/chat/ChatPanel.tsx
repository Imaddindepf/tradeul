'use client';

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MessageCircle, X, Users, Hash, ChevronLeft } from 'lucide-react';
import { useChatStore, selectActiveChannel, selectActiveGroup, selectOnlineCount } from '@/stores/useChatStore';
import { useChatWebSocket } from '@/hooks/useChatWebSocket';
import { ChatSidebar } from './ChatSidebar';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import { cn } from '@/lib/utils';

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ChatPanel({ isOpen, onClose }: ChatPanelProps) {
  const { isConnected, isSidebarOpen, toggleSidebar, activeTarget, setActiveTarget } = useChatStore();
  const activeChannel = useChatStore(selectActiveChannel);
  const activeGroup = useChatStore(selectActiveGroup);
  const onlineCount = useChatStore(selectOnlineCount);
  
  // Initialize WebSocket connection
  useChatWebSocket();

  const activeName = activeChannel?.name || activeGroup?.name || '';
  const activeIcon = activeChannel?.icon || activeGroup?.icon || '';
  const isGroup = activeTarget?.type === 'group';

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: '100%', opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className="fixed right-0 top-0 bottom-0 w-full sm:w-[420px] bg-background border-l border-border shadow-2xl z-50 flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
            <div className="flex items-center gap-3">
              {/* Back button (mobile) or sidebar toggle */}
              <button
                onClick={() => activeTarget ? setActiveTarget(null) : toggleSidebar()}
                className="p-1.5 rounded-lg hover:bg-muted transition-colors sm:hidden"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              
              <button
                onClick={toggleSidebar}
                className="hidden sm:flex p-1.5 rounded-lg hover:bg-muted transition-colors"
              >
                <MessageCircle className="w-5 h-5 text-primary" />
              </button>
              
              {activeTarget ? (
                <div className="flex items-center gap-2">
                  <span className="text-lg">{activeIcon}</span>
                  <div>
                    <div className="flex items-center gap-1.5">
                      {isGroup ? (
                        <Users className="w-3.5 h-3.5 text-muted-foreground" />
                      ) : (
                        <Hash className="w-3.5 h-3.5 text-muted-foreground" />
                      )}
                      <span className="font-semibold">{activeName}</span>
                    </div>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <span className="w-1.5 h-1.5 rounded-full bg-success" />
                      {onlineCount} online
                    </div>
                  </div>
                </div>
              ) : (
                <span className="font-semibold">Community Chat</span>
              )}
            </div>
            
            <div className="flex items-center gap-2">
              {/* Connection status */}
              <div 
                className={cn(
                  "w-2 h-2 rounded-full transition-colors",
                  isConnected ? "bg-success" : "bg-danger animate-pulse"
                )}
                title={isConnected ? "Connected" : "Disconnected"}
              />
              
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-muted transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex flex-1 overflow-hidden">
            {/* Sidebar */}
            <AnimatePresence mode="wait">
              {(isSidebarOpen || !activeTarget) && (
                <motion.div
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: 'auto', opacity: 1 }}
                  exit={{ width: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="border-r border-border overflow-hidden"
                >
                  <ChatSidebar />
                </motion.div>
              )}
            </AnimatePresence>

            {/* Messages area */}
            <div className="flex-1 flex flex-col min-w-0">
              {activeTarget ? (
                <>
                  <ChatMessages />
                  <ChatInput />
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground">
                  <div className="text-center">
                    <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p className="font-medium">Select a channel or group</p>
                    <p className="text-sm">to start chatting</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

