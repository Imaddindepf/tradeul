'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import {
  useUserPreferencesStore,
  type Workspace,
  type WindowLayout,
} from '@/stores/useUserPreferencesStore';
import { useFloatingWindowActions } from '@/contexts/FloatingWindowContext';
import { Z_INDEX } from '@/lib/z-index';

interface LayoutOptionsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface LayoutExport {
  schema: 'tradeul.layout';
  version: 1;
  exportedAt: string;
  scope: 'full' | 'screen';
  workspaces: Workspace[];
  activeWorkspaceId?: string;
}

interface ScreenExport {
  schema: 'tradeul.screen';
  version: 1;
  exportedAt: string;
  workspace: Workspace;
}

const downloadJson = (data: unknown, filename: string) => {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
};

const isValidWindowLayout = (val: unknown): val is WindowLayout => {
  if (!val || typeof val !== 'object') return false;
  const v = val as Record<string, unknown>;
  return (
    typeof v.id === 'string' &&
    typeof v.title === 'string' &&
    typeof v.position === 'object' &&
    typeof v.size === 'object'
  );
};

const isValidWorkspace = (val: unknown): val is Workspace => {
  if (!val || typeof val !== 'object') return false;
  const v = val as Record<string, unknown>;
  return (
    typeof v.id === 'string' &&
    typeof v.name === 'string' &&
    Array.isArray(v.windowLayouts) &&
    v.windowLayouts.every(isValidWindowLayout)
  );
};

/**
 * Modal (non-draggable) that exposes save / restore controls
 * for layouts (all workspaces) and screens (single workspace).
 */
