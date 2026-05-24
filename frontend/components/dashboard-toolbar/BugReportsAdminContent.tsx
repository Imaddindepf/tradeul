'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import {
  Bug,
  Check,
  CheckCircle2,
  ChevronLeft,
  ExternalLink,
  Loader2,
  RefreshCw,
  Trash2,
  X,
  AlertCircle,
} from 'lucide-react';
import { useIsAdmin } from '@/hooks/useIsAdmin';

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

type ReportStatus = 'open' | 'resolved' | 'dismissed';

interface StoredImage {
  filename: string;
  mime: string;
  size: number;
}

interface StoredReport {
  id: string;
  user: string | null;
  userEmail: string | null;
  userName: string | null;
  description: string;
  context: Record<string, any> | null;
  images: StoredImage[];
  imageCount: number;
  receivedAt: string;
  remoteAddr: string | null;
  status: ReportStatus;
  adminNote: string | null;
  resolvedAt: string | null;
  resolvedBy: string | null;
}

interface ListResponse {
  total: number;
  open: number;
  resolved: number;
  dismissed: number;
  items: StoredReport[];
  limit: number;
  offset: number;
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

const STATUS_FILTERS: Array<{ key: ReportStatus | 'all'; label: string }> = [
  { key: 'open', label: 'Open' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'dismissed', label: 'Dismissed' },
  { key: 'all', label: 'All' },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const now = Date.now();
    const diffMs = now - d.getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return d.toLocaleString();
  } catch {
    return iso;
  }
};

const statusBadgeCls = (status: ReportStatus): string => {
  switch (status) {
    case 'open':
      return 'bg-warning/15 text-warning border-warning/30';
    case 'resolved':
      return 'bg-success/15 text-success border-success/30';
    case 'dismissed':
      return 'bg-muted-fg/15 text-muted-fg border-muted-fg/30';
  }
};

// ----------------------------------------------------------------------------
// Component
// ----------------------------------------------------------------------------

