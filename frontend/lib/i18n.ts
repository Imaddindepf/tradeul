'use client';

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from '@/locales/en.json';
import es from '@/locales/es.json';

// Clave para localStorage
const LANGUAGE_KEY = 'tradeul-language';

// Recursos de traducción
const resources = {
  en: { translation: en },
  es: { translation: es },
};

// Idiomas disponibles
export const AVAILABLE_LANGUAGES = [
  { code: 'en', name: 'English', flag: '🇺🇸' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
] as const;

export type LanguageCode = typeof AVAILABLE_LANGUAGES[number]['code'];

// Inicializar i18next SIEMPRE en 'en', idéntico al HTML del SSR.
// Detectar aquí el idioma (localStorage/navigator) hacía que el primer render
// del cliente difiriera del servidor → React #425/#422 en cada carga.
// El idioma real se aplica post-hidratación en I18nProvider (detectLanguage).
i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: 'en',
    fallbackLng: 'en',
    defaultNS: 'translation',

    interpolation: {
      escapeValue: false, // React ya escapa por defecto
    },

    react: {
      useSuspense: false, // Evitar suspense en cliente
    },
  });

/**
 * Idioma preferido del usuario: localStorage y, si no hay nada guardado,
 * el idioma del navegador (cacheado en localStorage, como hacía el detector).
 * Solo llamar en cliente tras la hidratación.
 */
export function detectLanguage(): LanguageCode {
  if (typeof window === 'undefined') return 'en';
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    if (saved === 'en' || saved === 'es') return saved;
    const nav = (navigator.language || 'en').toLowerCase();
    const detected: LanguageCode = nav.startsWith('es') ? 'es' : 'en';
    localStorage.setItem(LANGUAGE_KEY, detected);
    return detected;
  } catch {
    return 'en';
  }
}

/**
 * Cambiar idioma y persistir en localStorage
 */
export async function changeLanguage(lang: LanguageCode): Promise<void> {
  localStorage.setItem(LANGUAGE_KEY, lang);
  await i18n.changeLanguage(lang);
}

/**
 * Obtener idioma actual
 */
export function getCurrentLanguage(): LanguageCode {
  return (i18n.language?.split('-')[0] as LanguageCode) || 'en';
}

/**
 * Obtener idioma guardado en localStorage
 */
export function getSavedLanguage(): LanguageCode | null {
  if (typeof window === 'undefined') return null;
  const saved = localStorage.getItem(LANGUAGE_KEY);
  return saved as LanguageCode | null;
}

export default i18n;
