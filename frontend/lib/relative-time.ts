import i18n from '@/lib/i18n';

/**
 * Compact relative time for UI chips ("just now", "5m ago" / "hace 5m").
 * Uses the active i18n language so EN/ES stay consistent with Settings.
 */
export function formatTimeAgo(epochSeconds: number): string {
    const s = Math.max(0, Date.now() / 1000 - epochSeconds);
    if (s < 60) return i18n.t('common.justNow');
    if (s < 3600) return i18n.t('common.ago', { time: `${Math.floor(s / 60)}m` });
    if (s < 86400) return i18n.t('common.ago', { time: `${Math.floor(s / 3600)}h` });
    if (s < 172800) return i18n.t('common.yesterday');
    if (s < 604800) return i18n.t('common.ago', { time: `${Math.floor(s / 86400)}d` });
    const locale = (i18n.language || 'en').startsWith('es') ? 'es-ES' : 'en-US';
    return new Date(epochSeconds * 1000).toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}
