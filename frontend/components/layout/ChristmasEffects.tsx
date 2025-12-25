'use client';

import { useEffect, useState, useMemo } from 'react';

/**
 * ChristmasEffects - Diseño navideño premium animado
 * 
 * Features:
 * - Copos de nieve cayendo con física realista
 * - Partículas de luz brillante
 * - Gradientes sutiles
 * - Efectos de aurora festiva
 */

interface Snowflake {
  id: number;
  x: number;
  size: number;
  duration: number;
  delay: number;
  opacity: number;
  drift: number;
  type: 'snow' | 'sparkle';
}

interface ChristmasLight {
  id: number;
  color: string;
  delay: number;
  position: number;
}

export function ChristmasEffects() {
  const [mounted, setMounted] = useState(false);

  // Generar copos de nieve y partículas
  const snowflakes = useMemo<Snowflake[]>(() => {
    const items: Snowflake[] = [];

    // Copos de nieve (50 unidades)
    for (let i = 0; i < 50; i++) {
      items.push({
        id: i,
        x: Math.random() * 100,
        size: Math.random() * 4 + 2,
        duration: Math.random() * 10 + 8,
        delay: Math.random() * 10,
        opacity: Math.random() * 0.6 + 0.3,
        drift: (Math.random() - 0.5) * 100,
        type: 'snow',
      });
    }

    // Partículas brillantes (20 unidades)
    for (let i = 50; i < 70; i++) {
      items.push({
        id: i,
        x: Math.random() * 100,
        size: Math.random() * 3 + 1,
        duration: Math.random() * 6 + 4,
        delay: Math.random() * 8,
        opacity: Math.random() * 0.8 + 0.2,
        drift: (Math.random() - 0.5) * 50,
        type: 'sparkle',
      });
    }

    return items;
  }, []);

  // Luces navideñas para el borde superior
  const christmasLights = useMemo<ChristmasLight[]>(() => {
    const lights: ChristmasLight[] = [];
    const colors = [
      '#ffffff', // Blanco
      '#7dd3fc', // Azul cielo
      '#60a5fa', // Azul
      '#a5b4fc', // Índigo suave
      '#fde68a', // Dorado suave
    ];

    for (let i = 0; i < 40; i++) {
      lights.push({
        id: i,
        color: colors[i % colors.length],
        delay: i * 0.15,
        position: (i / 40) * 100,
      });
    }

    return lights;
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return (
    <>
      {/* Aurora boreal navideña - Fondo animado */}
      <div className="christmas-aurora" aria-hidden="true" />

      {/* Capa de nieve y partículas */}
      <div className="christmas-snow-container" aria-hidden="true">
        {snowflakes.map((flake) => (
          <div
            key={flake.id}
            className={flake.type === 'snow' ? 'christmas-snowflake' : 'christmas-sparkle'}
            style={{
              '--x': `${flake.x}%`,
              '--size': `${flake.size}px`,
              '--duration': `${flake.duration}s`,
              '--delay': `${flake.delay}s`,
              '--opacity': flake.opacity,
              '--drift': `${flake.drift}px`,
            } as React.CSSProperties}
          />
        ))}
      </div>

      {/* Luces navideñas en el borde superior */}
      <div className="christmas-lights-container" aria-hidden="true">
        {christmasLights.map((light) => (
          <div
            key={light.id}
            className="christmas-light-bulb"
            style={{
              '--light-color': light.color,
              '--light-delay': `${light.delay}s`,
              '--light-position': `${light.position}%`,
            } as React.CSSProperties}
          />
        ))}
        {/* Cable de las luces */}
        <svg className="christmas-lights-cable" viewBox="0 0 100 8" preserveAspectRatio="none">
          <path
            d="M0,4 Q2.5,1 5,4 T10,4 T15,4 T20,4 T25,4 T30,4 T35,4 T40,4 T45,4 T50,4 T55,4 T60,4 T65,4 T70,4 T75,4 T80,4 T85,4 T90,4 T95,4 T100,4"
            fill="none"
            stroke="rgba(255,255,255,0.22)"
            strokeWidth="0.5"
          />
        </svg>
      </div>

      {/* Esquinas decorativas con acebo */}
      <div className="christmas-corner christmas-corner-left" aria-hidden="true">
        <svg width="120" height="120" viewBox="0 0 120 120">
          {/* Hojas de acebo */}
          <path
            d="M30,90 Q15,75 30,60 Q45,45 30,30 Q15,45 0,30"
            fill="none"
            stroke="#2d5016"
            strokeWidth="3"
            className="christmas-holly-leaf"
          />
          <path
            d="M40,85 Q55,70 40,55 Q55,40 40,25"
            fill="none"
            stroke="#3d6b1f"
            strokeWidth="3"
            className="christmas-holly-leaf"
            style={{ animationDelay: '0.5s' }}
          />
          {/* Bayas rojas */}
          <circle cx="35" cy="65" r="5" fill="#c41e3a" className="christmas-berry" />
          <circle cx="25" cy="55" r="4" fill="#c41e3a" className="christmas-berry" style={{ animationDelay: '0.3s' }} />
          <circle cx="40" cy="50" r="4" fill="#c41e3a" className="christmas-berry" style={{ animationDelay: '0.6s' }} />
        </svg>
      </div>

      <div className="christmas-corner christmas-corner-right" aria-hidden="true">
        <svg width="120" height="120" viewBox="0 0 120 120">
          {/* Hojas de acebo (espejado) */}
          <path
            d="M90,90 Q105,75 90,60 Q75,45 90,30 Q105,45 120,30"
            fill="none"
            stroke="#2d5016"
            strokeWidth="3"
            className="christmas-holly-leaf"
          />
          <path
            d="M80,85 Q65,70 80,55 Q65,40 80,25"
            fill="none"
            stroke="#3d6b1f"
            strokeWidth="3"
            className="christmas-holly-leaf"
            style={{ animationDelay: '0.5s' }}
          />
          {/* Bayas rojas */}
          <circle cx="85" cy="65" r="5" fill="#c41e3a" className="christmas-berry" />
          <circle cx="95" cy="55" r="4" fill="#c41e3a" className="christmas-berry" style={{ animationDelay: '0.3s' }} />
          <circle cx="80" cy="50" r="4" fill="#c41e3a" className="christmas-berry" style={{ animationDelay: '0.6s' }} />
        </svg>
      </div>

      {/* Texto festivo sutil en la esquina */}
      <div className="christmas-greeting" aria-hidden="true">
        <span className="christmas-greeting-text">Happy Holidays</span>
      </div>
    </>
  );
}

