'use client';

import { useEffect } from 'react';
import { I18nextProvider } from 'react-i18next';
import i18n, { detectLanguage } from '@/lib/i18n';

interface I18nProviderProps {
  children: React.ReactNode;
}

/**
 * Provider de internacionalización.
 *
 * i18n arranca en 'en' (idéntico al HTML del SSR) para que la hidratación
 * coincida; el idioma guardado/detectado se aplica aquí, en un efecto
 * post-hidratación. Cambiarlo antes de hidratar reintroduce React #425/#422.
 */
export function I18nProvider({ children }: I18nProviderProps) {
  useEffect(() => {
    const lang = detectLanguage();
    if (lang !== getBaseLanguage()) {
      void i18n.changeLanguage(lang);
    }
  }, []);

  return (
    <I18nextProvider i18n={i18n}>
      {children}
    </I18nextProvider>
  );
}

function getBaseLanguage(): string {
  return i18n.language?.split('-')[0] || 'en';
}
