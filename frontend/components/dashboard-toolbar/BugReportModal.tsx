'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { X, Loader2 } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { Z_INDEX } from '@/lib/z-index';

interface BugReportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface UploadedImage {
  id: string;
  name: string;
  dataUrl: string;
  size: number;
}

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB per image
const MAX_FILES = 5;
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

const readAsDataUrl = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

/**
 * Modal (non-draggable) for collecting structured bug reports.
 * Users can describe the issue, paste or upload screenshots, and submit.
 * The payload is POSTed to /api/v1/bug-reports.
 */
export function BugReportModal({ isOpen, onClose }: BugReportModalProps) {
  const { getToken } = useAuth();

  const [description, setDescription] = useState('');
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null);
  const [mounted, setMounted] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setStatus(null);
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  const addFiles = useCallback(async (files: File[]) => {
    const accepted = files.filter((f) => {
      if (!ACCEPTED_TYPES.includes(f.type)) return false;
      if (f.size > MAX_FILE_SIZE) return false;
      return true;
    });
    if (accepted.length === 0) {
      setStatus({ text: 'Only PNG/JPEG/WebP/GIF under 5 MB are accepted.', tone: 'err' });
      return;
    }
    const slots = Math.max(0, MAX_FILES - images.length);
    const limited = accepted.slice(0, slots);
    const next: UploadedImage[] = [];
    for (const file of limited) {
      try {
        const dataUrl = await readAsDataUrl(file);
        next.push({
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          name: file.name || 'screenshot.png',
          dataUrl,
          size: file.size,
        });
      } catch (err) {
        console.warn('[BugReportModal] readAsDataUrl failed', err);
      }
    }
    if (next.length === 0) return;
    setImages((prev) => [...prev, ...next]);
    setStatus(null);
  }, [images.length]);

  useEffect(() => {
    if (!isOpen) return;
    const handlePaste = (e: ClipboardEvent) => {
      if (!dialogRef.current?.contains(e.target as Node)) return;
      const items = e.clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length > 0) {
        e.preventDefault();
        void addFiles(files);
      }
    };
    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [isOpen, addFiles]);

  const removeImage = useCallback((id: string) => {
    setImages((prev) => prev.filter((img) => img.id !== id));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (submitting) return;
    const trimmed = description.trim();
    if (trimmed.length < 10) {
      setStatus({ text: 'Please provide at least 10 characters of description.', tone: 'err' });
      return;
    }

    setSubmitting(true);
    setStatus(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      try {
        const token = await getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
      } catch {
        // Anonymous reports are still accepted server-side.
      }

      const response = await fetch(`${apiUrl}/api/v1/bug-reports`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({
          description: trimmed,
          images: images.map((img) => ({
            name: img.name,
            dataUrl: img.dataUrl,
            size: img.size,
          })),
          context: {
            url: typeof window !== 'undefined' ? window.location.href : '',
            userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
            viewport:
              typeof window !== 'undefined'
                ? { width: window.innerWidth, height: window.innerHeight }
                : null,
            timestamp: new Date().toISOString(),
          },
        }),
      });

      if (!response.ok) {
        const text = await response.text().catch(() => '');
        throw new Error(text || `HTTP ${response.status}`);
      }

      const data = await response.json().catch(() => ({}));
      setStatus({
        text: data?.id
          ? `Thanks! Bug report received (ref: ${data.id}).`
          : 'Thanks! Bug report received.',
        tone: 'ok',
      });
      setDescription('');
      setImages([]);
      setTimeout(() => onClose(), 1500);
    } catch (err) {
      console.error('[BugReportModal] submit failed', err);
      setStatus({
        text: `Submission failed: ${(err as Error).message || 'Unknown error'}`,
        tone: 'err',
      });
    } finally {
      setSubmitting(false);
    }
  }, [description, images, submitting, getToken, onClose]);

  if (!isOpen || !mounted) return null;

  const modalNode = (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 flex items-center justify-center"
        style={{ zIndex: Z_INDEX.DASHBOARD_OVERLAY }}
        onMouseDown={onClose}
      >
        <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />
        <motion.div
          ref={dialogRef}
          initial={{ scale: 0.96, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.96, opacity: 0 }}
          onMouseDown={(e) => e.stopPropagation()}
          className="relative w-[min(520px,92vw)] max-h-[90vh] overflow-y-auto bg-surface border border-border rounded-lg shadow-2xl p-6"
          style={{ fontFamily: 'var(--font-mono-selected)' }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="bug-report-title"
        >
          <button
            onClick={onClose}
            className="absolute top-3 right-3 p-1 rounded hover:bg-foreground/10 text-muted-fg hover:text-foreground transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>

          <h2 id="bug-report-title" className="text-lg font-semibold text-foreground mb-5">
            Report a Bug
          </h2>

          <label className="block text-xs text-muted-fg mb-2" htmlFor="bug-description">
            Description
          </label>
          <textarea
            ref={textareaRef}
            id="bug-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the bug you encountered... (state of the app, steps to reproduce, expected vs actual behavior, etc.)"
            className="w-full min-h-[180px] resize-y p-3 rounded border border-border bg-background text-sm text-foreground placeholder:text-muted-fg/70 focus:outline-none focus:ring-2 focus:ring-primary/50"
            disabled={submitting}
          />

          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={submitting || images.length >= MAX_FILES}
              className="px-3 py-1.5 rounded border border-border text-xs text-foreground hover:bg-foreground/5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Upload Images
            </button>
            <span className="text-xs text-muted-fg">
              or paste screenshots directly
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_TYPES.join(',')}
              multiple
              className="hidden"
              onChange={(e) => {
                const files = e.target.files ? Array.from(e.target.files) : [];
                if (files.length > 0) void addFiles(files);
                e.target.value = '';
              }}
            />
          </div>

          {images.length > 0 && (
            <div className="mt-3 grid grid-cols-3 gap-2">
              {images.map((img) => (
                <div
                  key={img.id}
                  className="relative group rounded border border-border overflow-hidden bg-background"
                >
                  <img
                    src={img.dataUrl}
                    alt={img.name}
                    className="w-full h-20 object-cover"
                  />
                  <button
                    onClick={() => removeImage(img.id)}
                    className="absolute top-1 right-1 p-0.5 rounded-full bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    aria-label="Remove image"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {status && (
            <p
              className={`text-xs mt-3 ${
                status.tone === 'ok' ? 'text-success' : 'text-danger'
              }`}
            >
              {status.text}
            </p>
          )}

          <div className="mt-6 flex justify-start">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              className="inline-flex items-center gap-2 px-4 py-2 rounded bg-success/80 hover:bg-success text-white text-sm font-medium transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitting && <Loader2 className="w-3 h-3 animate-spin" />}
              {submitting ? 'Submitting…' : 'Submit'}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );

  return createPortal(modalNode, document.body);
}