export function LayoutOptionsModal({ isOpen, onClose }: LayoutOptionsModalProps) {
  const workspaces = useUserPreferencesStore((s) => s.workspaces);
  const activeWorkspaceId = useUserPreferencesStore((s) => s.activeWorkspaceId);
  const saveWorkspaceLayouts = useUserPreferencesStore((s) => s.saveWorkspaceLayouts);
  const setActiveWorkspace = useUserPreferencesStore((s) => s.setActiveWorkspace);
  const createWorkspace = useUserPreferencesStore((s) => s.createWorkspace);
  const resetAll = useUserPreferencesStore((s) => s.resetAll);

  const { closeAllWindows } = useFloatingWindowActions();

  const layoutFileInput = useRef<HTMLInputElement>(null);
  const screenFileInput = useRef<HTMLInputElement>(null);
  const [feedback, setFeedback] = useState<{ text: string; tone: 'ok' | 'err' } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!feedback) return;
    const t = setTimeout(() => setFeedback(null), 3500);
    return () => clearTimeout(t);
  }, [feedback]);

  const handleExportLayout = useCallback(() => {
    const payload: LayoutExport = {
      schema: 'tradeul.layout',
      version: 1,
      exportedAt: new Date().toISOString(),
      scope: 'full',
      workspaces,
      activeWorkspaceId,
    };
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    downloadJson(payload, `tradeul-layout-${stamp}.json`);
    setFeedback({ text: `Exported ${workspaces.length} screen(s).`, tone: 'ok' });
  }, [workspaces, activeWorkspaceId]);

  const handleExportScreen = useCallback(() => {
    const active = workspaces.find((w) => w.id === activeWorkspaceId);
    if (!active) {
      setFeedback({ text: 'No active screen to export.', tone: 'err' });
      return;
    }
    const payload: ScreenExport = {
      schema: 'tradeul.screen',
      version: 1,
      exportedAt: new Date().toISOString(),
      workspace: active,
    };
    const slug = active.name.replace(/[^A-Za-z0-9-_]+/g, '-').toLowerCase() || 'screen';
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    downloadJson(payload, `tradeul-screen-${slug}-${stamp}.json`);
    setFeedback({
      text: `Exported screen "${active.name}" (${active.windowLayouts.length} window(s)).`,
      tone: 'ok',
    });
  }, [workspaces, activeWorkspaceId]);

  const handleImportLayout = useCallback(async (file: File) => {
    try {
      const raw = await file.text();
      const data = JSON.parse(raw) as Partial<LayoutExport>;
      if (data.schema !== 'tradeul.layout' || !Array.isArray(data.workspaces)) {
        throw new Error('Invalid layout file (schema mismatch).');
      }
      const valid = data.workspaces.filter(isValidWorkspace);
      if (valid.length === 0) throw new Error('No valid workspaces in file.');

      // Close all windows first so the new layout takes effect cleanly
      closeAllWindows();
      useUserPreferencesStore.setState({
        workspaces: valid,
        activeWorkspaceId:
          (data.activeWorkspaceId && valid.find((w) => w.id === data.activeWorkspaceId))
            ? data.activeWorkspaceId
            : (valid[0]?.id ?? 'main'),
        workspacesModifiedAt: Date.now(),
      });
      setFeedback({ text: `Imported ${valid.length} screen(s).`, tone: 'ok' });
    } catch (err) {
      console.error('[LayoutOptionsModal] import layout failed', err);
      setFeedback({ text: `Import failed: ${(err as Error).message}`, tone: 'err' });
    }
  }, [closeAllWindows]);

  const handleImportScreen = useCallback(async (file: File) => {
    try {
      const raw = await file.text();
      const data = JSON.parse(raw) as Partial<ScreenExport>;
      if (data.schema !== 'tradeul.screen' || !isValidWorkspace(data.workspace)) {
        throw new Error('Invalid screen file (schema mismatch).');
      }
      const incoming = data.workspace as Workspace;
      const newId = createWorkspace(incoming.name || 'Imported');
      saveWorkspaceLayouts(newId, incoming.windowLayouts);
      setActiveWorkspace(newId);
      setFeedback({
        text: `Imported screen "${incoming.name}" (${incoming.windowLayouts.length} window(s)).`,
        tone: 'ok',
      });
    } catch (err) {
      console.error('[LayoutOptionsModal] import screen failed', err);
      setFeedback({ text: `Import failed: ${(err as Error).message}`, tone: 'err' });
    }
  }, [createWorkspace, saveWorkspaceLayouts, setActiveWorkspace]);

  const handleClearScreen = useCallback(() => {
    closeAllWindows();
    saveWorkspaceLayouts(activeWorkspaceId, []);
    setFeedback({ text: 'Current screen cleared.', tone: 'ok' });
  }, [closeAllWindows, saveWorkspaceLayouts, activeWorkspaceId]);

  const handleResetAll = useCallback(() => {
    if (!confirmReset) {
      setConfirmReset(true);
      return;
    }
    closeAllWindows();
    resetAll();
    setConfirmReset(false);
    setFeedback({ text: 'All screens reset to defaults.', tone: 'ok' });
  }, [closeAllWindows, resetAll, confirmReset]);

  const handleFileInputChange = (handler: (file: File) => Promise<void>) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handler(file);
      e.target.value = '';
    };

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
          initial={{ scale: 0.96, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.96, opacity: 0 }}
          onMouseDown={(e) => e.stopPropagation()}
          className="relative w-[min(440px,92vw)] max-h-[90vh] overflow-y-auto bg-surface border border-border rounded-lg shadow-2xl p-6"
          style={{ fontFamily: 'var(--font-mono-selected)' }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="layout-options-title"
        >
          <button
            onClick={onClose}
            className="absolute top-3 right-3 p-1 rounded hover:bg-foreground/10 text-muted-fg hover:text-foreground transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>

          <h2 id="layout-options-title" className="text-lg font-semibold text-foreground mb-5">
            Layout Options
          </h2>

          <Section title="Save and Restore Layouts">
            <Button onClick={handleExportLayout}>Export Layout</Button>
            <Button onClick={() => layoutFileInput.current?.click()}>Import Layout</Button>
            <input
              ref={layoutFileInput}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={handleFileInputChange(handleImportLayout)}
            />
          </Section>

          <Section title="Save and Restore Screens">
            <Button onClick={handleExportScreen}>Export Current Screen</Button>
            <Button onClick={() => screenFileInput.current?.click()}>Import Additional Screen</Button>
            <input
              ref={screenFileInput}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={handleFileInputChange(handleImportScreen)}
            />
          </Section>

          <Section title="Reset Layout">
            <Button onClick={handleClearScreen} tone="warn">
              Clear This Screen
            </Button>
            <Button onClick={handleResetAll} tone="danger">
              {confirmReset ? 'Click again to confirm — Reset All Screens' : 'Reset All Screens'}
            </Button>
          </Section>

          {feedback && (
            <p
              className={`text-xs mt-3 ${
                feedback.tone === 'ok' ? 'text-success' : 'text-danger'
              }`}
            >
              {feedback.text}
            </p>
          )}

          <div className="mt-5 pt-4 border-t border-border">
            <Button onClick={onClose}>Cancel</Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );

  return createPortal(modalNode, document.body);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="text-sm font-medium text-foreground mb-2">{title}</h3>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function Button({
  children,
  onClick,
  tone = 'default',
}: {
  children: React.ReactNode;
  onClick: () => void;
  tone?: 'default' | 'warn' | 'danger';
}) {
  const toneCls =
    tone === 'danger'
      ? 'border-danger/60 text-danger bg-danger/10 hover:bg-danger/20'
      : tone === 'warn'
        ? 'border-warning/60 text-warning hover:bg-warning/10'
        : 'border-border text-foreground hover:bg-foreground/5';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full px-3 py-2 rounded border text-sm transition-colors ${toneCls}`}
    >
      {children}
    </button>
  );
}
