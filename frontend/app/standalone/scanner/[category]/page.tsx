'use client';

import { use } from 'react';
import CategoryTableV2 from '@/components/scanner/CategoryTableV2';

interface StandaloneTablePageProps {
  params: Promise<{
    category: string;
  }>;
}

const CATEGORY_NAMES: Record<string, string> = {
  'gappers_up': 'Gap Up',
  'gappers_down': 'Gap Down',
  'momentum_up': 'Momentum Alcista',
  'momentum_down': 'Momentum Bajista',
  'winners': 'Mayores Ganadores',
  'losers': 'Mayores Perdedores',
  'new_highs': 'Nuevos Máximos',
  'new_lows': 'Nuevos Mínimos',
  'anomalies': 'Anomalías',
  'high_volume': 'Alto Volumen',
  'reversals': 'Reversals',
};

/**
 * Página standalone para tabla del scanner
 * Se abre en nueva ventana del navegador sin navbar ni sidebar
 */
export default function StandaloneTablePage({ params }: StandaloneTablePageProps) {
  const { category } = use(params);
  const categoryName = CATEGORY_NAMES[category] || category;

  return (
    <div className="h-screen w-screen overflow-hidden">
      <CategoryTableV2 
        title={categoryName}
        listName={category}
      />
    </div>
  );
}

