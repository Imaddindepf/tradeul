/**
 * Theme Provider
 * 
 * Aplica las preferencias de usuario (colores, fuentes) como CSS variables
 * Se actualiza automáticamente cuando cambian las preferencias
 */

'use client';

import { useEffect } from 'react';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

interface ThemeProviderProps {
  children: React.ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);

  // Aplicar CSS variables cuando cambian las preferencias
  useEffect(() => {
    const root = document.documentElement;
    
    // Colores
    root.style.setProperty('--color-tick-up', colors.tickUp);
    root.style.setProperty('--color-tick-down', colors.tickDown);
    root.style.setProperty('--color-background', colors.background);
    root.style.setProperty('--color-primary', colors.primary);
    
    // Fuente mono
    const fontMap = {
      'oxygen-mono': 'var(--font-oxygen-mono)',
      'ibm-plex-mono': 'var(--font-ibm-plex-mono)',
      'jetbrains-mono': 'var(--font-jetbrains-mono)',
      'fira-code': 'var(--font-fira-code)',
    };
    root.style.setProperty('--font-mono-selected', fontMap[theme.font] || fontMap['jetbrains-mono']);
    
    // Aplicar color de fondo al body
    document.body.style.backgroundColor = colors.background;
    
  }, [colors, theme]);

  return <>{children}</>;
}

export default ThemeProvider;

