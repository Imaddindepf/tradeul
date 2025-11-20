'use client';

import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';
import { Z_INDEX } from '@/lib/z-index';
import { useSidebar } from '@/contexts/SidebarContext';

interface NavbarProps {
  children?: ReactNode;
}

/**
 * Navbar Global Profesional
 * 
 * - Mismo nivel z-index que Sidebar (ambos son navegación global)
 * - Contenido dinámico según la página actual
 * - Se usa en el layout principal
 * - Se ajusta automáticamente cuando el sidebar colapsa
 */
export function Navbar({ children }: NavbarProps) {
  const pathname = usePathname();
  const { sidebarWidth } = useSidebar();

  // Determinar la página actual
  const currentPage = pathname?.split('/')[1] || '';

  return (
    <nav
      className="fixed top-0 right-0 h-16 bg-white border-b border-slate-200 shadow-sm transition-all duration-300"
      style={{ 
        left: `${sidebarWidth}px`, // Se ajusta dinámicamente cuando el sidebar colapsa
        zIndex: Z_INDEX.NAVBAR, // Mismo nivel que sidebar
      }}
    >
      <div className="h-full px-6">
        {/* Contenido dinámico inyectado por cada página */}
        {children}
      </div>
    </nav>
  );
}

/**
 * Variantes específicas de contenido del Navbar para cada página
 */

interface NavbarContentProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  statusBadge?: ReactNode;
}

export function NavbarContent({ title, subtitle, actions, statusBadge }: NavbarContentProps) {
  return (
    <div className="flex items-center justify-between h-full">
      {/* Left: Título y subtítulo */}
      <div className="flex flex-col justify-center">
        <h1 className="text-xl font-bold text-slate-900">{title}</h1>
        {subtitle && (
          <p className="text-sm text-slate-600 mt-0.5">{subtitle}</p>
        )}
      </div>

      {/* Right: Acciones y badges */}
      <div className="flex items-center gap-4">
        {statusBadge}
        {actions}
      </div>
    </div>
  );
}

