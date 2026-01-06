/**
 * IndicatorPanel - Panel de indicador sincronizado con el chart principal
 * 
 * Estilo TradingView: panel separado debajo del chart principal
 * Sincronizado con el timeScale del chart principal
 * 
 * INDICADORES SOPORTADOS:
 * - RSI (con líneas de sobrecompra/sobreventa)
 * - MACD (línea + histograma)
 * - Stochastic (K y D)
 * - ADX (ADX + +DI + -DI)
 * - ATR
 * - BB Width
 * - TTM Squeeze
 * - OBV
 */

'use client';

import { useEffect, useRef, memo, useCallback } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  ColorType,
  LineStyle,
  CrosshairMode,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';
import { X } from 'lucide-react';
import type { 
  IndicatorDataPoint, 
  MACDData, 
  StochData, 
  ADXData,
  SqueezeData,
} from '@/hooks/useIndicatorWorker';
import { PANEL_INDICATORS } from '@/hooks/useIndicatorWorker';

// ============================================================================
// Types
// ============================================================================

interface IndicatorPanelProps {
  type: string;
  data: any;
  mainChart: IChartApi | null;
  height?: number;
  onClose: () => void;
}

// ============================================================================
// Colors
// ============================================================================

const COLORS = {
  background: '#ffffff',
  gridColor: '#f1f5f9',
  borderColor: '#e2e8f0',
  textColor: '#64748b',
  
  // RSI
  rsi: '#8b5cf6',
  
  // MACD
  macdLine: '#3b82f6',
  macdSignal: '#f97316',
  macdHistogramUp: 'rgba(16, 185, 129, 0.6)',
  macdHistogramDown: 'rgba(239, 68, 68, 0.6)',
  
  // Stochastic
  stochK: '#3b82f6',
  stochD: '#f97316',
  
  // ADX
  adxLine: '#8b5cf6',
  pdiLine: '#10b981',
  mdiLine: '#ef4444',
  
  // ATR
  atr: '#6366f1',
  
  // BB Width
  bbWidth: '#14b8a6',
  
  // Squeeze
  squeezeOn: '#ef4444',
  squeezeOff: '#10b981',
  
  // OBV
  obv: '#3b82f6',
};

// ============================================================================
// Component
// ============================================================================

