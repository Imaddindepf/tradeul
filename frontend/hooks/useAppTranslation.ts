
import { useTranslation } from 'react-i18next';

/**
 * Hook personalizado para traducciones de la app
 * Wrapper sobre useTranslation con helpers útiles
 */
export function useAppTranslation() {
    const { t, i18n } = useTranslation();

    return {
        t,
        i18n,
        lang: i18n.language,
        isSpanish: i18n.language === 'es',
        isEnglish: i18n.language === 'en',
    };
}

// Re-export para conveniencia
export { useTranslation } from 'react-i18next';

