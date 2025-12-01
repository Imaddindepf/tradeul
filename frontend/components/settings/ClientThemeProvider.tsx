/**
 * Client Theme Provider Wrapper
 * 
 * Necesario porque layout.tsx es un Server Component por defecto
 * Incluye MobileBlocker para bloquear acceso desde dispositivos móviles
 */

'use client';

import { ThemeProvider } from './ThemeProvider';
import { MobileBlocker } from '@/components/ui/MobileBlocker';

export function ClientThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <MobileBlocker>
        {children}
      </MobileBlocker>
    </ThemeProvider>
  );
}

export default ClientThemeProvider;

