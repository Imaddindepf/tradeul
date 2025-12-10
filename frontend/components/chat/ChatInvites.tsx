'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Check, X, Users, Loader2 } from 'lucide-react';
import { useAuth, useUser } from '@clerk/nextjs';
import { useChatStore } from '@/stores/useChatStore';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';

export function ChatInvites() {
  const { getToken, isSignedIn } = useAuth();
  const { user } = useUser();
  const { invites, addInvite, removeInvite, groups, setGroups, setActiveTarget } = useChatStore();
  const [loading, setLoading] = useState<string | null>(null);
  const hasFetched = useRef(false);

  // Load pending invites on mount
  useEffect(() => {
    if (!isSignedIn || hasFetched.current) return;
    hasFetched.current = true;

    const fetchInvites = async () => {
      try {
        const token = await getToken();
        const res = await fetch(`${CHAT_API_URL}/api/chat/invites`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          // Add each invite to store (avoiding duplicates)
          for (const inv of data) {
            addInvite({
              id: inv.id,
              group_id: inv.group_id,
              group_name: inv.group_name,
              inviter_id: inv.inviter_id,
              inviter_name: inv.inviter_name,
              status: inv.status,
              created_at: inv.created_at,
              expires_at: inv.expires_at,
            });
          }
        }
      } catch (error) {
        console.error('Failed to fetch invites:', error);
      }
    };

    fetchInvites();
  }, [isSignedIn, getToken, addInvite]);

  const handleAccept = async (invite: typeof invites[0]) => {
    setLoading(invite.group_id);
    try {
      const token = await getToken();
      const displayName = user?.username || user?.fullName || user?.firstName || 'Usuario';
      
      const response = await fetch(`${CHAT_API_URL}/api/chat/invites/group/${invite.group_id}/accept`, {
        method: 'POST',
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_name: displayName }),
      });

      if (response.ok) {
        const group = await response.json();
        // Add group to list and remove invite
        setGroups([...groups, group]);
        removeInvite(invite.group_id);
        // Navigate to the new group
        setActiveTarget({ type: 'group', id: invite.group_id });
      }
    } catch (error) {
      console.error('Failed to accept invite:', error);
    } finally {
      setLoading(null);
    }
  };

  const handleDecline = async (invite: typeof invites[0]) => {
    setLoading(invite.group_id);
    try {
      const token = await getToken();
      await fetch(`${CHAT_API_URL}/api/chat/invites/group/${invite.group_id}/decline`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      removeInvite(invite.group_id);
    } catch (error) {
      console.error('Failed to decline invite:', error);
    } finally {
      setLoading(null);
    }
  };

  if (invites.length === 0) return null;

  return (
    <div className="border-b border-border bg-primary/5 p-2">
      <AnimatePresence>
        {invites.map((invite) => (
          <motion.div
            key={invite.id}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-2 p-1.5 bg-background rounded border border-border mb-1 last:mb-0"
          >
            <Users className="w-4 h-4 text-primary shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[11px] truncate">
                <span className="text-muted-foreground font-medium">{invite.inviter_name || 'Alguien'}</span>
                {' te invitó a '}
                <span className="font-medium text-primary">{invite.group_name}</span>
              </p>
            </div>
            
            {loading === invite.group_id ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
            ) : (
              <div className="flex gap-1">
                <button
                  onClick={() => handleAccept(invite)}
                  className="p-1 rounded bg-success/20 text-success hover:bg-success/30 transition-colors"
                  title="Aceptar"
                >
                  <Check className="w-3 h-3" />
                </button>
                <button
                  onClick={() => handleDecline(invite)}
                  className="p-1 rounded bg-danger/20 text-danger hover:bg-danger/30 transition-colors"
                  title="Rechazar"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