function IndicatorPanelComponent({
  type,
  data,
  mainChart,
  height = 100,
  onClose,
}: IndicatorPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Map<string, ISeriesApi<any>>>(new Map());
  
  const config = PANEL_INDICATORS[type];

  // ============================================================================
  // Crear chart del panel
  // ============================================================================
  
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: COLORS.background },
        textColor: COLORS.textColor,
        fontFamily: "'Inter', sans-serif",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: COLORS.gridColor, style: LineStyle.Solid },
        horzLines: { color: COLORS.gridColor, style: LineStyle.Solid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { visible: true, labelVisible: false, color: 'rgba(100, 116, 139, 0.5)', width: 1 },
        horzLine: { visible: true, labelVisible: true, color: 'rgba(100, 116, 139, 0.5)', width: 1 },
      },
      rightPriceScale: {
        borderColor: COLORS.borderColor,
        scaleMargins: { top: 0.1, bottom: 0.1 },
        autoScale: true,
      },
      timeScale: {
        borderColor: COLORS.borderColor,
        visible: false, // Ocultar eje X (lo muestra el chart principal)
        rightOffset: 5,
      },
      handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: false },
      handleScroll: { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false },
    });

    chartRef.current = chart;

    // Crear series según el tipo de indicador
    createSeries(chart, type);
    
    // Añadir líneas de referencia si existen
    if (config?.lines) {
      const mainSeries = seriesRefs.current.get('main') || seriesRefs.current.values().next().value;
      if (mainSeries) {
        for (const line of config.lines) {
          mainSeries.createPriceLine({
            price: line.value,
            color: line.color,
            lineWidth: 1,
            lineStyle: line.style === 'dashed' ? LineStyle.Dashed : LineStyle.Solid,
            axisLabelVisible: false,
          });
        }
      }
    }

    // Resize observer - usa height - 18 para el espacio real del chart
    const chartHeight = height - 18;
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) {
          chart.applyOptions({ width, height: chartHeight });
        }
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRefs.current.clear();
    };
  }, [type, height, config]);

  // ============================================================================
  // Crear series según tipo de indicador
  // ============================================================================
  
  const createSeries = useCallback((chart: IChartApi, indicatorType: string) => {
    seriesRefs.current.clear();
    
    switch (indicatorType) {
      case 'rsi':
        const rsiSeries = chart.addLineSeries({
          color: COLORS.rsi,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesRefs.current.set('main', rsiSeries);
        break;
        
      case 'macd':
        const histogramSeries = chart.addHistogramSeries({
          priceLineVisible: false,
          lastValueVisible: false,
          priceScaleId: 'macd',
        });
        const macdLineSeries = chart.addLineSeries({
          color: COLORS.macdLine,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
          priceScaleId: 'macd',
        });
        const signalSeries = chart.addLineSeries({
          color: COLORS.macdSignal,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          priceScaleId: 'macd',
        });
        seriesRefs.current.set('histogram', histogramSeries);
        seriesRefs.current.set('macd', macdLineSeries);
        seriesRefs.current.set('signal', signalSeries);
        break;
        
      case 'stoch':
        const kSeries = chart.addLineSeries({
          color: COLORS.stochK,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        const dSeries = chart.addLineSeries({
          color: COLORS.stochD,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        seriesRefs.current.set('k', kSeries);
        seriesRefs.current.set('d', dSeries);
        seriesRefs.current.set('main', kSeries);
        break;
        
      case 'adx':
        const adxSeries = chart.addLineSeries({
          color: COLORS.adxLine,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        const pdiSeries = chart.addLineSeries({
          color: COLORS.pdiLine,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        const mdiSeries = chart.addLineSeries({
          color: COLORS.mdiLine,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        seriesRefs.current.set('adx', adxSeries);
        seriesRefs.current.set('pdi', pdiSeries);
        seriesRefs.current.set('mdi', mdiSeries);
        seriesRefs.current.set('main', adxSeries);
        break;
        
      case 'atr':
        const atrSeries = chart.addLineSeries({
          color: COLORS.atr,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesRefs.current.set('main', atrSeries);
        break;
        
      case 'bbWidth':
        const bbWidthSeries = chart.addLineSeries({
          color: COLORS.bbWidth,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesRefs.current.set('main', bbWidthSeries);
        break;
        
      case 'squeeze':
        const squeezeSeries = chart.addHistogramSeries({
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesRefs.current.set('main', squeezeSeries);
        break;
        
      case 'obv':
        const obvSeries = chart.addLineSeries({
          color: COLORS.obv,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesRefs.current.set('main', obvSeries);
        break;
        
      case 'rvol':
        const rvolSeries = chart.addHistogramSeries({
          priceLineVisible: false,
          lastValueVisible: true,
          priceFormat: {
            type: 'price',
            precision: 2,
            minMove: 0.01,
          },
        });
        seriesRefs.current.set('main', rvolSeries);
        break;
    }
  }, []);

  // ============================================================================
  // Actualizar datos
  // ============================================================================
  
  useEffect(() => {
    if (!chartRef.current || !data) return;

    switch (type) {
      case 'rsi':
      case 'atr':
      case 'bbWidth':
      case 'obv':
        const mainSeries = seriesRefs.current.get('main');
        if (mainSeries && Array.isArray(data)) {
          mainSeries.setData(data.map((d: IndicatorDataPoint) => ({
            time: d.time as UTCTimestamp,
            value: d.value,
          })));
        }
        break;
        
      case 'macd':
        const macdData = data as MACDData;
        if (macdData) {
          const histSeries = seriesRefs.current.get('histogram');
          const macdLineSeries = seriesRefs.current.get('macd');
          const sigSeries = seriesRefs.current.get('signal');
          
          if (histSeries && macdData.histogram) {
            histSeries.setData(macdData.histogram.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
              color: d.color || (d.value >= 0 ? COLORS.macdHistogramUp : COLORS.macdHistogramDown),
            })));
          }
          if (macdLineSeries && macdData.macd) {
            macdLineSeries.setData(macdData.macd.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
          if (sigSeries && macdData.signal) {
            sigSeries.setData(macdData.signal.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
        }
        break;
        
      case 'stoch':
        const stochData = data as StochData;
        if (stochData) {
          const kSeries = seriesRefs.current.get('k');
          const dSeries = seriesRefs.current.get('d');
          
          if (kSeries && stochData.k) {
            kSeries.setData(stochData.k.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
          if (dSeries && stochData.d) {
            dSeries.setData(stochData.d.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
        }
        break;
        
      case 'adx':
        const adxData = data as ADXData;
        if (adxData) {
          const adxSeries = seriesRefs.current.get('adx');
          const pdiSeries = seriesRefs.current.get('pdi');
          const mdiSeries = seriesRefs.current.get('mdi');
          
          if (adxSeries && adxData.adx) {
            adxSeries.setData(adxData.adx.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
          if (pdiSeries && adxData.pdi) {
            pdiSeries.setData(adxData.pdi.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
          if (mdiSeries && adxData.mdi) {
            mdiSeries.setData(adxData.mdi.map(d => ({
              time: d.time as UTCTimestamp,
              value: d.value,
            })));
          }
        }
        break;
        
      case 'squeeze':
        const squeezeSeries = seriesRefs.current.get('main');
        if (squeezeSeries && Array.isArray(data)) {
          squeezeSeries.setData(data.map((d: SqueezeData) => ({
            time: d.time as UTCTimestamp,
            value: d.value,
            color: d.color || (d.squeezeOn ? COLORS.squeezeOn : COLORS.squeezeOff),
          })));
        }
        break;
        
      case 'rvol':
        const rvolSeries = seriesRefs.current.get('main');
        if (rvolSeries && Array.isArray(data)) {
          rvolSeries.setData(data.map((d: IndicatorDataPoint) => ({
            time: d.time as UTCTimestamp,
            value: d.value,
            color: d.color,
          })));
        }
        break;
    }
  }, [data, type]);

  // ============================================================================
  // Sincronizar timeScale con el chart principal
  // ============================================================================
  
  useEffect(() => {
    if (!mainChart || !chartRef.current) return;

    const mainTimeScale = mainChart.timeScale();
    const panelTimeScale = chartRef.current.timeScale();

    // Sincronizar cuando cambia el visible range del chart principal
    const handleVisibleRangeChange = () => {
      try {
        const range = mainTimeScale.getVisibleLogicalRange();
        if (range && range.from !== null && range.to !== null) {
          panelTimeScale.setVisibleLogicalRange(range);
        }
      } catch (e) {
        // Ignorar errores de sincronización cuando el chart no está listo
      }
    };

    // Sincronizar también el visible time range (para alineación exacta)
    const handleVisibleTimeRangeChange = () => {
      try {
        const timeRange = mainTimeScale.getVisibleRange();
        if (timeRange && timeRange.from && timeRange.to) {
          panelTimeScale.setVisibleRange(timeRange);
        }
      } catch (e) {
        // Ignorar errores de sincronización cuando el chart no está listo
      }
    };

    mainTimeScale.subscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
    mainTimeScale.subscribeVisibleTimeRangeChange(handleVisibleTimeRangeChange);
    
    // Sincronización inicial con un pequeño delay para asegurar que los datos estén cargados
    const syncTimeout = setTimeout(() => {
      handleVisibleRangeChange();
      handleVisibleTimeRangeChange();
    }, 50);

    return () => {
      clearTimeout(syncTimeout);
      mainTimeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleRangeChange);
      mainTimeScale.unsubscribeVisibleTimeRangeChange(handleVisibleTimeRangeChange);
    };
  }, [mainChart, data]); // Re-sincronizar cuando cambian los datos

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <div 
      className="relative border-t border-slate-200 bg-white flex-shrink-0"
      style={{ height: `${height}px` }}
    >
      {/* Header del panel - altura fija 18px */}
      <div className="h-[18px] flex items-center justify-between px-2 bg-slate-50/95 border-b border-slate-100">
        <span className="text-[9px] font-medium text-slate-500">
          {config?.label || type.toUpperCase()}
        </span>
        <button
          onClick={onClose}
          className="p-0.5 text-slate-400 hover:text-slate-600 hover:bg-slate-200 rounded transition-colors"
          title="Close panel"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
      
      {/* Chart container - altura = total - header */}
      <div 
        ref={containerRef} 
        className="w-full"
        style={{ height: `${height - 18}px` }}
      />
    </div>
  );
}

export const IndicatorPanel = memo(IndicatorPanelComponent);
export default IndicatorPanel;

