'use client';

import { useEffect, useState } from 'react';
import { ThemeProvider as NextThemesProvider, useTheme as useNextTheme } from 'next-themes';
import { useUserPreferencesStore } from '@/stores/useUserPreferencesStore';
import { useClerkSync } from '@/hooks/useClerkSync';

interface ThemeProviderProps {
  children: React.ReactNode;
}

function ThemeSync() {
  const colors = useUserPreferencesStore((state) => state.colors);
  const theme = useUserPreferencesStore((state) => state.theme);
  const { setTheme } = useNextTheme();
  const [hydrated, setHydrated] = useState(false);

  useClerkSync();

  useEffect(() => {
    useUserPreferencesStore.persist.rehydrate();
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    setTheme(theme.colorScheme);
  }, [hydrated, theme.colorScheme, setTheme]);

  useEffect(() => {
    if (!hydrated) return;

    const root = document.documentElement;
    root.style.setProperty('--color-tick-up', colors.tickUp);
    root.style.setProperty('--color-tick-down', colors.tickDown);
    root.style.setProperty('--color-background', colors.background);
    root.style.setProperty('--color-primary', colors.primary);

    const fontMap: Record<string, string> = {
      'oxygen-mono': 'var(--font-oxygen-mono)',
      'ibm-plex-mono': 'var(--font-ibm-plex-mono)',
      'jetbrains-mono': 'var(--font-jetbrains-mono)',
      'fira-code': 'var(--font-fira-code)',
    };
    root.style.setProperty('--font-mono-selected', fontMap[theme.font] || fontMap['jetbrains-mono']);

    document.body.style.backgroundColor = colors.background;
  }, [hydrated, colors, theme]);

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
