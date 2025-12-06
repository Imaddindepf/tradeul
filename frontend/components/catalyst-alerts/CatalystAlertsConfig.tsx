/**
 * CatalystAlertsConfig
 * 
 * Panel de configuración de criterios de alerta
 */

'use client';

import { useTranslation } from 'react-i18next';
import { useCatalystAlertsStore } from '@/stores/useCatalystAlertsStore';

// Función para crear una alerta de prueba
function createTestAlert() {
  const testTickers = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'MSFT'];
  const ticker = testTickers[Math.floor(Math.random() * testTickers.length)];
  const change = (Math.random() * 8 + 2).toFixed(1);

  return {
    id: `test-${Date.now()}`,
    ticker,
    title: `${ticker} surges on major news catalyst - Breaking development`,
    url: '#',
    published: new Date().toISOString(),
    metrics: {
      // Nuevos campos del sistema simplificado
      price: 150 + Math.random() * 50,
      change_recent_pct: parseFloat(change),
      change_day_pct: parseFloat(change) * 1.2,
      volume: Math.floor(Math.random() * 5000000),
      rvol: 2 + Math.random() * 3,
      ticker,
      lookback_minutes: 3,
      source: 'test',
      // Campos legacy (compatibilidad)
      price_at_news: 150 + Math.random() * 50,
      change_1m_pct: parseFloat(change),
      change_5m_pct: parseFloat(change) * 1.5,
      snapshot_time: Date.now(),
    },
    triggeredAt: Date.now(),
    dismissed: false,
    reason: `+${change}% in 3min`,
  };
}

export function CatalystAlertsConfig() {
  const { t } = useTranslation();
  const enabled = useCatalystAlertsStore((state) => state.enabled);
  const criteria = useCatalystAlertsStore((state) => state.criteria);
  const setEnabled = useCatalystAlertsStore((state) => state.setEnabled);
  const setCriteria = useCatalystAlertsStore((state) => state.setCriteria);
  const addAlert = useCatalystAlertsStore((state) => state.addAlert);

  const handleTestAlert = () => {
    const testAlert = createTestAlert();
    addAlert(testAlert);
  };

  return (
    <div className="p-4 space-y-4 bg-white h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <h2 className="text-lg font-semibold text-slate-800">
          {t('catalyst.title') || 'News Catalyst Alerts'}
        </h2>
        <button
          onClick={() => setEnabled(!enabled)}
          className={`
            px-3 py-1.5 rounded-full text-sm font-medium transition-colors
            ${enabled
              ? 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }
          `}
        >
          {enabled ? t('common.enabled') || 'Enabled' : t('common.disabled') || 'Disabled'}
        </button>
      </div>

      {/* Description */}
      <p className="text-sm text-slate-500">
        {t('catalyst.description') || 'Get alerts when news triggers explosive price movements based on your criteria.'}
      </p>

      {/* Price Change Criteria */}
      <div className="space-y-3 p-3 bg-slate-50 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm text-slate-700">
            {t('catalyst.priceChange') || 'Price Change'}
          </span>
          <label className="ml-auto flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={criteria.priceChange.enabled}
              onChange={(e) => setCriteria({
                priceChange: { ...criteria.priceChange, enabled: e.target.checked }
              })}
              className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
          </label>
        </div>

        {criteria.priceChange.enabled && (
          <div className="flex items-center gap-2 pl-4">
            <span className="text-sm text-slate-600">{t('catalyst.alertWhen') || 'Alert when'} ≥</span>
            <input
              type="number"
              value={criteria.priceChange.minPercent}
              onChange={(e) => setCriteria({
                priceChange: { ...criteria.priceChange, minPercent: parseFloat(e.target.value) || 0 }
              })}
              className="w-16 px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
              min={0}
              step={0.5}
            />
            <span className="text-sm text-slate-600">% {t('catalyst.in') || 'in'}</span>
            <select
              value={criteria.priceChange.timeWindow}
              onChange={(e) => setCriteria({
                priceChange: { ...criteria.priceChange, timeWindow: parseInt(e.target.value) as 1 | 5 }
              })}
              className="px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
            >
              <option value={1}>1 min</option>
              <option value={5}>5 min</option>
            </select>
          </div>
        )}
      </div>

      {/* RVOL Criteria */}
      <div className="space-y-3 p-3 bg-slate-50 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm text-slate-700">
            {t('catalyst.rvol') || 'Relative Volume (RVOL)'}
          </span>
          <label className="ml-auto flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={criteria.rvol.enabled}
              onChange={(e) => setCriteria({
                rvol: { ...criteria.rvol, enabled: e.target.checked }
              })}
              className="w-4 h-4 rounded border-slate-300 text-purple-600 focus:ring-purple-500"
            />
          </label>
        </div>

        {criteria.rvol.enabled && (
          <div className="flex items-center gap-2 pl-4">
            <span className="text-sm text-slate-600">{t('catalyst.alertWhen') || 'Alert when'} ≥</span>
            <input
              type="number"
              value={criteria.rvol.minValue}
              onChange={(e) => setCriteria({
                rvol: { ...criteria.rvol, minValue: parseFloat(e.target.value) || 0 }
              })}
              className="w-16 px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-purple-500"
              min={0}
              step={0.5}
            />
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="space-y-3 p-3 bg-slate-50 rounded-lg">
        <span className="font-medium text-sm text-slate-700">
          {t('catalyst.filters') || 'Filters'}
        </span>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.filters.onlyScanner}
            onChange={(e) => setCriteria({
              filters: { ...criteria.filters, onlyScanner: e.target.checked }
            })}
            className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-slate-600">
            {t('catalyst.onlyScanner') || 'Only tickers in scanner tables'}
          </span>
        </label>
      </div>

      {/* Notifications */}
      <div className="space-y-3 p-3 bg-slate-50 rounded-lg">
        <span className="font-medium text-sm text-slate-700">
          {t('catalyst.notifications') || 'Notifications'}
        </span>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.notifications.popup}
            onChange={(e) => setCriteria({
              notifications: { ...criteria.notifications, popup: e.target.checked }
            })}
            className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-slate-600">
            {t('catalyst.popupNotification') || 'Popup notifications'}
          </span>
        </label>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.notifications.sound}
            onChange={(e) => setCriteria({
              notifications: { ...criteria.notifications, sound: e.target.checked }
            })}
            className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-slate-600">
            {t('catalyst.soundNotification') || 'Sound alerts'}
          </span>
        </label>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={criteria.notifications.squawk}
            onChange={(e) => setCriteria({
              notifications: { ...criteria.notifications, squawk: e.target.checked }
            })}
            className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-slate-600">
            {t('catalyst.squawkNotification') || 'Squawk (read aloud)'}
          </span>
        </label>
      </div>
    </div>
  );
}
