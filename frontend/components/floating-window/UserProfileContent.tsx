'use client';

import { useTranslation } from 'react-i18next';
import { UserProfile } from '@clerk/nextjs';
import { User } from 'lucide-react';

/**
 * Contenido de la ventana flotante de User Profile
 * Utiliza el componente UserProfile de Clerk con estilos personalizados
 */
export function UserProfileContent() {
  return (
    <div className="h-full w-full overflow-auto bg-slate-50">
      <UserProfile
        routing="hash"
        appearance={{
          elements: {
            // Root & Layout
            rootBox: 'w-full h-full',
            cardBox: 'w-full shadow-none border-0',
            card: 'w-full shadow-none border-0 bg-transparent',

            // Navigation
            navbar: 'bg-white border-r border-slate-200',
            navbarButton: 'text-slate-600 hover:bg-slate-100 data-[active=true]:bg-blue-50 data-[active=true]:text-blue-600',
            navbarButtonIcon: 'text-slate-500',

            // Page content
            pageScrollBox: 'p-6',
            page: 'gap-6',

            // Profile section
            profileSection: 'bg-white rounded-xl border border-slate-200 p-6 shadow-sm',
            profileSectionTitle: 'text-slate-800 font-semibold text-base',
            profileSectionTitleText: 'text-slate-800 font-semibold',
            profileSectionContent: 'mt-4',
            profileSectionPrimaryButton: 'bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg px-4 py-2 transition-colors',

            // Form elements
            formFieldLabel: 'text-slate-700 font-medium text-sm',
            formFieldInput: 'border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            formButtonPrimary: 'bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors',
            formButtonReset: 'text-slate-600 hover:text-slate-800',

            // Avatars
            avatarBox: 'rounded-full border-2 border-slate-200',
            avatarImage: 'rounded-full',

            // Headers
            headerTitle: 'text-slate-900 font-bold text-xl',
            headerSubtitle: 'text-slate-600',

            // Badges
            badge: 'bg-slate-100 text-slate-700 text-xs font-medium px-2 py-1 rounded-full',
            badgePrimary: 'bg-blue-100 text-blue-700',

            // Buttons
            button: 'transition-colors',
            buttonPrimary: 'bg-blue-600 hover:bg-blue-700 text-white',
            buttonDanger: 'bg-red-600 hover:bg-red-700 text-white',

            // Accordion (Security section)
            accordionTriggerButton: 'hover:bg-slate-50 rounded-lg transition-colors',
            accordionContent: 'bg-slate-50 rounded-lg',

            // Tables (Sessions, etc)
            tableHead: 'bg-slate-50 text-slate-600 text-xs uppercase font-semibold',

            // Footer
            footer: 'hidden', // Ocultar footer de Clerk
          },
          layout: {
            shimmer: true,
          },
        }}
      />
    </div>
  );
}

/**
 * Configuración por defecto para la ventana de UserProfile
 */
export const USER_PROFILE_WINDOW_CONFIG = {
  title: 'User Profile',
  width: 900,
  height: 650,
  minWidth: 700,
  minHeight: 500,
  maxWidth: 1200,
  maxHeight: 900,
};

