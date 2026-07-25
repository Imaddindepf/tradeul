'use client';

/**
 * ForexMonitorContent — ventana del comando FX
 *
 * Monitor del set curado de forex spot (majors, crosses, EM y metales spot).
 * Datos en vivo del pipeline propio (fmp_forex → snapshot → gateway
 * /realtime/class/forex).
 */

import React from 'react';
import { AssetMonitorTable, MonitorGroup } from '@/components/markets/AssetMonitorTable';

const GROUPS: MonitorGroup[] = [
  { title: 'Majors', symbols: ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD'] },
  { title: 'EUR Crosses', symbols: ['EURGBP', 'EURJPY', 'EURCHF', 'EURAUD', 'EURCAD'] },
  { title: 'GBP / JPY Crosses', symbols: ['GBPJPY', 'GBPCHF', 'GBPAUD', 'GBPCAD', 'AUDJPY', 'CADJPY', 'CHFJPY', 'NZDJPY'] },
  { title: 'Minor Crosses', symbols: ['AUDCAD', 'AUDCHF', 'AUDNZD', 'NZDCAD', 'CADCHF'] },
  { title: 'EM & Others', symbols: ['USDMXN', 'USDBRL', 'USDZAR', 'USDTRY', 'USDSEK', 'USDNOK', 'USDPLN', 'USDSGD', 'USDHKD', 'USDCNH', 'USDINR'] },
  { title: 'Metals Spot', symbols: ['XAUUSD', 'XAGUSD'] },
];

export function ForexMonitorContent() {
  return <AssetMonitorTable assetClass="forex" groups={GROUPS} />;
}
