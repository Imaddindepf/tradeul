'use client';

import { usePathname } from 'next/navigation';
import { ReactNode, useState, useRef, useEffect } from 'react';
import { useClerk, useUser } from '@clerk/nextjs';
import { User, Settings, LogOut } from 'lucide-react';
import { Z_INDEX } from '@/lib/z-index';
import { useCommandExecutor } from '@/hooks/useCommandExecutor';

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

  return (
    <nav
      className="fixed top-0 left-0 right-0 h-16 bg-white border-b border-slate-200 shadow-sm"
      style={{
        zIndex: Z_INDEX.NAVBAR,
      }}
    >
      <div className="h-full w-full px-6">
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

/**
 * Custom User Menu - Dropdown con Profile, Settings, Logout
 * Exportado para uso en cualquier navbar personalizado
 */
export function UserMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { signOut } = useClerk();
  const { user } = useUser();
  const { executeCommand } = useCommandExecutor();

  // Cerrar al hacer click fuera
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    signOut({ redirectUrl: '/' });
  };

  // Obtener iniciales del usuario
  const initials = user?.firstName && user?.lastName
    ? `${user.firstName[0]}${user.lastName[0]}`
    : user?.emailAddresses?.[0]?.emailAddress?.[0]?.toUpperCase() || 'U';

  return (
    <div className="relative" ref={menuRef}>
      {/* Avatar Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white font-semibold text-sm hover:from-blue-600 hover:to-blue-700 transition-all shadow-md hover:shadow-lg"
      >
        {user?.imageUrl ? (
          <img
            src={user.imageUrl}
            alt="Avatar"
            className="w-9 h-9 rounded-full object-cover"
          />
        ) : (
          initials
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-xl border border-slate-200 py-1 overflow-hidden"
          style={{ zIndex: Z_INDEX.MODAL }}
        >
          {/* User Info Header */}
          <div className="px-4 py-3 border-b border-slate-100">
            <p className="text-sm font-medium text-slate-900 truncate">
              {user?.fullName || 'Usuario'}
            </p>
            <p className="text-xs text-slate-500 truncate">
              {user?.emailAddresses?.[0]?.emailAddress}
            </p>
          </div>

          {/* Menu Items */}
          <div className="py-1">
            <button
              onClick={() => {
                setIsOpen(false);
                // TODO: Implementar Profile
              }}
              className="w-full px-4 py-2 text-left text-sm text-slate-600 hover:bg-slate-50 flex items-center gap-3 opacity-50 cursor-not-allowed"
              disabled
            >
              <User className="w-4 h-4" />
              <span>Profile</span>
              <span className="ml-auto text-xs text-slate-400">Próximamente</span>
            </button>

            <button
              onClick={() => {
                setIsOpen(false);
                executeCommand('settings');
              }}
              className="w-full px-4 py-2 text-left text-sm text-slate-600 hover:bg-slate-50 flex items-center gap-3 transition-colors"
            >
              <Settings className="w-4 h-4" />
              <span>Settings</span>
            </button>
          </div>

          {/* Logout */}
          <div className="border-t border-slate-100 py-1">
            <button
              onClick={handleLogout}
              className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-3 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span>Cerrar Sesión</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
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
        {/* Custom User Menu */}
        <UserMenu />
      </div>
    </div>
  );
}

