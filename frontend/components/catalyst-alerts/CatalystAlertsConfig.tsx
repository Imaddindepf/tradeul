/**
 * CatalystAlertsConfig
 * 
 * Panel de configuracion de alertas de catalyst.
 * Estilo compacto, sin colores, usa la fuente del usuario.
 */

'use client';

import { useTranslation } from 'react-i18next';
import { useCatalystAlertsStore } from '@/stores/useCatalystAlertsStore';

// Defaults para inputs (evita undefined -> controlled error)
const inputDefaults = {
  priceChange: { enabled: true, minPercent: 2 },
  velocity: { enabled: false, minPerMinute: 0.5 },
  rvol: { enabled: true, minValue: 2.0 },
  volumeSpike: { enabled: false, minRatio: 3 },
  alertTypes: { early: true, confirmed: true },
  filters: { onlyScanner: false, onlyWatchlist: false },
  notifications: { popup: true, sound: true, squawk: false },
  };

export function CatalystAlertsConfig() {
  const { t } = useTranslation();
  const enabled = useCatalystAlertsStore((state) => state.enabled);
  const rawCriteria = useCatalystAlertsStore((state) => state.criteria);
  const setEnabled = useCatalystAlertsStore((state) => state.setEnabled);
  const setCriteria = useCatalystAlertsStore((state) => state.setCriteria);
  
  // Merge con defaults para evitar undefined
  const criteria = {
    priceChange: { ...inputDefaults.priceChange, ...rawCriteria?.priceChange },
    velocity: { ...inputDefaults.velocity, ...rawCriteria?.velocity },
    rvol: { ...inputDefaults.rvol, ...rawCriteria?.rvol },
    volumeSpike: { ...inputDefaults.volumeSpike, ...rawCriteria?.volumeSpike },
    alertTypes: { ...inputDefaults.alertTypes, ...rawCriteria?.alertTypes },
    filters: { ...inputDefaults.filters, ...rawCriteria?.filters },
    notifications: { ...inputDefaults.notifications, ...rawCriteria?.notifications },
  };

  return (
    <div className="h-full overflow-auto bg-white p-3 text-sm">
      {/* Header con toggle */}
      <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-200">
        <span className="font-medium text-slate-800">
          {t('catalyst.title') || 'News Catalyst Alerts'}
        </span>
        <label className="flex items-center gap-2 cursor-pointer">
          <span className="text-xs text-slate-500">
            {enabled ? 'ON' : 'OFF'}
          </span>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="w-4 h-4 rounded border-slate-300"
          />
        </label>
      </div>

      <div className="space-y-3">
        {/* Alert Types */}
        <div className="border-b border-slate-100 pb-2">
          <div className="text-xs font-medium text-slate-500 mb-1">Alert Types</div>
          <div className="flex gap-4">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={criteria.alertTypes.early}
                onChange={(e) => setCriteria({
                  alertTypes: { ...criteria.alertTypes, early: e.target.checked }
                })}
                className="w-3.5 h-3.5 rounded border-slate-300"
              />
              <span className="text-slate-700">Early</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={criteria.alertTypes.confirmed}
                onChange={(e) => setCriteria({
                  alertTypes: { ...criteria.alertTypes, confirmed: e.target.checked }
                })}
                className="w-3.5 h-3.5 rounded border-slate-300"
              />
              <span className="text-slate-700">Confirmed</span>
            </label>
          </div>
        </div>

        {/* Criteria */}
        <div className="border-b border-slate-100 pb-2">
          <div className="text-xs font-medium text-slate-500 mb-1">Criteria (AND logic)</div>
          
          {/* Price Change */}
          <div className="flex items-center gap-2 py-1">
            <input
              type="checkbox"
              checked={criteria.priceChange.enabled}
              onChange={(e) => setCriteria({
                priceChange: { ...criteria.priceChange, enabled: e.target.checked }
              })}
              className="w-3.5 h-3.5 rounded border-slate-300"
            />
            <span className="text-slate-700 w-24">Price Change</span>
            <span className="text-slate-500">≥</span>
            <input
              type="number"
              value={criteria.priceChange.minPercent}
              onChange={(e) => setCriteria({
                priceChange: { ...criteria.priceChange, minPercent: parseFloat(e.target.value) || 0 }
              })}
              className="w-14 px-1.5 py-0.5 border border-slate-200 rounded text-right"
              min={0}
              step={0.5}
              disabled={!criteria.priceChange.enabled}
            />
            <span className="text-slate-500">%</span>
      </div>

          {/* RVOL */}
          <div className="flex items-center gap-2 py-1">
            <input
              type="checkbox"
              checked={criteria.rvol.enabled}
              onChange={(e) => setCriteria({
                rvol: { ...criteria.rvol, enabled: e.target.checked }
              })}
              className="w-3.5 h-3.5 rounded border-slate-300"
            />
            <span className="text-slate-700 w-24">RVOL</span>
            <span className="text-slate-500">≥</span>
            <input
              type="number"
              value={criteria.rvol.minValue}
              onChange={(e) => setCriteria({
                rvol: { ...criteria.rvol, minValue: parseFloat(e.target.value) || 0 }
              })}
              className="w-14 px-1.5 py-0.5 border border-slate-200 rounded text-right"
              min={0}
              step={0.5}
              disabled={!criteria.rvol.enabled}
            />
            <span className="text-slate-500">x</span>
          </div>

          {/* Velocity */}
          <div className="flex items-center gap-2 py-1">
            <input
              type="checkbox"
              checked={criteria.velocity.enabled}
              onChange={(e) => setCriteria({
                velocity: { ...criteria.velocity, enabled: e.target.checked }
              })}
              className="w-3.5 h-3.5 rounded border-slate-300"
            />
            <span className="text-slate-700 w-24">Velocity</span>
            <span className="text-slate-500">≥</span>
            <input
              type="number"
              value={criteria.velocity.minPerMinute}
              onChange={(e) => setCriteria({
                velocity: { ...criteria.velocity, minPerMinute: parseFloat(e.target.value) || 0 }
              })}
              className="w-14 px-1.5 py-0.5 border border-slate-200 rounded text-right"
              min={0}
              step={0.1}
              disabled={!criteria.velocity.enabled}
            />
            <span className="text-slate-500">%/min</span>
          </div>

          {/* Volume Spike */}
          <div className="flex items-center gap-2 py-1">
            <input
              type="checkbox"
              checked={criteria.volumeSpike.enabled}
              onChange={(e) => setCriteria({
                volumeSpike: { ...criteria.volumeSpike, enabled: e.target.checked }
              })}
              className="w-3.5 h-3.5 rounded border-slate-300"
            />
            <span className="text-slate-700 w-24">Vol Spike</span>
            <span className="text-slate-500">≥</span>
            <input
              type="number"
              value={criteria.volumeSpike.minRatio}
              onChange={(e) => setCriteria({
                volumeSpike: { ...criteria.volumeSpike, minRatio: parseFloat(e.target.value) || 0 }
              })}
              className="w-14 px-1.5 py-0.5 border border-slate-200 rounded text-right"
              min={0}
              step={0.5}
              disabled={!criteria.volumeSpike.enabled}
            />
            <span className="text-slate-500">x</span>
          </div>
      </div>

      {/* Filters */}
        <div className="border-b border-slate-100 pb-2">
          <div className="text-xs font-medium text-slate-500 mb-1">Filters</div>
          <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.filters.onlyScanner}
            onChange={(e) => setCriteria({
              filters: { ...criteria.filters, onlyScanner: e.target.checked }
            })}
              className="w-3.5 h-3.5 rounded border-slate-300"
          />
            <span className="text-slate-700">Only tickers in scanner</span>
        </label>
      </div>

      {/* Notifications */}
        <div>
          <div className="text-xs font-medium text-slate-500 mb-1">Notifications</div>
          <div className="flex gap-4">
            <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.notifications.popup}
            onChange={(e) => setCriteria({
              notifications: { ...criteria.notifications, popup: e.target.checked }
            })}
                className="w-3.5 h-3.5 rounded border-slate-300"
          />
              <span className="text-slate-700">Popup</span>
        </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.notifications.sound}
            onChange={(e) => setCriteria({
              notifications: { ...criteria.notifications, sound: e.target.checked }
            })}
                className="w-3.5 h-3.5 rounded border-slate-300"
          />
              <span className="text-slate-700">Sound</span>
        </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.notifications.squawk}
            onChange={(e) => setCriteria({
              notifications: { ...criteria.notifications, squawk: e.target.checked }
            })}
                className="w-3.5 h-3.5 rounded border-slate-300"
          />
              <span className="text-slate-700">Squawk</span>
        </label>
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="mt-3 pt-2 border-t border-slate-100">
        <p className="text-xs text-slate-400">
          When multiple criteria are enabled, ALL must be met (AND logic).
        </p>
      </div>
    </div>
  );
}
