'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '@/lib/utils';

export interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'danger' | 'warning';
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({ 
  isOpen, 
  title, 
  message, 
  confirmText = 'Confirm', 
  cancelText = 'Cancel', 
  variant = 'danger', 
  onConfirm, 
  onCancel 
}: ConfirmModalProps) {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center"
        onClick={onCancel}
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-black/40" />

        {/* Modal */}
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          onClick={(e) => e.stopPropagation()}
          className="relative bg-background border border-border rounded-lg shadow-xl p-4 max-w-[300px] w-full mx-4"
          style={{ fontFamily: 'var(--font-mono-selected)' }}
        >
          <div className="mb-4">
            <h3 className="text-sm font-medium mb-1">{title}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{message}</p>
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={onCancel}
              className="px-3 py-1.5 text-xs rounded border border-border hover:bg-muted transition-colors"
            >
              {cancelText}
            </button>
            <button
              onClick={onConfirm}
              className={cn(
                "px-3 py-1.5 text-xs rounded text-white transition-colors",
                variant === 'danger' ? "bg-danger hover:bg-danger/90" : "bg-warning hover:bg-warning/90"
              )}
            >
              {confirmText}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
