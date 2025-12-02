'use client';

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

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

// Inicializar i18next
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    defaultNS: 'translation',
    
    // Detectar idioma del navegador, pero priorizar localStorage
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: LANGUAGE_KEY,
      caches: ['localStorage'],
    },

    interpolation: {
      escapeValue: false, // React ya escapa por defecto
    },

    react: {
      useSuspense: false, // Evitar suspense en cliente
    },
  });

/**
 * Cambiar idioma y persistir en localStorage
 */
export function changeLanguage(lang: LanguageCode): Promise<void> {
  localStorage.setItem(LANGUAGE_KEY, lang);
  return i18n.changeLanguage(lang);
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

