'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  ScanSearch,
  TrendingUp,
  Bell,
  Settings,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
} from 'lucide-react';

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
  comingSoon?: boolean;
}

const navItems: NavItem[] = [
  {
    name: 'Dashboard',
    href: '/',
    icon: LayoutDashboard,
    comingSoon: true,
  },
  {
    name: 'Escáner',
    href: '/scanner',
    icon: ScanSearch,
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
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  const toggleCollapse = () => setCollapsed(!collapsed);
  const toggleMobile = () => setMobileOpen(!mobileOpen);

  return (
    <>
      {/* Mobile Menu Button */}
      <button
        onClick={toggleMobile}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 rounded-lg bg-white shadow-lg border border-slate-200 hover:bg-slate-50 transition-colors"
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
          className="lg:hidden fixed inset-0 bg-black/50 z-30"
          onClick={toggleMobile}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed top-0 left-0 h-screen bg-white border-r border-slate-200 z-40
          transition-all duration-300 ease-in-out
          ${collapsed ? 'w-20' : 'w-64'}
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
          lg:translate-x-0
          shadow-xl lg:shadow-sm
        `}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-5 border-b border-slate-200">
            <div className={`flex items-center gap-3 ${collapsed ? 'lg:justify-center lg:w-full' : ''}`}>
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-md">
                <span className="text-white font-bold text-xl">T</span>
              </div>
              {!collapsed && (
                <div className="overflow-hidden">
                  <h1 className="text-xl font-bold text-slate-900 whitespace-nowrap">Tradeul</h1>
                  <p className="text-xs text-slate-500 whitespace-nowrap">Scanner Pro</p>
                </div>
              )}
            </div>

            {/* Desktop Collapse Button */}
            <button
              onClick={toggleCollapse}
              className="hidden lg:flex p-1.5 rounded-md hover:bg-slate-100 transition-colors"
              aria-label="Toggle sidebar"
            >
              {collapsed ? (
                <ChevronRight className="w-4 h-4 text-slate-600" />
              ) : (
                <ChevronLeft className="w-4 h-4 text-slate-600" />
              )}
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-4 px-3">
            <ul className="space-y-1">
              {navItems.map((item) => {
                const isActive = pathname === item.href || 
                  (item.href !== '/' && pathname.startsWith(item.href));
                const Icon = item.icon;

                return (
                  <li key={item.href}>
                    <Link
                      href={item.comingSoon ? '#' : item.href}
                      onClick={(e) => {
                        if (item.comingSoon) e.preventDefault();
                        if (!item.comingSoon && mobileOpen) toggleMobile();
                      }}
                      className={`
                        flex items-center gap-3 px-3 py-2.5 rounded-lg
                        transition-all duration-200
                        ${collapsed ? 'lg:justify-center' : ''}
                        ${
                          isActive && !item.comingSoon
                            ? 'bg-blue-50 text-blue-600 shadow-sm'
                            : item.comingSoon
                            ? 'text-slate-400 cursor-not-allowed'
                            : 'text-slate-700 hover:bg-slate-50 hover:text-blue-600'
                        }
                        ${!item.comingSoon && 'active:scale-95'}
                        group relative
                      `}
                    >
                      <Icon className={`w-5 h-5 shrink-0 ${isActive && !item.comingSoon ? 'stroke-2' : ''}`} />
                      
                      {!collapsed && (
                        <>
                          <span className="font-medium text-sm whitespace-nowrap overflow-hidden">
                            {item.name}
                          </span>
                          {item.comingSoon && (
                            <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-medium">
                              Pronto
                            </span>
                          )}
                          {item.badge && !item.comingSoon && (
                            <span className="ml-auto min-w-[20px] h-5 px-1.5 rounded-full bg-blue-500 text-white text-xs font-medium flex items-center justify-center">
                              {item.badge}
                            </span>
                          )}
                        </>
                      )}

                      {/* Tooltip for collapsed state */}
                      {collapsed && (
                        <div className="absolute left-full ml-2 px-3 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all whitespace-nowrap z-50 shadow-xl">
                          {item.name}
                          {item.comingSoon && (
                            <span className="ml-2 text-xs text-slate-400">(Próximamente)</span>
                          )}
                          <div className="absolute left-0 top-1/2 -translate-x-1 -translate-y-1/2 w-2 h-2 bg-slate-900 rotate-45" />
                        </div>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-slate-200">
            <div className={`flex items-center gap-3 ${collapsed ? 'lg:justify-center' : ''}`}>
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white font-semibold text-sm shrink-0">
                IA
              </div>
              {!collapsed && (
                <div className="overflow-hidden">
                  <p className="text-sm font-medium text-slate-900 whitespace-nowrap">Imad Amsif</p>
                  <p className="text-xs text-slate-500 whitespace-nowrap">Trader Pro</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* Spacer for content */}
      <div className={`hidden lg:block transition-all duration-300 ${collapsed ? 'w-20' : 'w-64'}`} />
    </>
  );
}

