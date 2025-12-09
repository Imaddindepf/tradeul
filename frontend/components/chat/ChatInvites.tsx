'use client';

import React, { useState } from 'react';
import { Check, X, Users, Loader2 } from 'lucide-react';
import { useAuth, useUser } from '@clerk/nextjs';
import { useChatStore } from '@/stores/useChatStore';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL || 'https://chat.tradeul.com';

export function ChatInvites() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const { invites, removeInvite, groups, setGroups, setActiveTarget } = useChatStore();
  const [loading, setLoading] = useState<string | null>(null);

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
                <span className="text-muted-foreground">{invite.inviter_name}</span>
                {' te invitó a '}
                <span className="font-medium">{invite.group_name}</span>
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

