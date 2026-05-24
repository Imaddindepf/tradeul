'use client';

import { useRef, useState } from 'react';
import { LayoutGrid, Lock, Unlock, Bug, Maximize2, Minimize2, Shield } from 'lucide-react';
import {
  useUserPreferencesStore,
  selectPanelLocks,
} from '@/stores/useUserPreferencesStore';
import { useIsAdmin } from '@/hooks/useIsAdmin';
import { useFloatingWindowActions, useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { LayoutOptionsModal } from './LayoutOptionsModal';
import { BugReportModal } from './BugReportModal';
import { LockPopover } from './LockPopover';
import { useFullscreen } from './useFullscreen';
import { BugReportsAdminContent } from './BugReportsAdminContent';

const ADMIN_WINDOW_ID = 'bug-reports-admin';
const ADMIN_WINDOW_TITLE = 'Bug Reports Admin';

/**
 * Bottom-right toolbar shown inside the workspace tabs bar.
 * Provides quick access to layout options, panel lock toggles,
 * bug reporting and fullscreen toggle — TradingView-style.
 *
 * The admin shield button is only rendered when the current user has
 * `roles: ["admin"]` in their Clerk publicMetadata. Backend endpoints
 * also enforce this, so the button is purely a cosmetic gate.
 */
export function DashboardToolbar() {
  const panelLocks = useUserPreferencesStore(selectPanelLocks);
  const anyLockActive = panelLocks.movement || panelLocks.open || panelLocks.close;

  const lockBtnRef = useRef<HTMLButtonElement>(null);
  const [showLockPopover, setShowLockPopover] = useState(false);
  const [showLayoutModal, setShowLayoutModal] = useState(false);
  const [showBugModal, setShowBugModal] = useState(false);

  const { isFullscreen, toggle: toggleFullscreen } = useFullscreen();
  const isAdmin = useIsAdmin();
  const { openWindow, bringToFront, restoreWindow } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();

  const handleOpenAdminPanel = () => {
    const existing = windows.find((w) => w.id === ADMIN_WINDOW_ID);
    if (existing) {
      if (existing.isMinimized) restoreWindow(ADMIN_WINDOW_ID);
      bringToFront(ADMIN_WINDOW_ID);
      return;
    }
    openWindow({
      id: ADMIN_WINDOW_ID,
      title: ADMIN_WINDOW_TITLE,
      content: <BugReportsAdminContent />,
      width: 1080,
      height: 640,
      minWidth: 720,
      minHeight: 420,
      x: 120,
      y: 80,
    });
  };

  return (
    <>
      <div className="flex items-center h-full pr-1.5 gap-0.5 select-none">
        <ToolbarButton
          label="Layout Options"
          onClick={() => setShowLayoutModal(true)}
        >
          <LayoutGrid className="w-3.5 h-3.5" />
        </ToolbarButton>

        <ToolbarButton
          label="Lock Options"
          buttonRef={lockBtnRef}
          active={anyLockActive}
          onClick={() => setShowLockPopover((v) => !v)}
        >
          {anyLockActive ? (
            <Lock className="w-3.5 h-3.5" />
          ) : (
            <Unlock className="w-3.5 h-3.5" />
          )}
        </ToolbarButton>

        <ToolbarButton
          label="Report a Bug"
          onClick={() => setShowBugModal(true)}
        >
          <Bug className="w-3.5 h-3.5" />
        </ToolbarButton>

        {isAdmin && (
          <ToolbarButton
            label="Bug Reports Admin"
            onClick={handleOpenAdminPanel}
          >
            <Shield className="w-3.5 h-3.5" />
          </ToolbarButton>
        )}

        <ToolbarButton
          label={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
          onClick={toggleFullscreen}
        >
          {isFullscreen ? (
            <Minimize2 className="w-3.5 h-3.5" />
          ) : (
            <Maximize2 className="w-3.5 h-3.5" />
          )}
        </ToolbarButton>
      </div>

      <LockPopover
        anchorEl={lockBtnRef.current}
        isOpen={showLockPopover}
        onClose={() => setShowLockPopover(false)}
      />
      <LayoutOptionsModal
        isOpen={showLayoutModal}
        onClose={() => setShowLayoutModal(false)}
      />
      <BugReportModal
        isOpen={showBugModal}
        onClose={() => setShowBugModal(false)}
      />
    </>
  );
}

interface ToolbarButtonProps {
  label: string;
  active?: boolean;
  buttonRef?: React.RefObject<HTMLButtonElement>;
  onClick: () => void;
  children: React.ReactNode;
}

function ToolbarButton({ label, active, buttonRef, onClick, children }: ToolbarButtonProps) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`inline-flex items-center justify-center w-6 h-6 rounded transition-colors ${
        active
          ? 'text-primary bg-primary/10'
          : 'text-muted-fg hover:text-foreground hover:bg-foreground/5'
      }`}
    >
      {children}
    </button>
  );
}
