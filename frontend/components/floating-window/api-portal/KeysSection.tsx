'use client';

import { useState, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useAuthFetch } from '@/hooks/useAuthFetch';

interface KeyInfo {
  key_id: string;
  name: string;
  active: boolean;
  created_at: string;
  last_used_at: string | null;
  rate_limit: number;
}

interface NewKeyResult {
  key: string;
  info: KeyInfo;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
}

function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return formatDate(iso);
}

export function KeysSection() {
  const { authFetch } = useAuthFetch();
  const [keys, setKeys] = useState<KeyInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newKey, setNewKey] = useState<NewKeyResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const fetchKeys = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await authFetch('/api/v1/developer/keys');
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setKeys(data.keys);
    } catch (e: any) {
      setError(e.message || 'Failed to load keys');
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const res = await authFetch('/api/v1/developer/keys', {
        method: 'POST',
        body: JSON.stringify({ name: newName.trim() }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create key');
      }
      const data: NewKeyResult = await res.json();
      setNewKey(data);
      setNewName('');
      await fetchKeys();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (key_id: string) => {
    setRevoking(key_id);
    try {
      const res = await authFetch(`/api/v1/developer/keys/${key_id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to revoke key');
      await fetchKeys();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRevoking(null);
    }
  };

  const handleCopy = async () => {
    if (!newKey) return;
    await navigator.clipboard.writeText(newKey.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full">

      {/* New key banner — shown once after creation */}
      {newKey && (
        <div className="mx-2 mt-2 border border-border rounded p-2 bg-muted/20 flex-shrink-0">
          <div className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground/50 mb-1">
            New key — copy it now, it will not be shown again
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-[10px] font-mono text-foreground break-all select-all">
              {newKey.key}
            </code>
            <button
              onClick={handleCopy}
              className="px-2 py-1 text-[9px] font-medium border border-border rounded text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
            >
              {copied ? 'COPIED' : 'COPY'}
            </button>
            <button
              onClick={() => setNewKey(null)}
              className="px-2 py-1 text-[9px] text-muted-foreground/50 hover:text-muted-foreground transition-colors flex-shrink-0"
            >
              DISMISS
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-2 py-1 text-[10px] text-red-500 border-b border-border flex-shrink-0">
          {error}
        </div>
      )}

      {/* Create row */}
      <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border flex-shrink-0">
        <input
          type="text"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCreate()}
          placeholder="Key name (e.g. Bot prod)"
          className={cn(
            'flex-1 bg-transparent text-[10px] outline-none',
            'placeholder:text-muted-foreground/30 text-foreground',
          )}
        />
        <button
          onClick={handleCreate}
          disabled={creating || !newName.trim()}
          className="px-2.5 py-1 text-[9px] font-medium border border-border rounded text-muted-foreground hover:text-foreground hover:border-border transition-colors disabled:opacity-30"
        >
          {creating ? '...' : '+ NEW KEY'}
        </button>
      </div>

      {/* Keys table */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* Table header */}
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] px-2 py-1 border-b border-border">
          {['NAME', 'CREATED', 'LAST USED', 'STATUS', ''].map((h, i) => (
            <span key={i} className="text-[8px] font-medium uppercase tracking-wider text-muted-foreground/40">
              {h}
            </span>
          ))}
        </div>

        {loading && (
          <div className="px-2 py-3 text-[10px] text-muted-foreground/40">Loading…</div>
        )}

        {!loading && keys.length === 0 && (
          <div className="px-2 py-3 text-[10px] text-muted-foreground/40">
            No API keys yet. Create your first key above.
          </div>
        )}

        {keys.map(k => (
          <div
            key={k.key_id}
            className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] items-center px-2 py-[5px] border-b border-border hover:bg-muted/5 transition-colors"
          >
            <span className={cn('text-[10px] font-medium truncate', !k.active && 'line-through text-muted-foreground/40')}>
              {k.name}
            </span>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {formatDate(k.created_at)}
            </span>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {formatRelative(k.last_used_at)}
            </span>
            <span className={cn('text-[10px]', k.active ? 'text-green-500' : 'text-muted-foreground/40')}>
              {k.active ? 'live' : 'revoked'}
            </span>
            {k.active && (
              <button
                onClick={() => handleRevoke(k.key_id)}
                disabled={revoking === k.key_id}
                className="text-[9px] text-muted-foreground/30 hover:text-red-500 transition-colors disabled:opacity-30 px-1"
              >
                {revoking === k.key_id ? '…' : 'revoke'}
              </button>
            )}
            {!k.active && <span />}
          </div>
        ))}
      </div>

      {/* Footer note */}
      <div className="px-2 py-1.5 border-t border-border flex-shrink-0">
        <span className="text-[9px] text-muted-foreground/30">
          Keys are stored as SHA-256 hash · {keys.filter(k => k.active).length} active · rate limit {keys[0]?.rate_limit ?? 120} req/min
        </span>
      </div>
    </div>
  );
}
