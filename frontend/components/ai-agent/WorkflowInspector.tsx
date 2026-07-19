'use client';

/**
 * WorkflowInspector — el detalle completo de un workflow armado, dentro del
 * canvas (la antigua ventana flotante "AI Alerts" fusionada aquí).
 *
 * Reusa el mismo shell del inspector de nodo (InspectorModal): tabs dinámicos
 * de Resumen / Output / Código. Los artifacts se construyen en el cliente a
 * partir del spec + el historial real de disparos (REST /api/alerts/{id}/fires)
 * + la última captura si es un workflow programado.
 */
import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { Archive, Pause, Play } from 'lucide-react';
import {
  type AlertSpec, type AlertFire, archiveAlert, armAlert, fmtCooldown,
  formatPriceLevel, formatUniverse, listFires, pauseAlert,
} from '@/lib/aiAlerts';
import { useAIAlertFiresStore } from '@/stores/useAIAlertFiresStore';
import type { Artifact } from './types';
import { InspectorModal } from './NodeInspector';

const TIER_LABELS: Record<string, string> = {
  event_match: 'evento en vivo',
  sequence: 'secuencia',
  membership: 'ranking',
  agentic: 'workflow',
  scheduled: 'programado',
};

function fmtWhen(epoch: number): string {
  return new Date(epoch * 1000).toLocaleString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function buildArtifacts(spec: AlertSpec, fires: AlertFire[] | null): Artifact[] {
  const arts: Artifact[] = [];

  if (spec.paraphrase) {
    arts.push({ kind: 'summary', title: 'Qué vigila', text: spec.paraphrase });
  }

  const metrics: Array<{ label: string; value: string | number }> = [
    { label: 'tipo', value: TIER_LABELS[spec.tier] || spec.tier },
    { label: 'estado', value: spec.status === 'armed' ? 'activo' : spec.status },
    { label: 'cooldown', value: fmtCooldown(spec.lifecycle.cooldown_seconds) },
  ];
  if (spec.schedule?.every_seconds) {
    metrics.push({ label: 'intervalo', value: `${spec.schedule.every_seconds}s` });
  }
  if (spec.dry_run?.total_fires != null) {
    metrics.push({ label: 'disparos dry-run', value: spec.dry_run.total_fires });
  }
  if (fires) metrics.push({ label: 'disparos registrados', value: fires.length });
  arts.push({ kind: 'metrics', title: 'Configuración', items: metrics });

  const eventChips = [
    ...spec.steps.flatMap(s => s.event_types),
    ...(spec.price_levels || []).map(formatPriceLevel),
  ];
  if (eventChips.length) {
    arts.push({ kind: 'chips', title: 'Condiciones', items: eventChips.slice(0, 12) });
  }
  const universeChips = formatUniverse(spec.universe);
  if (universeChips.length) {
    arts.push({ kind: 'chips', title: 'Universo', items: universeChips });
  }

  // Historial real de disparos / capturas
  if (fires && fires.length) {
    const isScheduled = spec.tier === 'scheduled';
    arts.push({
      kind: 'table',
      title: isScheduled ? 'Capturas recientes' : 'Historial de disparos',
      columns: ['symbol', 'evento', 'precio', 'cuándo'],
      rows: fires.slice(0, 200).map(f => [
        f.symbol,
        f.event_type || '—',
        f.price != null ? f.price : null,
        fmtWhen(f.fired_at),
      ]),
      total: fires.length,
    });
  }

  // Spec completa como código — la "fuente" del workflow
  arts.push({
    kind: 'code',
    title: 'Spec del workflow',
    language: 'json',
    content: JSON.stringify({
      id: spec.id,
      name: spec.name,
      tier: spec.tier,
      universe: spec.universe,
      steps: spec.steps,
      day_conditions: spec.day_conditions,
      price_levels: spec.price_levels || [],
      schedule: spec.schedule || null,
      lifecycle: spec.lifecycle,
      source_query: spec.source_query,
    }, null, 2),
  });

  return arts;
}

interface WorkflowInspectorProps {
  spec: AlertSpec | null;
  onClose: () => void;
}

export const WorkflowInspector = memo(function WorkflowInspector({
  spec, onClose,
}: WorkflowInspectorProps) {
  const { getToken } = useAuth();
  const [fires, setFires] = useState<AlertFire[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Refresca el historial cuando llegan disparos nuevos por el WS
  const liveFireCount = useAIAlertFiresStore(s => s.fires.length);

  useEffect(() => {
    if (!spec) return;
    let cancelled = false;
    listFires(getToken, spec.id, 200)
      .then(res => { if (!cancelled) setFires(res.fires); })
      .catch(() => { if (!cancelled) setFires([]); });
    return () => { cancelled = true; };
  }, [getToken, spec, liveFireCount]);

  const artifacts = useMemo(
    () => (spec ? buildArtifacts(spec, fires) : null),
    [spec, fires],
  );

  const run = useCallback(async (fn: () => Promise<unknown>, closeAfter = false) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      window.dispatchEvent(new CustomEvent('tradeul:ai-alerts-changed'));
      if (closeAfter) onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'La acción falló');
    } finally {
      setBusy(false);
    }
  }, [onClose]);

  const armed = spec?.status === 'armed';
  const actions = spec ? (
    <div className="flex items-center gap-1">
      <button
        onClick={() => void run(() => (armed ? pauseAlert(getToken, spec.id) : armAlert(getToken, spec.id)))}
        disabled={busy}
        className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold transition-colors disabled:opacity-40 ${
          armed
            ? 'bg-surface-inset text-muted-fg hover:text-foreground'
            : 'bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25'
        }`}
        title={armed ? 'Pausar workflow' : 'Activar workflow'}
      >
        {armed ? <Pause size={10} /> : <Play size={10} />}
        {armed ? 'Pausar' : 'Activar'}
      </button>
      <button
        onClick={() => void run(() => archiveAlert(getToken, spec.id), true)}
        disabled={busy}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-semibold text-muted-fg transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-40"
        title="Archivar workflow (deja de vigilar)"
      >
        <Archive size={10} />
      </button>
    </div>
  ) : null;

  return (
    <InspectorModal
      open={spec !== null}
      title={spec?.name || ''}
      subtitle={spec ? `${TIER_LABELS[spec.tier] || spec.tier} · ${armed ? 'activo' : spec.status}` : undefined}
      tag={spec?.id.slice(0, 8)}
      artifacts={artifacts}
      error={error}
      onClose={onClose}
      actions={actions}
      footerLeft="workflow inspector · datos en vivo"
    />
  );
});
