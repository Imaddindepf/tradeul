'use client';

import { useEffect, useRef, useState } from 'react';
import { ThemeProvider as NextThemesProvider, useTheme as useNextTheme } from 'next-themes';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';

interface ThemeProviderProps {
  children: React.ReactNode;
}

type ColorScheme = 'light' | 'dark' | 'system';

const VALID_SCHEMES: ColorScheme[] = ['light', 'dark', 'system'];

function ThemeSync() {
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);
  const { theme: activeTheme, setTheme, resolvedTheme } = useNextTheme();
  const [hydrated, setHydrated] = useState(false);
  const lastStoreSchemeRef = useRef<string | null>(null);

  useEffect(() => {
    useUserPreferencesStore.persist.rehydrate();
    setHydrated(true);
  }, []);

  // Dos direcciones, sin ping-pong:
  // - Cambia el store (click del usuario / backend) → imponer a next-themes.
  // - Cambia next-themes con el store quieto (evento storage de otra pestaña)
  //   → adoptarlo en el store, que además lo sincroniza al backend.
  // Adoptar no llama a setTheme e imponer no toca el store: no hay bucle
  // posible entre pestañas, ambas convergen al último cambio real.
  useEffect(() => {
    if (!hydrated) return;
    const want = theme.colorScheme;
    if (lastStoreSchemeRef.current !== want) {
      lastStoreSchemeRef.current = want;
      if (activeTheme !== want) setTheme(want);
      return;
    }
    if (activeTheme && activeTheme !== want && VALID_SCHEMES.includes(activeTheme as ColorScheme)) {
      lastStoreSchemeRef.current = activeTheme;
      useUserPreferencesStore.getState().setColorScheme(activeTheme as ColorScheme);
    }
  }, [hydrated, activeTheme, theme.colorScheme, setTheme]);

  useEffect(() => {
    if (!hydrated || !resolvedTheme) return;

    const root = document.documentElement;
    root.style.setProperty('--color-tick-up', colors.tickUp);
    root.style.setProperty('--color-tick-down', colors.tickDown);
    root.style.setProperty('--color-primary', colors.primary);

    // El background del dashboard (Settings → Data colors) es independiente
    // del tema claro/oscuro. La única excepción es el blanco default en dark:
    // ahí no es una elección del usuario, es el DEFAULT_COLORS heredado de
    // light, y un inline blanco pisaría body{background:var(--color-bg)}.
    const bg = (colors.background || '').toLowerCase();
    const bgIsDefaultWhite = bg === '#ffffff' || bg === '#fff' || bg === 'white';
    if (resolvedTheme === 'dark' && bgIsDefaultWhite) {
      root.style.removeProperty('--color-background');
      root.style.background = '';
      document.body.style.backgroundColor = '';
    } else if (bg) {
      root.style.setProperty('--color-background', colors.background);
      root.style.background = colors.background;
      document.body.style.backgroundColor = colors.background;
    }

    const fontMap: Record<string, string> = {
      'oxygen-mono': 'var(--font-oxygen-mono)',
      'ibm-plex-mono': 'var(--font-ibm-plex-mono)',
      'jetbrains-mono': 'var(--font-jetbrains-mono)',
      'fira-code': 'var(--font-fira-code)',
    };
    root.style.setProperty('--font-mono-selected', fontMap[theme.font] || fontMap['jetbrains-mono']);
  }, [hydrated, colors, theme, resolvedTheme]);

  return null;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      <ThemeSync />
      {children}
    </NextThemesProvider>
  );
}

export default ThemeProvider;
