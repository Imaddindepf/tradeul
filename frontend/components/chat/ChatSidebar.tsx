'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Hash, Users, Plus, Bell, Settings, Loader2 } from 'lucide-react';
import { useChatStore, type ChatChannel, type ChatGroup } from '@/stores/useChatStore';
import { cn } from '@/lib/utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'http://localhost:8016';

export function ChatSidebar() {
  const { 
    channels, 
    groups, 
    invites,
    activeTarget, 
    setActiveTarget, 
    setChannels, 
    setGroups,
    setInvites 
  } = useChatStore();
  
  const [isLoading, setIsLoading] = useState(true);
  const [showNewGroup, setShowNewGroup] = useState(false);

  // Fetch channels and groups
  useEffect(() => {
    async function loadData() {
      try {
        const [channelsRes, groupsRes, invitesRes] = await Promise.all([
          fetch(`${CHAT_API_URL}/api/chat/channels`),
          fetch(`${CHAT_API_URL}/api/chat/groups`, { credentials: 'include' }),
          fetch(`${CHAT_API_URL}/api/chat/invites`, { credentials: 'include' }),
        ]);

        if (channelsRes.ok) {
          const data = await channelsRes.json();
          setChannels(data);
        }

        if (groupsRes.ok) {
          const data = await groupsRes.json();
          setGroups(data);
        }

        if (invitesRes.ok) {
          const data = await invitesRes.json();
          setInvites(data);
        }
      } catch (error) {
        console.error('Failed to load chat data:', error);
      } finally {
        setIsLoading(false);
      }
    }

    loadData();
  }, [setChannels, setGroups, setInvites]);

  if (isLoading) {
    return (
      <div className="w-48 flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="w-48 flex flex-col h-full bg-muted/20">
      {/* Channels Section */}
      <div className="p-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 px-2">
          Channels
        </h3>
        <div className="space-y-0.5">
          {channels.map((channel) => (
            <ChannelItem
              key={channel.id}
              channel={channel}
              isActive={activeTarget?.type === 'channel' && activeTarget.id === channel.id}
              onClick={() => setActiveTarget({ type: 'channel', id: channel.id })}
            />
          ))}
        </div>
      </div>

      {/* Groups Section */}
      <div className="p-3 flex-1">
        <div className="flex items-center justify-between mb-2 px-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Groups
          </h3>
          <button
            onClick={() => setShowNewGroup(true)}
            className="p-0.5 rounded hover:bg-muted transition-colors"
          >
            <Plus className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        </div>
        
        {groups.length === 0 ? (
          <p className="text-xs text-muted-foreground px-2 py-2">
            No groups yet
          </p>
        ) : (
          <div className="space-y-0.5">
            {groups.map((group) => (
              <GroupItem
                key={group.id}
                group={group}
                isActive={activeTarget?.type === 'group' && activeTarget.id === group.id}
                onClick={() => setActiveTarget({ type: 'group', id: group.id })}
              />
            ))}
          </div>
        )}
      </div>

      {/* Invites */}
      {invites.length > 0 && (
        <div className="p-3 border-t border-border">
          <div className="flex items-center gap-2 px-2 py-1.5 bg-primary/10 rounded-lg text-sm">
            <Bell className="w-4 h-4 text-primary" />
            <span className="font-medium">{invites.length} pending</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

function ChannelItem({ 
  channel, 
  isActive, 
  onClick 
}: { 
  channel: ChatChannel; 
  isActive: boolean; 
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors text-left",
        isActive 
          ? "bg-primary text-white" 
          : "hover:bg-muted text-foreground"
      )}
    >
      <span className="text-base">{channel.icon || '💬'}</span>
      <span className="truncate flex-1">{channel.name}</span>
      {channel.unread_count > 0 && (
        <span className={cn(
          "min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-[10px] font-bold",
          isActive ? "bg-white/20" : "bg-primary text-white"
        )}>
          {channel.unread_count > 99 ? '99+' : channel.unread_count}
        </span>
      )}
    </button>
  );
}

function GroupItem({ 
  group, 
  isActive, 
  onClick 
}: { 
  group: ChatGroup; 
  isActive: boolean; 
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors text-left",
        isActive 
          ? "bg-primary text-white" 
          : "hover:bg-muted text-foreground"
      )}
    >
      {group.is_dm ? (
        <Users className="w-4 h-4 shrink-0" />
      ) : (
        <span className="text-base">{group.icon || '👥'}</span>
      )}
      <span className="truncate flex-1">{group.name}</span>
      {group.unread_count > 0 && (
        <span className={cn(
          "min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-[10px] font-bold",
          isActive ? "bg-white/20" : "bg-primary text-white"
        )}>
          {group.unread_count > 99 ? '99+' : group.unread_count}
        </span>
      )}
    </button>
  );
}

