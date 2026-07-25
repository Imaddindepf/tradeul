'use client';

/**
 * FuturesMonitorContent — ventana del comando FUT
 *
 * Monitor de los 40 futuros continuos (front-month) agrupados por complejo:
 * índices US, tipos, energía, metales, agro, softs y dólar. Datos en vivo del
 * pipeline propio (fmp_indices → snapshot → gateway /realtime/class/future).
 */

import React from 'react';
import { AssetMonitorTable, MonitorGroup } from '@/components/markets/AssetMonitorTable';

const GROUPS: MonitorGroup[] = [
  { title: 'Equity Index', symbols: ['ESUSD', 'NQUSD', 'YMUSD', 'RTYUSD'] },
  { title: 'Rates', symbols: ['ZQUSD', 'ZTUSD', 'ZFUSD', 'ZNUSD', 'ZBUSD'] },
  { title: 'Energy', symbols: ['CLUSD', 'BZUSD', 'NGUSD', 'HOUSD', 'RBUSD'] },
  { title: 'Metals', symbols: ['GCUSD', 'SIUSD', 'HGUSD', 'PLUSD', 'PAUSD', 'ALIUSD', 'MGCUSD', 'SILUSD'] },
  { title: 'Agriculture', symbols: ['ZCUSX', 'ZSUSX', 'ZLUSX', 'ZMUSD', 'ZOUSX', 'ZRUSD', 'KEUSX', 'LEUSX', 'HEUSX', 'GFUSX', 'DCUSD', 'LBUSD'] },
  { title: 'Softs', symbols: ['SBUSX', 'CTUSX', 'KCUSX', 'CCUSD', 'OJUSX'] },
  { title: 'Currency', symbols: ['DXUSD'] },
];

const LABELS: Record<string, string> = {
  ESUSD: 'S&P 500 E-mini',
  NQUSD: 'Nasdaq 100 E-mini',
  YMUSD: 'Dow Mini',
  RTYUSD: 'Russell 2000 Micro',
  ZQUSD: 'Fed Funds 30D',
  ZTUSD: '2Y T-Note',
  ZFUSD: '5Y T-Note',
  ZNUSD: '10Y T-Note',
  ZBUSD: '30Y T-Bond',
  CLUSD: 'WTI Crude',
  BZUSD: 'Brent Crude',
  NGUSD: 'Natural Gas',
  HOUSD: 'Heating Oil',
  RBUSD: 'RBOB Gasoline',
  GCUSD: 'Gold',
  SIUSD: 'Silver',
  HGUSD: 'Copper',
  PLUSD: 'Platinum',
  PAUSD: 'Palladium',
  ALIUSD: 'Aluminum',
  MGCUSD: 'Micro Gold',
  SILUSD: 'Micro Silver',
  ZCUSX: 'Corn',
  ZSUSX: 'Soybeans',
  ZLUSX: 'Soybean Oil',
  ZMUSD: 'Soybean Meal',
  ZOUSX: 'Oats',
  ZRUSD: 'Rough Rice',
  KEUSX: 'Wheat',
  LEUSX: 'Live Cattle',
  HEUSX: 'Lean Hogs',
  GFUSX: 'Feeder Cattle',
  DCUSD: 'Class III Milk',
  LBUSD: 'Lumber',
  SBUSX: 'Sugar',
  CTUSX: 'Cotton',
  KCUSX: 'Coffee',
  CCUSD: 'Cocoa',
  OJUSX: 'Orange Juice',
  DXUSD: 'Dollar Index',
};

export function FuturesMonitorContent() {
  return <AssetMonitorTable assetClass="future" groups={GROUPS} labels={LABELS} />;
}
