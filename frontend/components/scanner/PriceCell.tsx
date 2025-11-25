/**
 * PriceCell - Professional Price Display with Tick Indicator
 * 
 * Estilo Bloomberg/Reuters/TradingView:
 * - Solo cambia el COLOR del texto (verde/rojo)
 * - Sin fondos, sin transformaciones, sin animaciones pesadas
 * - Ultra-eficiente: cada celda maneja su propio estado
 * - Aislado: cambios NO causan re-render de toda la tabla
 */

'use client';

import { memo, useRef, useEffect, useState } from 'react';
import { formatPrice } from '@/lib/formatters';

interface PriceCellProps {
  price: number | undefined;
  symbol: string;
}

type TickDirection = 'up' | 'down' | 'neutral';

/**
 * Componente memoizado para mostrar precio con tick indicator
 * Cada celda maneja su propio estado de tick de forma independiente
 */
function PriceCellComponent({ price, symbol }: PriceCellProps) {
  const prevPriceRef = useRef<number | undefined>(undefined);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [tick, setTick] = useState<TickDirection>('neutral');

  useEffect(() => {
    // Limpiar timeout anterior si existe
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    const prevPrice = prevPriceRef.current;
    
    // Solo mostrar tick si hay cambio de precio real
    if (prevPrice !== undefined && price !== undefined && price !== prevPrice) {
      // Threshold mínimo para evitar ruido (0.001%)
      const threshold = prevPrice * 0.00001;
      const diff = Math.abs(price - prevPrice);
      
      if (diff > threshold) {
        // Determinar dirección
        const direction: TickDirection = price > prevPrice ? 'up' : 'down';
        setTick(direction);
        
        // Volver a neutral después de 300ms (como los profesionales)
        timeoutRef.current = setTimeout(() => {
          setTick('neutral');
        }, 300);
      }
    }

    // Actualizar referencia
    prevPriceRef.current = price;

    // Cleanup
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [price]);

  return (
    <span 
      className="price-cell font-mono font-semibold"
      data-tick={tick}
    >
      {formatPrice(price)}
    </span>
  );
}

// Memoizar para evitar re-renders innecesarios
// Solo re-renderiza si price o symbol cambian
export const PriceCell = memo(PriceCellComponent, (prev, next) => {
  return prev.price === next.price && prev.symbol === next.symbol;
});

PriceCell.displayName = 'PriceCell';

