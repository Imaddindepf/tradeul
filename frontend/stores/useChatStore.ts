/**
 * Chat Store - Zustand
 * 
 * Manages chat state for community chat feature.
 * Completely isolated from scanner/ticker stores.
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

// ============================================================================
// TYPES
// ============================================================================

export interface ChatMessage {
  id: string;
  channel_id?: string;
  group_id?: string;
  user_id: string;
  user_name: string;
  user_avatar?: string;
  content: string;
  content_type: 'text' | 'image' | 'file' | 'ticker' | 'system';
  reply_to_id?: string;
  mentions: string[];
  tickers: string[];
  ticker_prices?: Record<string, { price: number; change: number; changePercent: number }>;
  reactions: Record<string, string[]>; // emoji -> user_ids
  created_at: string;
  edited_at?: string;
}

export interface ChatChannel {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  is_default: boolean;
  sort_order: number;
  message_count: number;
  unread_count: number;
}

export interface ChatGroup {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  is_dm: boolean;
  owner_id: string;
  member_count: number;
  unread_count: number;
  created_at: string;
}

export interface ChatMember {
  user_id: string;
  user_name: string;
  user_avatar?: string;
  role: 'owner' | 'admin' | 'member';
  joined_at: string;
}

export interface ChatInvite {
  id: string;
  group_id: string;
  group_name?: string;
  inviter_id: string;
  inviter_name?: string;
  status: 'pending' | 'accepted' | 'declined' | 'expired';
  created_at: string;
  expires_at: string;
}

export interface TypingUser {
  user_id: string;
  user_name: string;
  timestamp: number;
}

export interface ChatState {
  // Connection
  isConnected: boolean;
  connectionError?: string;

  // Data
  channels: ChatChannel[];
  groups: ChatGroup[];
  invites: ChatInvite[];

  // Active chat
  activeTarget: { type: 'channel' | 'group'; id: string } | null;
  messages: Record<string, ChatMessage[]>; // target_key -> messages

  // Typing indicators
  typingUsers: Record<string, TypingUser[]>; // target_key -> typing users

  // Presence
  onlineUsers: Record<string, string[]>; // target_key -> user_ids

  // UI State
  isSidebarOpen: boolean;
  isLoadingMessages: boolean;
  hasMoreMessages: Record<string, boolean>;
  replyingTo: ChatMessage | null;

  // Actions
  setConnected: (connected: boolean, error?: string) => void;
  setChannels: (channels: ChatChannel[]) => void;
  setGroups: (groups: ChatGroup[]) => void;
  setInvites: (invites: ChatInvite[]) => void;
  addInvite: (invite: ChatInvite) => void;
  removeInvite: (groupId: string) => void;
  setActiveTarget: (target: { type: 'channel' | 'group'; id: string } | null) => void;

  // Message actions
  addMessage: (targetKey: string, message: ChatMessage) => void;
  addMessages: (targetKey: string, messages: ChatMessage[], prepend?: boolean) => void;
  updateMessage: (targetKey: string, messageId: string, updates: Partial<ChatMessage>) => void;
  removeMessage: (targetKey: string, messageId: string) => void;
  clearMessages: (targetKey: string) => void;
  invalidateMessages: (targetKey: string) => void; // Fuerza recarga desde servidor
  setHasMoreMessages: (targetKey: string, hasMore: boolean) => void;

  // Typing
  addTypingUser: (targetKey: string, user: TypingUser) => void;
  removeTypingUser: (targetKey: string, userId: string) => void;

  // Presence
  setOnlineUsers: (targetKey: string, userIds: string[]) => void;

  // Reactions
  addReaction: (targetKey: string, messageId: string, emoji: string, userId: string) => void;
  removeReaction: (targetKey: string, messageId: string, emoji: string, userId: string) => void;

  // UI
  toggleSidebar: () => void;
  setLoadingMessages: (loading: boolean) => void;
  setReplyingTo: (message: ChatMessage | null) => void;

  // Utils
  getTargetKey: (target: { type: 'channel' | 'group'; id: string }) => string;
  getActiveMessages: () => ChatMessage[];
}

// ============================================================================
// STORE
// ============================================================================

export const useChatStore = create<ChatState>()(
  devtools(
    persist(
      immer((set, get) => ({
        // Initial state
        isConnected: false,
        connectionError: undefined,
        channels: [],
        groups: [],
        invites: [],
        activeTarget: null,
        messages: {},
        typingUsers: {},
        onlineUsers: {},
        isSidebarOpen: true,
        isLoadingMessages: false,
        hasMoreMessages: {},
        replyingTo: null,

        // Connection
        setConnected: (connected, error) =>
          set((state) => {
            state.isConnected = connected;
            state.connectionError = error;
          }),

        // Data
        setChannels: (channels) =>
          set((state) => {
            state.channels = channels;
          }),

        setGroups: (groups) =>
          set((state) => {
            state.groups = groups;
          }),

        setInvites: (invites) =>
          set((state) => {
            state.invites = invites;
          }),

        addInvite: (invite) =>
          set((state) => {
            const exists = state.invites.some((i) => i.id === invite.id || i.group_id === invite.group_id);
            if (!exists) {
              state.invites.push(invite);
            }
          }),

        removeInvite: (groupId) =>
          set((state) => {
            state.invites = state.invites.filter((i) => i.group_id !== groupId);
          }),

        setActiveTarget: (target) =>
          set((state) => {
            state.activeTarget = target;
          }),

        // Messages
        addMessage: (targetKey, message) =>
          set((state) => {
            if (!state.messages[targetKey]) {
              state.messages[targetKey] = [];
            }
            // Avoid duplicates
            const exists = state.messages[targetKey].some((m) => m.id === message.id);
            if (!exists) {
              state.messages[targetKey].push(message);
            }
          }),

        addMessages: (targetKey, messages, prepend = false) =>
          set((state) => {
            if (!state.messages[targetKey]) {
              state.messages[targetKey] = [];
            }
            // Filter duplicates
            const existingIds = new Set(state.messages[targetKey].map((m) => m.id));
            const newMessages = messages.filter((m) => !existingIds.has(m.id));

            if (prepend) {
              state.messages[targetKey] = [...newMessages, ...state.messages[targetKey]];
            } else {
              state.messages[targetKey] = [...state.messages[targetKey], ...newMessages];
            }
          }),

        updateMessage: (targetKey, messageId, updates) =>
          set((state) => {
            const messages = state.messages[targetKey];
            if (!messages) return;
            const index = messages.findIndex((m) => m.id === messageId);
            if (index !== -1) {
              Object.assign(messages[index], updates);
            }
          }),

        removeMessage: (targetKey, messageId) =>
          set((state) => {
            const messages = state.messages[targetKey];
            if (!messages) return;
            const index = messages.findIndex((m) => m.id === messageId);
            if (index !== -1) {
              messages.splice(index, 1);
            }
          }),

        clearMessages: (targetKey) =>
          set((state) => {
            state.messages[targetKey] = [];
            state.hasMoreMessages[targetKey] = true;
          }),

        // Invalidar mensajes completamente (fuerza recarga desde servidor)
        invalidateMessages: (targetKey) =>
          set((state) => {
            delete state.messages[targetKey];
            delete state.hasMoreMessages[targetKey];
          }),

        setHasMoreMessages: (targetKey, hasMore) =>
          set((state) => {
            state.hasMoreMessages[targetKey] = hasMore;
          }),

        // Typing
        addTypingUser: (targetKey, user) =>
          set((state) => {
            if (!state.typingUsers[targetKey]) {
              state.typingUsers[targetKey] = [];
            }
            // Update or add
            const existing = state.typingUsers[targetKey].findIndex(
              (u) => u.user_id === user.user_id
            );
            if (existing !== -1) {
              state.typingUsers[targetKey][existing] = user;
            } else {
              state.typingUsers[targetKey].push(user);
            }
          }),

        removeTypingUser: (targetKey, userId) =>
          set((state) => {
            const users = state.typingUsers[targetKey];
            if (!users) return;
            const index = users.findIndex((u) => u.user_id === userId);
            if (index !== -1) {
              users.splice(index, 1);
            }
          }),

        // Presence
        setOnlineUsers: (targetKey, userIds) =>
          set((state) => {
            state.onlineUsers[targetKey] = userIds;
          }),

        // Reactions
        addReaction: (targetKey, messageId, emoji, userId) =>
          set((state) => {
            const messages = state.messages[targetKey];
            if (!messages) return;
            const message = messages.find((m) => m.id === messageId);
            if (!message) return;
            if (!message.reactions[emoji]) {
              message.reactions[emoji] = [];
            }
            if (!message.reactions[emoji].includes(userId)) {
              message.reactions[emoji].push(userId);
            }
          }),

        removeReaction: (targetKey, messageId, emoji, userId) =>
          set((state) => {
            const messages = state.messages[targetKey];
            if (!messages) return;
            const message = messages.find((m) => m.id === messageId);
            if (!message || !message.reactions[emoji]) return;
            const index = message.reactions[emoji].indexOf(userId);
            if (index !== -1) {
              message.reactions[emoji].splice(index, 1);
              if (message.reactions[emoji].length === 0) {
                delete message.reactions[emoji];
              }
            }
          }),

        // UI
        toggleSidebar: () =>
          set((state) => {
            state.isSidebarOpen = !state.isSidebarOpen;
          }),

        setLoadingMessages: (loading) =>
          set((state) => {
            state.isLoadingMessages = loading;
          }),

        setReplyingTo: (message) =>
          set((state) => {
            state.replyingTo = message;
          }),

        // Utils
        getTargetKey: (target) => `${target.type}:${target.id}`,

        getActiveMessages: () => {
          const state = get();
          if (!state.activeTarget) return [];
          const key = state.getTargetKey(state.activeTarget);
          return state.messages[key] || [];
        },
      })),
      {
        name: 'tradeul-chat',
        partialize: (state) => ({
          // Only persist UI preferences
          isSidebarOpen: state.isSidebarOpen,
          activeTarget: state.activeTarget,
        }),
      }
    ),
    { name: 'ChatStore' }
  )
);

// ============================================================================
// SELECTORS
// ============================================================================

export const selectActiveChannel = (state: ChatState) => {
  if (state.activeTarget?.type === 'channel') {
    return state.channels.find((c) => c.id === state.activeTarget?.id);
  }
  return null;
};

export const selectActiveGroup = (state: ChatState) => {
  if (state.activeTarget?.type === 'group') {
    return state.groups.find((g) => g.id === state.activeTarget?.id);
  }
  return null;
};

export const selectTypingUsers = (state: ChatState) => {
  if (!state.activeTarget) return [];
  const key = state.getTargetKey(state.activeTarget);
  // Filter out stale typing indicators (> 5 seconds)
  const now = Date.now();
  return (state.typingUsers[key] || []).filter((u) => now - u.timestamp < 5000);
};

export const selectOnlineCount = (state: ChatState) => {
  if (!state.activeTarget) return 0;
  const key = state.getTargetKey(state.activeTarget);
  return state.onlineUsers[key]?.length || 0;
};

