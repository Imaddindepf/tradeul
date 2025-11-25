/**
 * Client Theme Provider Wrapper
 * 
 * Necesario porque layout.tsx es un Server Component por defecto
 */

'use client';

import { ThemeProvider } from './ThemeProvider';

export function ClientThemeProvider({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}

export default ClientThemeProvider;

