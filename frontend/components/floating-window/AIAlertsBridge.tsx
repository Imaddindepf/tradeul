'use client';

/**
 * AIAlertsBridge — redirige `tradeul:open-ai-alerts` al AI Agent (pestaña
 * Mis workflows), en lugar de abrir una ventana flotante paralela.
 *
 * Las alertas viven en el canvas del agente: same DAG, rail de carpetas,
 * WorkflowInspector. El popup de fires (AIAlertFiresPopup) sigue existiendo
 * como toast; al hacer clic abre el Agent, no un panel aparte.
 */
import { useEffect } from 'react';
import { useFloatingWindowActions, useFloatingWindowsList } from '@/contexts/FloatingWindowContext';
import { AIAgentContent } from '@/components/ai-agent';

const AGENT_TITLE = 'AI Agent';

export function AIAlertsBridge() {
  const { openWindow, bringToFront, restoreWindow } = useFloatingWindowActions();
  const windows = useFloatingWindowsList();

  useEffect(() => {
    const openAgentWorkflows = () => {
      // Pedir al Agent que muestre la pestaña Mis workflows (aunque aún no esté montado).
      window.dispatchEvent(new CustomEvent('tradeul:ai-agent-show-workflows'));

      const existing = windows.find(w => w.title === AGENT_TITLE);
      if (existing) {
        if (existing.isMinimized) restoreWindow(existing.id);
        bringToFront(existing.id);
        return;
      }
      const screenWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
      const screenHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
      openWindow({
        title: AGENT_TITLE,
        content: <AIAgentContent />,
        width: 1100,
        height: 700,
        x: Math.max(50, screenWidth / 2 - 550),
        y: Math.max(70, screenHeight / 2 - 350),
        minWidth: 480,
        minHeight: 400,
      });
    };

    window.addEventListener('tradeul:open-ai-alerts', openAgentWorkflows);
    return () => window.removeEventListener('tradeul:open-ai-alerts', openAgentWorkflows);
  }, [openWindow, bringToFront, restoreWindow, windows]);

  return null;
}
