'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { Loader2, Hash, Users, Plus, X, Search, ChevronDown, ChevronRight, MoreVertical, LogOut, Trash2, Settings, ExternalLink } from 'lucide-react';
import { useAuth, useUser } from '@clerk/nextjs';
import { openChatWindow } from '@/lib/window-injector';
import { useChatStore, selectActiveChannel, selectActiveGroup, selectOnlineCount } from '@/stores/useChatStore';
import { useChatWebSocket } from '@/hooks/useChatWebSocket';
import { ChatMessages } from './ChatMessages';
import { ChatInput } from './ChatInput';
import { ChatInvites } from './ChatInvites';
import { GroupManagePanel } from './GroupManagePanel';
import { cn } from '@/lib/utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://tradeul.com';

interface UserResult {
  id: string;
  username: string;
  email?: string;
  imageUrl?: string;
}

export function ChatContent() {
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateGroup, setShowCreateGroup] = useState(false);
  const [groupName, setGroupName] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [userResults, setUserResults] = useState<UserResult[]>([]);
  const [selectedMembers, setSelectedMembers] = useState<UserResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [expandedDMs, setExpandedDMs] = useState(true);
  const [expandedChannels, setExpandedChannels] = useState(true);
  const [showGroupMenu, setShowGroupMenu] = useState(false);
  const [showManagePanel, setShowManagePanel] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  
  const { getToken, isSignedIn, userId } = useAuth();
  const { user } = useUser();
  
  const { 
    isConnected,
    channels, 
    groups, 
    activeTarget, 
    setActiveTarget, 
    setChannels, 
    setGroups 
  } = useChatStore();
  
  const activeChannel = useChatStore(selectActiveChannel);
  const activeGroup = useChatStore(selectActiveGroup);
  const onlineCount = useChatStore(selectOnlineCount);
  
  useChatWebSocket();

  // Fetch channels and groups
  useEffect(() => {
    async function loadData() {
      try {
        // Get token for authenticated requests
        const token = isSignedIn ? await getToken() : null;
        const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

        const [channelsRes, groupsRes] = await Promise.all([
          fetch(`${CHAT_API_URL}/api/chat/channels`),
          token 
            ? fetch(`${CHAT_API_URL}/api/chat/groups`, { headers: authHeaders })
            : Promise.resolve({ ok: false } as Response),
        ]);

        if (channelsRes.ok) {
          const data = await channelsRes.json();
          setChannels(data);
          if (!activeTarget && data.length > 0) {
            const general = data.find((c: any) => c.name === 'general') || data[0];
            setActiveTarget({ type: 'channel', id: general.id });
          }
        }

        if (groupsRes.ok) {
          const data = await groupsRes.json();
          setGroups(data);
        }
      } catch (error) {
        console.error('Failed to load chat data:', error);
      } finally {
        setIsLoading(false);
      }
    }

    loadData();
  }, [setChannels, setGroups, setActiveTarget, activeTarget, isSignedIn, getToken]);

  // Search users
  useEffect(() => {
    if (!userSearch || userSearch.length < 2) {
      setUserResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const token = await getToken();
        const response = await fetch(
          `${CHAT_API_URL}/api/chat/users/search?q=${encodeURIComponent(userSearch)}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (response.ok) {
          const data = await response.json();
          // Filter out already selected members
          const filtered = data.filter((u: UserResult) => 
            !selectedMembers.some(m => m.id === u.id)
          );
          setUserResults(filtered);
        }
      } catch (err) {
        console.error('User search error:', err);
      } finally {
        setSearchLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [userSearch, getToken, selectedMembers]);

  // Add member
  const addMember = useCallback((user: UserResult) => {
    setSelectedMembers(prev => [...prev, user]);
    setUserSearch('');
    setUserResults([]);
  }, []);

  // Remove member
  const removeMember = useCallback((userId: string) => {
    setSelectedMembers(prev => prev.filter(m => m.id !== userId));
  }, []);

  // Create group
  const handleCreateGroup = async () => {
    if (selectedMembers.length === 0 || creating) return;
    
    setCreating(true);
    try {
      const token = await getToken();
      const response = await fetch(`${CHAT_API_URL}/api/chat/groups`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: groupName || `Chat with ${selectedMembers.map(m => m.username).join(', ')}`,
          member_ids: selectedMembers.map(m => m.id),
        }),
      });

      if (response.ok) {
        const group = await response.json();
        setGroups([...groups, group]);
        setActiveTarget({ type: 'group', id: group.id });
        setShowCreateGroup(false);
        setGroupName('');
        setSelectedMembers([]);
      }
    } catch (error) {
      console.error('Failed to create group:', error);
    } finally {
      setCreating(false);
    }
  };

  // Leave group (remove self from members)
  const handleLeaveGroup = async () => {
    if (!activeGroup || actionLoading) return;
    
    const confirmed = window.confirm('¿Seguro que quieres salir del grupo?');
    if (!confirmed) return;
    
    setActionLoading(true);
    try {
      const token = await getToken();
      const response = await fetch(
        `${CHAT_API_URL}/api/chat/groups/${activeGroup.id}/members/${userId}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        setGroups(groups.filter(g => g.id !== activeGroup.id));
        setActiveTarget(channels[0] ? { type: 'channel', id: channels[0].id } : null);
        setShowGroupMenu(false);
      }
    } catch (error) {
      console.error('Failed to leave group:', error);
    } finally {
      setActionLoading(false);
    }
  };

  // Pop out to new window
  const handlePopOut = async () => {
    try {
      const token = await getToken();
      if (!token) return;
      
      const wsUrl = process.env.NEXT_PUBLIC_CHAT_WS_URL || 'wss://wschat.tradeul.com';
      
      openChatWindow(
        {
          wsUrl,
          apiUrl: CHAT_API_URL,
          token,
          userId: userId || '',
          userName: user?.username || user?.fullName || user?.firstName || 'User',
          userAvatar: user?.imageUrl,
          activeTarget: activeTarget || undefined,
        },
        {
          title: 'Community Chat - Tradeul',
          width: 950,
          height: 700,
          centered: true,
        }
      );
    } catch (error) {
      console.error('Failed to open chat window:', error);
    }
  };

  // Delete group (owner only)
  const handleDeleteGroup = async () => {
    if (!activeGroup || actionLoading) return;
    
    const confirmed = window.confirm('¿Eliminar grupo permanentemente? Esto borrará todos los mensajes.');
    if (!confirmed) return;
    
    setActionLoading(true);
    try {
      const token = await getToken();
      const response = await fetch(
        `${CHAT_API_URL}/api/chat/groups/${activeGroup.id}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        setGroups(groups.filter(g => g.id !== activeGroup.id));
        setActiveTarget(channels[0] ? { type: 'channel', id: channels[0].id } : null);
        setShowGroupMenu(false);
      }
    } catch (error) {
      console.error('Failed to delete group:', error);
    } finally {
      setActionLoading(false);
    }
  };

  const activeName = activeChannel?.name || activeGroup?.name || '';
  const isGroup = activeTarget?.type === 'group';
  const isGroupOwner = activeGroup?.owner_id === userId;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-background">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex h-full bg-background text-xs" style={{ fontFamily: 'var(--font-mono-selected)' }}>
      {/* Sidebar */}
      <div className="w-36 border-r border-border flex flex-col bg-muted/20 overflow-hidden">
        {/* DMs / Groups Section */}
        <div className="p-1.5 border-b border-border">
          <div className="flex items-center justify-between px-1 mb-1">
            <button 
              onClick={() => setExpandedDMs(!expandedDMs)}
              className="flex items-center gap-0.5 text-[9px] font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground"
            >
              {expandedDMs ? <ChevronDown className="w-2.5 h-2.5" /> : <ChevronRight className="w-2.5 h-2.5" />}
              DMs / Groups
            </button>
            <button 
              onClick={() => setShowCreateGroup(true)}
              className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
              title="New conversation"
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>
          
          {expandedDMs && groups.length > 0 && (
            <div className="space-y-px">
              {groups.map((group) => (
                <button
                  key={group.id}
                  onClick={() => setActiveTarget({ type: 'group', id: group.id })}
                  className={cn(
                    "w-full flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors text-left",
                    activeTarget?.type === 'group' && activeTarget.id === group.id
                      ? "bg-primary text-white" 
                      : "hover:bg-muted text-foreground"
                  )}
                >
                  <Users className="w-2.5 h-2.5 shrink-0" />
                  <span className="truncate">{group.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Public Channels */}
        <div className="p-1.5 flex-1 overflow-y-auto">
          <button 
            onClick={() => setExpandedChannels(!expandedChannels)}
            className="flex items-center gap-0.5 text-[9px] font-semibold text-muted-foreground uppercase tracking-wider mb-1 px-1 hover:text-foreground"
          >
            {expandedChannels ? <ChevronDown className="w-2.5 h-2.5" /> : <ChevronRight className="w-2.5 h-2.5" />}
            Public Channels
          </button>
          
          {expandedChannels && (
            <div className="space-y-px">
              {channels.map((channel) => (
                <button
                  key={channel.id}
                  onClick={() => setActiveTarget({ type: 'channel', id: channel.id })}
                  className={cn(
                    "w-full flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors text-left",
                    activeTarget?.type === 'channel' && activeTarget.id === channel.id
                      ? "bg-primary text-white" 
                      : "hover:bg-muted text-foreground"
                  )}
                >
                  <Hash className="w-2.5 h-2.5 shrink-0" />
                  <span className="truncate">{channel.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Connection Status */}
        <div className="p-1.5 border-t border-border">
          <div className="flex items-center gap-1 px-1 text-[9px] text-muted-foreground">
            <span className={cn(
              "w-1.5 h-1.5 rounded-full",
              isConnected ? "bg-success" : "bg-danger animate-pulse"
            )} />
            {isConnected ? 'OK' : '...'}
          </div>
        </div>
      </div>

      {/* Main Area - Chat, Create Group, or Manage Group */}
      {showManagePanel && activeGroup ? (
        <div className="flex-1 flex flex-col min-w-0 p-3">
          <GroupManagePanel 
            group={activeGroup} 
            onClose={() => setShowManagePanel(false)} 
          />
        </div>
      ) : showCreateGroup ? (
        <div className="flex-1 flex flex-col min-w-0 p-3">
          {/* Header */}
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium">Start a conversation</h2>
            <button 
              onClick={() => {
                setShowCreateGroup(false);
                setGroupName('');
                setSelectedMembers([]);
                setUserSearch('');
              }}
              className="p-1 rounded hover:bg-muted text-muted-foreground"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex gap-4 flex-1">
            {/* Left: Search & Add */}
            <div className="flex-1">
              {/* Group Name (optional) */}
              <div className="mb-3">
                <label className="text-[10px] text-muted-foreground mb-1 block">Group name (optional)</label>
                <input
                  type="text"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  placeholder="My trading group..."
                  className="w-full px-2 py-1.5 text-xs bg-muted rounded border-0 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* User Search */}
              <div className="mb-3">
                <label className="text-[10px] text-muted-foreground mb-1 block">Invite:</label>
                <div className="relative">
                  <input
                    type="text"
                    value={userSearch}
                    onChange={(e) => setUserSearch(e.target.value)}
                    placeholder="Search for a user..."
                    className="w-full px-2 py-1.5 text-xs bg-muted rounded border-0 focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  {searchLoading && (
                    <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 animate-spin text-muted-foreground" />
                  )}
                </div>

                {/* Search Results */}
                {userResults.length > 0 && (
                  <div className="mt-1 border border-border rounded bg-background shadow-lg max-h-32 overflow-y-auto">
                    {userResults.map((user) => (
                      <button
                        key={user.id}
                        onClick={() => addMember(user)}
                        className="w-full px-2 py-1.5 text-xs text-left hover:bg-muted flex items-center gap-2"
                      >
                        <div className="w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center text-[9px] font-medium">
                          {user.username?.[0]?.toUpperCase() || '?'}
                        </div>
                        <span>{user.username}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-4">
                <button
                  onClick={() => {
                    setShowCreateGroup(false);
                    setGroupName('');
                    setSelectedMembers([]);
                  }}
                  className="px-3 py-1.5 text-xs rounded bg-muted hover:bg-muted/80"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateGroup}
                  disabled={selectedMembers.length === 0 || creating}
                  className={cn(
                    "px-3 py-1.5 text-xs rounded transition-colors",
                    selectedMembers.length > 0
                      ? "bg-primary text-white hover:bg-primary/90"
                      : "bg-muted text-muted-foreground cursor-not-allowed"
                  )}
                >
                  {creating ? 'Creating...' : 'Create Group'}
                </button>
              </div>
            </div>

            {/* Right: Members List */}
            <div className="w-40 border-l border-border pl-4">
              <h3 className="text-[10px] text-muted-foreground mb-2">Members:</h3>
              {selectedMembers.length === 0 ? (
                <p className="text-[10px] text-muted-foreground/60 italic">No members yet</p>
              ) : (
                <div className="space-y-1">
                  {selectedMembers.map((member) => (
                    <div key={member.id} className="flex items-center justify-between group">
                      <span className="text-[11px]">- {member.username}</span>
                      <button
                        onClick={() => removeMember(member.id)}
                        className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-muted rounded"
                      >
                        <X className="w-2.5 h-2.5 text-muted-foreground" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="h-7 px-2 flex items-center gap-2 border-b border-border bg-muted/30">
            <div className="flex items-center gap-1">
              {isGroup ? (
                <Users className="w-3 h-3 text-muted-foreground" />
              ) : (
                <Hash className="w-3 h-3 text-muted-foreground" />
              )}
              <span className="font-medium text-xs">{activeName}</span>
            </div>
            <div className="flex items-center gap-1 text-[9px] text-muted-foreground ml-auto">
              <span className="w-1.5 h-1.5 rounded-full bg-success" />
              {onlineCount}
            </div>
            
            {/* Pop out button */}
            <button
              onClick={handlePopOut}
              className="p-1 hover:bg-muted rounded transition-colors"
              title="Abrir en ventana nueva"
            >
              <ExternalLink className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
            
            {/* Group menu */}
            {isGroup && (
              <div className="relative">
                <button
                  onClick={() => setShowGroupMenu(!showGroupMenu)}
                  className="p-1 hover:bg-muted rounded transition-colors"
                >
                  <MoreVertical className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
                
                {showGroupMenu && (
                  <>
                    <div 
                      className="fixed inset-0 z-10" 
                      onClick={() => setShowGroupMenu(false)} 
                    />
                    <div className="absolute right-0 top-full mt-1 bg-background border border-border rounded shadow-lg z-20 py-1 min-w-[140px]">
                      {/* Manage group - owner and admins */}
                      <button
                        onClick={() => {
                          setShowManagePanel(true);
                          setShowGroupMenu(false);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-muted transition-colors"
                      >
                        <Settings className="w-3 h-3" />
                        Gestionar grupo
                      </button>

                      {/* Leave/Delete */}
                      {isGroupOwner ? (
                        <button
                          onClick={handleDeleteGroup}
                          disabled={actionLoading}
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-danger hover:bg-danger/10 transition-colors"
                        >
                          <Trash2 className="w-3 h-3" />
                          Eliminar grupo
                        </button>
                      ) : (
                        <button
                          onClick={handleLeaveGroup}
                          disabled={actionLoading}
                          className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-warning hover:bg-warning/10 transition-colors"
                        >
                          <LogOut className="w-3 h-3" />
                          Salir del grupo
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Pending Invites */}
          <ChatInvites />

          {/* Messages */}
          <ChatMessages />

          {/* Input */}
          <ChatInput />
        </div>
      )}
    </div>
  );
}
