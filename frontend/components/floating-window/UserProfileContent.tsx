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
    <div className="h-full w-full overflow-auto bg-surface-hover">
      <UserProfile
        routing="hash"
        appearance={{
          elements: {
            // Root & Layout
            rootBox: 'w-full h-full',
            cardBox: 'w-full shadow-none border-0',
            card: 'w-full shadow-none border-0 bg-transparent',

            // Navigation
            navbar: 'bg-surface border-r border-border',
            navbarButton: 'text-foreground/80 hover:bg-surface-hover data-[active=true]:bg-blue-500/10 data-[active=true]:text-blue-600',
            navbarButtonIcon: 'text-muted-fg',

            // Page content
            pageScrollBox: 'p-6',
            page: 'gap-6',

            // Profile section
            profileSection: 'bg-surface rounded-xl border border-border p-6 shadow-sm',
            profileSectionTitle: 'text-foreground font-semibold text-base',
            profileSectionTitleText: 'text-foreground font-semibold',
            profileSectionContent: 'mt-4',
            profileSectionPrimaryButton: 'bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg px-4 py-2 transition-colors',

            // Form elements
            formFieldLabel: 'text-foreground font-medium text-sm',
            formFieldInput: 'border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            formButtonPrimary: 'bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors',
            formButtonReset: 'text-foreground/80 hover:text-foreground',

            // Avatars
            avatarBox: 'rounded-full border-2 border-border',
            avatarImage: 'rounded-full',

            // Headers
            headerTitle: 'text-foreground font-bold text-xl',
            headerSubtitle: 'text-foreground/80',

            // Badges
            badge: 'bg-surface-inset text-foreground text-xs font-medium px-2 py-1 rounded-full',
            badgePrimary: 'bg-blue-500/15 text-blue-700 dark:text-blue-400',

            // Buttons
            button: 'transition-colors',
            buttonPrimary: 'bg-blue-600 hover:bg-blue-700 text-white',
            buttonDanger: 'bg-red-600 hover:bg-red-700 text-white',

            // Accordion (Security section)
            accordionTriggerButton: 'hover:bg-surface-hover rounded-lg transition-colors',
            accordionContent: 'bg-surface-hover rounded-lg',

            // Tables (Sessions, etc)
            tableHead: 'bg-surface-hover text-foreground/80 text-xs uppercase font-semibold',

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

