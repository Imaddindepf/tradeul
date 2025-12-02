'use client';

import { useTranslation } from 'react-i18next';
import CategoryTableV2 from '@/components/scanner/CategoryTableV2';

interface StandaloneTablePageProps {
  params: {
    category: string;
  };
}

/**
 * Página standalone para tabla del scanner
 * Se abre en nueva ventana del navegador sin navbar ni sidebar
 */
export default function StandaloneTablePage({ params }: StandaloneTablePageProps) {
  const { t } = useTranslation();
  const { category } = params;

  // Obtener nombre de categoría desde traducciones
  const categoryNameMap: Record<string, string> = {
    'gappers_up': t('scanner.gapUp'),
    'gappers_down': t('scanner.gapDown'),
    'momentum_up': t('scanner.momentumUp'),
    'momentum_down': t('scanner.momentumDown'),
    'winners': t('scanner.topGainers'),
    'losers': t('scanner.topLosers'),
    'new_highs': t('scanner.newHighs'),
    'new_lows': t('scanner.newLows'),
    'anomalies': t('scanner.anomalies'),
    'high_volume': t('scanner.highVolume'),
    'reversals': t('scanner.reversals'),
  };

  const categoryName = categoryNameMap[category] || category;

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-white">
      <div className="flex-1 min-h-0">
        <CategoryTableV2
          title={categoryName}
          listName={category}
        />
      </div>
    </div>
  );
}