export function BugReportsAdminContent() {
  const isAdmin = useIsAdmin();
  const { getToken } = useAuth();

  const [statusFilter, setStatusFilter] = useState<ReportStatus | 'all'>('open');
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const authFetch = useCallback(
    async (path: string, init?: RequestInit) => {
      const token = await getToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...((init?.headers as Record<string, string>) || {}),
      };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      return fetch(`${API_BASE}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      });
    },
    [getToken],
  );

  const fetchList = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: '50', offset: '0' });
      if (statusFilter !== 'all') params.set('status_filter', statusFilter);
      const res = await authFetch(`/api/v1/admin/bug-reports?${params.toString()}`);
      if (!res.ok) {
        if (res.status === 403) {
          throw new Error('Admin access required');
        }
        const txt = await res.text().catch(() => '');
        throw new Error(txt || `HTTP ${res.status}`);
      }
      const json: ListResponse = await res.json();
      setData(json);
      // Preserve selection if still in list, else clear
      if (selectedId && !json.items.find((it) => it.id === selectedId)) {
        setSelectedId(null);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [authFetch, statusFilter, isAdmin, selectedId]);

  useEffect(() => {
    if (isAdmin) {
      void fetchList();
    }
  }, [isAdmin, statusFilter, fetchList]);

  const items = data?.items ?? [];
  const selected = useMemo(
    () => items.find((it) => it.id === selectedId) ?? null,
    [items, selectedId],
  );

  // ---- mutations ----
  const updateStatus = useCallback(
    async (id: string, next: ReportStatus) => {
      try {
        const res = await authFetch(`/api/v1/admin/bug-reports/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ status: next }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await fetchList();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [authFetch, fetchList],
  );

  const saveNote = useCallback(
    async (id: string, note: string) => {
      try {
        const res = await authFetch(`/api/v1/admin/bug-reports/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ adminNote: note }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await fetchList();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [authFetch, fetchList],
  );

  const deleteReport = useCallback(
    async (id: string) => {
      try {
        const res = await authFetch(`/api/v1/admin/bug-reports/${id}`, {
          method: 'DELETE',
        });
        if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
        if (selectedId === id) setSelectedId(null);
        await fetchList();
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [authFetch, fetchList, selectedId],
  );

  // ---- gating ----
  if (!isAdmin) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center text-muted-fg text-sm gap-2">
        <AlertCircle className="w-8 h-8 text-danger" />
        <span>Admin access required</span>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex bg-surface text-foreground text-xs select-none">
      {/* === Left column: list === */}
      <div className="w-[42%] min-w-[280px] max-w-[420px] border-r border-border flex flex-col">
        <div className="px-2 py-1.5 border-b border-border flex items-center gap-1.5 bg-surface-hover">
          <Bug className="w-3.5 h-3.5 text-muted-fg" />
          <span className="font-medium">Bug Reports</span>
          <span className="ml-auto flex items-center gap-2 text-[10px] text-muted-fg">
            <span>{data?.total ?? 0} total</span>
            <button
              type="button"
              onClick={() => void fetchList()}
              disabled={loading}
              className="p-0.5 rounded hover:bg-foreground/10 transition-colors"
              title="Refresh"
              aria-label="Refresh"
            >
              {loading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <RefreshCw className="w-3 h-3" />
              )}
            </button>
          </span>
        </div>

        {/* Status tabs */}
        <div className="flex border-b border-border bg-surface">
          {STATUS_FILTERS.map((f) => {
            const count =
              f.key === 'all'
                ? data?.total ?? 0
                : (data?.[f.key] as number | undefined) ?? 0;
            const active = statusFilter === f.key;
            return (
              <button
                key={f.key}
                type="button"
                onClick={() => setStatusFilter(f.key)}
                className={`flex-1 px-2 py-1.5 text-[10px] border-b-2 transition-colors ${
                  active
                    ? 'border-primary text-primary bg-primary/5'
                    : 'border-transparent text-muted-fg hover:text-foreground hover:bg-foreground/5'
                }`}
              >
                {f.label} <span className="opacity-60">({count})</span>
              </button>
            );
          })}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="p-3 text-danger text-[11px] border-b border-border bg-danger/5 flex items-start gap-2">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {!loading && items.length === 0 && !error && (
            <div className="p-6 text-center text-muted-fg text-[11px]">
              No reports in this view.
            </div>
          )}
          {items.map((item) => {
            const isSel = selectedId === item.id;
            const preview = (item.description || '').replace(/\s+/g, ' ').slice(0, 120);
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedId(item.id)}
                className={`w-full text-left px-2 py-2 border-b border-border/60 transition-colors ${
                  isSel
                    ? 'bg-primary/10 border-l-2 border-l-primary'
                    : 'hover:bg-foreground/5'
                }`}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span
                    className={`px-1.5 py-px text-[9px] uppercase font-medium border rounded ${statusBadgeCls(
                      item.status,
                    )}`}
                  >
                    {item.status}
                  </span>
                  <span className="text-[10px] text-muted-fg truncate flex-1">
                    {item.userEmail || item.user || 'anonymous'}
                  </span>
                  {item.imageCount > 0 && (
                    <span className="text-[10px] text-muted-fg">
                      {item.imageCount} img
                    </span>
                  )}
                </div>
                <div className="text-[11px] leading-tight line-clamp-2">
                  {preview || '(no description)'}
                </div>
                <div className="text-[10px] text-muted-fg mt-1">
                  {formatDate(item.receivedAt)}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* === Right column: detail === */}
      <div className="flex-1 overflow-y-auto">
        {selected ? (
          <DetailView
            report={selected}
            onClose={() => setSelectedId(null)}
            onUpdateStatus={(next) => updateStatus(selected.id, next)}
            onSaveNote={(note) => saveNote(selected.id, note)}
            onDelete={() => deleteReport(selected.id)}
            authFetch={authFetch}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-muted-fg gap-2 p-6 text-center">
            <Bug className="w-8 h-8 opacity-30" />
            <span className="text-[11px]">Select a report to see details.</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Detail view
// ----------------------------------------------------------------------------

interface DetailViewProps {
  report: StoredReport;
  onClose: () => void;
  onUpdateStatus: (next: ReportStatus) => void;
  onSaveNote: (note: string) => void;
  onDelete: () => void;
  authFetch: (path: string, init?: RequestInit) => Promise<Response>;
}

function DetailView({
  report,
  onClose,
  onUpdateStatus,
  onSaveNote,
  onDelete,
  authFetch,
}: DetailViewProps) {
  const [note, setNote] = useState(report.adminNote ?? '');
  const [savingNote, setSavingNote] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({});
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  useEffect(() => {
    setNote(report.adminNote ?? '');
    setConfirmDelete(false);
  }, [report.id, report.adminNote]);

  // Fetch images as blobs so the admin Authorization header is sent.
  useEffect(() => {
    let cancelled = false;
    const objectUrls: string[] = [];

    const loadAll = async () => {
      const urls: Record<string, string> = {};
      for (const img of report.images) {
        try {
          const res = await authFetch(
            `/api/v1/admin/bug-reports/${report.id}/images/${encodeURIComponent(img.filename)}`,
          );
          if (!res.ok) continue;
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          objectUrls.push(url);
          urls[img.filename] = url;
        } catch {
          // Ignore individual image failures.
        }
      }
      if (!cancelled) setImageUrls(urls);
    };

    void loadAll();
    return () => {
      cancelled = true;
      objectUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [report.id, report.images, authFetch]);

  const handleSaveNote = useCallback(async () => {
    setSavingNote(true);
    try {
      await onSaveNote(note);
    } finally {
      setSavingNote(false);
    }
  }, [note, onSaveNote]);

  const ctx = report.context || {};
  const url = ctx.url as string | undefined;
  const userAgent = ctx.userAgent as string | undefined;
  const viewport = ctx.viewport as { width?: number; height?: number } | undefined;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-1.5 border-b border-border bg-surface-hover flex items-center gap-2">
        <button
          type="button"
          onClick={onClose}
          className="p-0.5 rounded hover:bg-foreground/10 transition-colors"
          title="Back to list"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <span
          className={`px-1.5 py-px text-[9px] uppercase font-medium border rounded ${statusBadgeCls(report.status)}`}
        >
          {report.status}
        </span>
        <span className="text-[10px] text-muted-fg font-mono">{report.id}</span>
        <div className="ml-auto flex items-center gap-1">
          {report.status !== 'resolved' && (
            <button
              type="button"
              onClick={() => onUpdateStatus('resolved')}
              className="px-2 py-1 text-[10px] rounded border border-success/40 text-success hover:bg-success/10 transition-colors inline-flex items-center gap-1"
            >
              <CheckCircle2 className="w-3 h-3" /> Resolve
            </button>
          )}
          {report.status !== 'dismissed' && report.status !== 'resolved' && (
            <button
              type="button"
              onClick={() => onUpdateStatus('dismissed')}
              className="px-2 py-1 text-[10px] rounded border border-border text-muted-fg hover:bg-foreground/5 transition-colors"
            >
              Dismiss
            </button>
          )}
          {report.status !== 'open' && (
            <button
              type="button"
              onClick={() => onUpdateStatus('open')}
              className="px-2 py-1 text-[10px] rounded border border-border text-muted-fg hover:bg-foreground/5 transition-colors"
            >
              Reopen
            </button>
          )}
          <button
            type="button"
            onClick={() => (confirmDelete ? onDelete() : setConfirmDelete(true))}
            className={`px-2 py-1 text-[10px] rounded border inline-flex items-center gap-1 transition-colors ${
              confirmDelete
                ? 'border-danger bg-danger text-white'
                : 'border-danger/40 text-danger hover:bg-danger/10'
            }`}
            title={confirmDelete ? 'Click again to confirm' : 'Delete report'}
          >
            <Trash2 className="w-3 h-3" />
            {confirmDelete ? 'Confirm delete' : 'Delete'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Meta */}
        <section className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
          <Meta label="User">
            {report.userName ? `${report.userName} ` : ''}
            <span className="text-muted-fg">{report.userEmail || report.user || 'anonymous'}</span>
          </Meta>
          <Meta label="Received">{new Date(report.receivedAt).toLocaleString()}</Meta>
          {url && (
            <Meta label="URL" className="col-span-2">
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline inline-flex items-center gap-1 break-all"
              >
                {url}
                <ExternalLink className="w-3 h-3 flex-shrink-0" />
              </a>
            </Meta>
          )}
          {userAgent && (
            <Meta label="User Agent" className="col-span-2">
              <span className="text-muted-fg text-[10px] break-all">{userAgent}</span>
            </Meta>
          )}
          {viewport?.width && viewport?.height && (
            <Meta label="Viewport">
              {viewport.width}×{viewport.height}
            </Meta>
          )}
          {report.resolvedAt && (
            <Meta label={report.status === 'resolved' ? 'Resolved' : 'Closed'}>
              {new Date(report.resolvedAt).toLocaleString()}
            </Meta>
          )}
        </section>

        {/* Description */}
        <section>
          <SectionTitle>Description</SectionTitle>
          <p className="text-[12px] whitespace-pre-wrap break-words bg-surface-hover rounded border border-border p-2.5">
            {report.description}
          </p>
        </section>

        {/* Images */}
        {report.images.length > 0 && (
          <section>
            <SectionTitle>Screenshots ({report.images.length})</SectionTitle>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
              {report.images.map((img) => {
                const objUrl = imageUrls[img.filename];
                return (
                  <button
                    key={img.filename}
                    type="button"
                    onClick={() => objUrl && setLightboxUrl(objUrl)}
                    className="relative aspect-video bg-background border border-border rounded overflow-hidden hover:border-primary transition-colors group"
                    title={img.filename}
                  >
                    {objUrl ? (
                      <img
                        src={objUrl}
                        alt={img.filename}
                        className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Loader2 className="w-4 h-4 animate-spin text-muted-fg" />
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {/* Admin note */}
        <section>
          <SectionTitle>Internal note</SectionTitle>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add an internal note (visible only to admins)…"
            className="w-full min-h-[80px] resize-y p-2 rounded border border-border bg-background text-[11px] focus:outline-none focus:ring-2 focus:ring-primary/40"
            disabled={savingNote}
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={handleSaveNote}
              disabled={savingNote || note === (report.adminNote ?? '')}
              className="px-2.5 py-1 text-[10px] rounded bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity inline-flex items-center gap-1"
            >
              {savingNote ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Check className="w-3 h-3" />
              )}
              Save note
            </button>
            {report.adminNote && (
              <span className="text-[10px] text-muted-fg">
                Last updated by admin
              </span>
            )}
          </div>
        </section>
      </div>

      {lightboxUrl && (
        <Lightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------
// Subcomponents
// ----------------------------------------------------------------------------

function Meta({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="text-[9px] uppercase text-muted-fg tracking-wide">{label}</div>
      <div className="text-[11px]">{children}</div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] uppercase tracking-wide text-muted-fg mb-1.5">
      {children}
    </h3>
  );
}

function Lightbox({ url, onClose }: { url: string; onClose: () => void }) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[10600] bg-black/85 backdrop-blur-md flex items-center justify-center p-6"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 p-1.5 rounded hover:bg-white/10 text-white"
        aria-label="Close"
      >
        <X className="w-5 h-5" />
      </button>
      <img
        src={url}
        alt="screenshot"
        onClick={(e) => e.stopPropagation()}
        className="max-w-[95vw] max-h-[90vh] rounded border border-white/10 shadow-2xl"
      />
    </div>
  );
}
