'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { X, Search, UserPlus, UserMinus, Shield, ShieldOff, Loader2, Crown, Users, Clock, XCircle } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { useChatStore, type ChatGroup } from '@/stores/useChatStore';
import { cn } from '@/lib/utils';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';

interface Member {
    user_id: string;
    user_name: string;
    user_avatar?: string;
    role: 'owner' | 'admin' | 'member';
    joined_at: string;
}

interface UserResult {
    id: string;
    username: string;
    first_name?: string;
    last_name?: string;
    image_url?: string;
}

interface PendingInvite {
    id: string;
    invitee_id: string;
    invitee_name?: string;
    inviter_id: string;
    created_at: string;
    expires_at: string;
}

interface GroupManagePanelProps {
    group: ChatGroup;
    onClose: () => void;
}

export function GroupManagePanel({ group, onClose }: GroupManagePanelProps) {
    const { getToken, userId } = useAuth();
    const { groups, setGroups } = useChatStore();

    const [members, setMembers] = useState<Member[]>([]);
    const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
    const [loadingMembers, setLoadingMembers] = useState(true);
    const [activeTab, setActiveTab] = useState<'members' | 'invite'>('members');

    // Invite state
    const [userSearch, setUserSearch] = useState('');
    const [userResults, setUserResults] = useState<UserResult[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [inviting, setInviting] = useState<string | null>(null);
    const [promoting, setPromoting] = useState<string | null>(null);
    const [removing, setRemoving] = useState<string | null>(null);
    const [cancellingInvite, setCancellingInvite] = useState<string | null>(null);

    const isOwner = group.owner_id === userId;
    const currentUserRole = members.find(m => m.user_id === userId)?.role;
    const isAdmin = currentUserRole === 'admin' || currentUserRole === 'owner';

    // Load members and pending invites
    useEffect(() => {
        async function loadData() {
            try {
                const token = await getToken();

                // Load members
                const membersRes = await fetch(`${CHAT_API_URL}/api/chat/groups/${group.id}/members`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (membersRes.ok) {
                    setMembers(await membersRes.json());
                }

                // Load pending invites
                const invitesRes = await fetch(`${CHAT_API_URL}/api/chat/invites/group/${group.id}/pending`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (invitesRes.ok) {
                    setPendingInvites(await invitesRes.json());
                }
            } catch (error) {
                console.error('Failed to load data:', error);
            } finally {
                setLoadingMembers(false);
            }
        }
        loadData();
    }, [group.id, getToken]);

    // Search users
    useEffect(() => {
        if (!userSearch.trim()) {
            setUserResults([]);
            return;
        }

        const timer = setTimeout(async () => {
            setSearchLoading(true);
            try {
                const token = await getToken();
                const res = await fetch(
                    `${CHAT_API_URL}/api/chat/users/search?q=${encodeURIComponent(userSearch)}&limit=10`,
                    { headers: { Authorization: `Bearer ${token}` } }
                );
                if (res.ok) {
                    const users = await res.json();
                    // Filter out existing members
                    const memberIds = new Set(members.map(m => m.user_id));
                    setUserResults(users.filter((u: UserResult) => !memberIds.has(u.id)));
                }
            } catch (error) {
                console.error('Failed to search users:', error);
            } finally {
                setSearchLoading(false);
            }
        }, 300);

        return () => clearTimeout(timer);
    }, [userSearch, getToken, members]);

    // Invite user
    const handleInvite = async (userToInvite: UserResult) => {
        setInviting(userToInvite.id);
        const inviteeName = userToInvite.username || userToInvite.first_name || 'Unknown';
        try {
            const token = await getToken();
            const res = await fetch(`${CHAT_API_URL}/api/chat/groups/${group.id}/invite/${userToInvite.id}`, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ invitee_name: inviteeName }),
            });
            if (res.ok) {
                // Remove from search results
                setUserResults(prev => prev.filter(u => u.id !== userToInvite.id));
                setUserSearch('');

                // Add to pending invites immediately (optimistic update)
                setPendingInvites(prev => [...prev, {
                    id: `temp_${userToInvite.id}`,
                    invitee_id: userToInvite.id,
                    invitee_name: inviteeName,
                    inviter_id: userId || '',
                    created_at: new Date().toISOString(),
                    expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
                }]);
            }
        } catch (error) {
            console.error('Failed to invite user:', error);
        } finally {
            setInviting(null);
        }
    };

    // Promote to admin
    const handlePromote = async (memberId: string) => {
        setPromoting(memberId);
        try {
            const token = await getToken();
            const res = await fetch(`${CHAT_API_URL}/api/chat/groups/${group.id}/members/${memberId}/promote`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                setMembers(prev => prev.map(m =>
                    m.user_id === memberId ? { ...m, role: 'admin' } : m
                ));
            }
        } catch (error) {
            console.error('Failed to promote member:', error);
        } finally {
            setPromoting(null);
        }
    };

    // Demote from admin
    const handleDemote = async (memberId: string) => {
        setPromoting(memberId);
        try {
            const token = await getToken();
            const res = await fetch(`${CHAT_API_URL}/api/chat/groups/${group.id}/members/${memberId}/demote`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                setMembers(prev => prev.map(m =>
                    m.user_id === memberId ? { ...m, role: 'member' } : m
                ));
            }
        } catch (error) {
            console.error('Failed to demote member:', error);
        } finally {
            setPromoting(null);
        }
    };

    // Remove member from group
    const handleRemove = async (memberId: string, memberName: string) => {
        const confirmed = window.confirm(`¿Eliminar a ${memberName} del grupo?`);
        if (!confirmed) return;

        setRemoving(memberId);
        try {
            const token = await getToken();
            const res = await fetch(`${CHAT_API_URL}/api/chat/groups/${group.id}/members/${memberId}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                setMembers(prev => prev.filter(m => m.user_id !== memberId));
            }
        } catch (error) {
            console.error('Failed to remove member:', error);
        } finally {
            setRemoving(null);
        }
    };

    // Check if current user can manage a specific member
    const canManage = (member: Member) => {
        if (member.user_id === userId) return false; // Can't manage self
        if (member.role === 'owner') return false; // Can't manage owner
        if (isOwner) return true; // Owner can manage everyone
        if (currentUserRole === 'admin' && member.role === 'member') return true; // Admin can manage members
        return false;
    };

    const canPromote = (member: Member) => {
        if (!canManage(member)) return false;
        return member.role === 'member'; // Can only promote members
    };

    const canDemote = (member: Member) => {
        if (member.role !== 'admin') return false;
        return isOwner; // Only owner can demote admins
    };

    const canRemove = (member: Member) => {
        if (member.user_id === userId) return false;
        if (member.role === 'owner') return false;
        if (isOwner) return true;
        if (currentUserRole === 'admin' && member.role === 'member') return true;
        return false;
    };

    // Cancel pending invite
    const handleCancelInvite = async (inviteeId: string) => {
        setCancellingInvite(inviteeId);
        try {
            const token = await getToken();
            const res = await fetch(`${CHAT_API_URL}/api/chat/invites/group/${group.id}/pending/${inviteeId}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                setPendingInvites(prev => prev.filter(i => i.invitee_id !== inviteeId));
            }
        } catch (error) {
            console.error('Failed to cancel invite:', error);
        } finally {
            setCancellingInvite(null);
        }
    };

    // Format time ago
    const timeAgo = (dateStr: string) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now.getTime() - date.getTime()) / 1000 / 60); // minutes
        if (diff < 60) return `${diff}m`;
        if (diff < 1440) return `${Math.floor(diff / 60)}h`;
        return `${Math.floor(diff / 1440)}d`;
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-primary" />
                    <span className="font-medium text-sm">{group.name}</span>
                </div>
                <button onClick={onClose} className="p-1 hover:bg-muted rounded text-muted-foreground">
                    <X className="w-4 h-4" />
                </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-border">
                <button
                    onClick={() => setActiveTab('members')}
                    className={cn(
                        "flex-1 px-3 py-1.5 text-xs transition-colors",
                        activeTab === 'members'
                            ? "border-b-2 border-primary text-primary"
                            : "text-muted-foreground hover:text-foreground"
                    )}
                >
                    Miembros ({members.length})
                </button>
                {isAdmin && (
                    <button
                        onClick={() => setActiveTab('invite')}
                        className={cn(
                            "flex-1 px-3 py-1.5 text-xs transition-colors",
                            activeTab === 'invite'
                                ? "border-b-2 border-primary text-primary"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        Invitar
                    </button>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-2">
                {activeTab === 'members' ? (
                    loadingMembers ? (
                        <div className="flex items-center justify-center py-8">
                            <Loader2 className="w-5 h-5 animate-spin text-primary" />
                        </div>
                    ) : (
                        <div className="space-y-1">
                            {members.map((member) => (
                                <div
                                    key={member.user_id}
                                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50"
                                >
                                    <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center text-[10px] font-medium">
                                        {member.user_name?.charAt(0).toUpperCase() || '?'}
                                    </div>
                                    <span className="flex-1 text-xs truncate">{member.user_name}</span>

                                    {/* Role badge */}
                                    {member.role === 'owner' && (
                                        <span title="Owner"><Crown className="w-3.5 h-3.5 text-amber-500" /></span>
                                    )}
                                    {member.role === 'admin' && (
                                        <span title="Admin"><Shield className="w-3.5 h-3.5 text-primary" /></span>
                                    )}

                                    {/* Action buttons */}
                                    <div className="flex items-center gap-0.5">
                                        {/* Promote button - for members */}
                                        {canPromote(member) && (
                                            <button
                                                onClick={() => handlePromote(member.user_id)}
                                                disabled={promoting === member.user_id}
                                                className="p-1 rounded transition-colors hover:bg-primary/20 text-primary"
                                                title="Hacer admin"
                                            >
                                                {promoting === member.user_id ? (
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                ) : (
                                                    <Shield className="w-3 h-3" />
                                                )}
                                            </button>
                                        )}

                                        {/* Demote button - only owner can demote admins */}
                                        {canDemote(member) && (
                                            <button
                                                onClick={() => handleDemote(member.user_id)}
                                                disabled={promoting === member.user_id}
                                                className="p-1 rounded transition-colors hover:bg-warning/20 text-warning"
                                                title="Quitar admin"
                                            >
                                                {promoting === member.user_id ? (
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                ) : (
                                                    <ShieldOff className="w-3 h-3" />
                                                )}
                                            </button>
                                        )}

                                        {/* Remove button */}
                                        {canRemove(member) && (
                                            <button
                                                onClick={() => handleRemove(member.user_id, member.user_name)}
                                                disabled={removing === member.user_id}
                                                className="p-1 rounded transition-colors hover:bg-danger/20 text-danger"
                                                title="Eliminar del grupo"
                                            >
                                                {removing === member.user_id ? (
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                ) : (
                                                    <UserMinus className="w-3 h-3" />
                                                )}
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}

                            {/* Pending Invites Section */}
                            {isAdmin && pendingInvites.length > 0 && (
                                <div className="mt-4 pt-3 border-t border-border">
                                    <div className="flex items-center gap-1.5 mb-2 text-[10px] text-muted-foreground">
                                        <Clock className="w-3 h-3" />
                                        <span>Invitaciones pendientes ({pendingInvites.length})</span>
                                    </div>
                                    {pendingInvites.map((invite) => (
                                        <div
                                            key={invite.invitee_id}
                                            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50"
                                        >
                                            <div className="w-6 h-6 rounded-full bg-warning/20 flex items-center justify-center text-[10px] font-medium text-warning">
                                                {(invite.invitee_name || '?')[0].toUpperCase()}
                                            </div>
                                            <span className="flex-1 text-xs truncate text-muted-foreground">
                                                {invite.invitee_name || invite.invitee_id.replace('user_', '').slice(0, 8)}
                                            </span>
                                            <span className="text-[9px] text-muted-foreground/60">
                                                {timeAgo(invite.created_at)}
                                            </span>
                                            <button
                                                onClick={() => handleCancelInvite(invite.invitee_id)}
                                                disabled={cancellingInvite === invite.invitee_id}
                                                className="p-1 rounded transition-colors hover:bg-danger/20 text-danger"
                                                title="Cancelar invitación"
                                            >
                                                {cancellingInvite === invite.invitee_id ? (
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                ) : (
                                                    <XCircle className="w-3 h-3" />
                                                )}
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )
                ) : (
                    <div className="space-y-3">
                        {/* Search input */}
                        <div className="relative">
                            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                            <input
                                type="text"
                                value={userSearch}
                                onChange={(e) => setUserSearch(e.target.value)}
                                placeholder="Buscar usuario..."
                                className="w-full pl-7 pr-3 py-1.5 text-xs bg-muted rounded focus:outline-none focus:ring-1 focus:ring-primary/50"
                            />
                        </div>

                        {/* Search results */}
                        {searchLoading ? (
                            <div className="flex items-center justify-center py-4">
                                <Loader2 className="w-4 h-4 animate-spin text-primary" />
                            </div>
                        ) : userResults.length > 0 ? (
                            <div className="space-y-1">
                                {userResults.map((user) => (
                                    <div
                                        key={user.id}
                                        className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50"
                                    >
                                        <div className="w-6 h-6 rounded-full bg-muted flex items-center justify-center text-[10px] font-medium">
                                            {user.username?.charAt(0).toUpperCase() || '?'}
                                        </div>
                                        <span className="flex-1 text-xs truncate">{user.username}</span>
                                        <button
                                            onClick={() => handleInvite(user)}
                                            disabled={inviting === user.id}
                                            className="p-1 rounded bg-primary/20 text-primary hover:bg-primary/30 transition-colors"
                                        >
                                            {inviting === user.id ? (
                                                <Loader2 className="w-3 h-3 animate-spin" />
                                            ) : (
                                                <UserPlus className="w-3 h-3" />
                                            )}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        ) : userSearch.trim() ? (
                            <p className="text-center text-xs text-muted-foreground py-4">
                                No se encontraron usuarios
                            </p>
                        ) : (
                            <p className="text-center text-xs text-muted-foreground py-4">
                                Escribe un nombre de usuario para buscar
                            </p>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

