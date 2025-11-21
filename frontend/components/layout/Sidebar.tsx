'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  ScanSearch,
  BarChart3,
  TrendingUp,
  Bell,
  Settings,
  Menu,
  X,
} from 'lucide-react';
import { useFloatingWindow } from '@/contexts/FloatingWindowContext';
import { useSidebar } from '@/contexts/SidebarContext';
import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';
import { Z_INDEX } from '@/lib/z-index';

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  comingSoon?: boolean;
}

const navItems: NavItem[] = [
  {
    name: 'Escáner',
    href: '/scanner',
    icon: ScanSearch,
  },
  {
    name: 'Dilution Tracker',
    href: '/dilution-tracker',
    icon: BarChart3,
  },
  {
    name: 'Analytics',
    href: '/analytics',
    icon: TrendingUp,
    comingSoon: true,
  },
  {
    name: 'Alertas',
    href: '/alerts',
    icon: Bell,
    comingSoon: true,
  },
  {
    name: 'Configuración',
    href: '/settings',
    icon: Settings,
    comingSoon: true,
  },
];

export function Sidebar() {
  const { collapsed } = useSidebar();
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  const toggleMobile = () => setMobileOpen(!mobileOpen);

  return (
    <>
      {/* Mobile Menu Button */}
      <button
        onClick={toggleMobile}
        className="lg:hidden fixed top-4 left-4 p-2 rounded-lg bg-white shadow-lg border border-slate-200 hover:bg-slate-50 transition-colors"
        style={{ zIndex: Z_INDEX.SIDEBAR_MOBILE_BUTTON }}
        aria-label="Toggle menu"
      >
        {mobileOpen ? (
          <X className="w-6 h-6 text-slate-700" />
        ) : (
          <Menu className="w-6 h-6 text-slate-700" />
        )}
      </button>

      {/* Mobile Overlay */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50"
          style={{ zIndex: Z_INDEX.SIDEBAR_MOBILE_OVERLAY }}
          onClick={toggleMobile}
        />
      )}

      {/* Sidebar - Ultra compacto (64px, solo iconos) */}
      <aside
        className={`
          fixed top-0 left-0 h-screen bg-white border-r border-slate-200
          transition-all duration-300 ease-in-out
          ${collapsed ? 'w-0' : 'w-16'}
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          lg:translate-x-0
          shadow-xl lg:shadow-sm
        `}
        style={{ zIndex: Z_INDEX.SIDEBAR }}
      >
        <div className="flex flex-col h-full">
          {/* Logo - Compacto */}
          <div className="flex items-center justify-center border-b border-slate-200 h-16">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-md">
              <span className="text-white font-bold text-xl">T</span>
            </div>
          </div>

          {/* Navigation - Solo iconos grandes */}
          <nav className="flex-1 overflow-y-auto py-4 px-2">
            <ul className="space-y-2">
              {navItems.map((item) => {
                const isActive = pathname === item.href || 
                  (item.href !== '/' && pathname.startsWith(item.href));
                const Icon = item.icon;

                return (
                  <li key={item.href}>
                    <Link
                      href={item.comingSoon ? '#' : item.href}
                      onClick={(e) => {
                        if (item.comingSoon) {
                          e.preventDefault();
                          return;
                        }
                        if (mobileOpen) toggleMobile();
                      }}
                      className={`
                        flex items-center justify-center p-3 rounded-lg
                        transition-all duration-200 group relative
                        ${isActive && !item.comingSoon
                          ? 'bg-blue-50 text-blue-600 shadow-sm'
                          : item.comingSoon
                          ? 'text-slate-300 cursor-not-allowed'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-blue-600'
                        }
                        ${!item.comingSoon && 'active:scale-95'}
                      `}
                    >
                      <Icon className={`w-6 h-6 shrink-0 ${isActive && !item.comingSoon ? 'stroke-[2.5]' : ''}`} />
                      
                      {/* Tooltip on hover */}
                      <div className="absolute left-full ml-2 px-3 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg
                                    opacity-0 invisible group-hover:opacity-100 group-hover:visible
                                    transition-all duration-200 whitespace-nowrap pointer-events-none shadow-xl z-50">
                        {item.name}
                        {item.comingSoon && <span className="text-slate-400 ml-2">(Pronto)</span>}
                        <div className="absolute left-0 top-1/2 -translate-x-1 -translate-y-1/2 w-2 h-2 bg-slate-900 rotate-45" />
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          {/* Footer - Compacto */}
          <div className="border-t border-slate-200 p-2">
            <div className="text-center">
              <div className="w-8 h-8 mx-auto rounded-full bg-slate-100 flex items-center justify-center text-slate-600 text-xs font-bold">
                U
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Spacer para layout */}
      <div className={`hidden lg:block transition-all duration-300 ${collapsed ? 'w-0' : 'w-16'}`} />
    </>
  );
}
