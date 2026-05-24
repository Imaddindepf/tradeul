/**
 * Date formatting utilities for Tradeul
 * 
 * All times are displayed in the user's preferred timezone.
 * Default: Eastern Time (ET) - the standard for US markets.
 * 
 * JavaScript Intl handles DST automatically - no external API needed!
 */

import { useUserPreferencesStore, TimezoneOption } from '@/stores/useUserPreferencesStore';

// Timezone labels for display
export const TIMEZONE_LABELS: Record<TimezoneOption, { label: string; abbrev: string; region: string }> = {
    'America/New_York': { label: 'Eastern Time', abbrev: 'ET', region: '🇺🇸 New York' },
    'America/Chicago': { label: 'Central Time', abbrev: 'CT', region: '🇺🇸 Chicago' },
    'America/Denver': { label: 'Mountain Time', abbrev: 'MT', region: '🇺🇸 Denver' },
    'America/Los_Angeles': { label: 'Pacific Time', abbrev: 'PT', region: '🇺🇸 Los Angeles' },
    'Europe/London': { label: 'British Time', abbrev: 'GMT/BST', region: '🇬🇧 London' },
    'Europe/Madrid': { label: 'Spain Time', abbrev: 'CET/CEST', region: '🇪🇸 Madrid' },
    'Europe/Paris': { label: 'France Time', abbrev: 'CET/CEST', region: '🇫🇷 Paris' },
    'Europe/Berlin': { label: 'Germany Time', abbrev: 'CET/CEST', region: '🇩🇪 Berlin' },
    'Asia/Tokyo': { label: 'Japan Time', abbrev: 'JST', region: '🇯🇵 Tokyo' },
    'Asia/Hong_Kong': { label: 'Hong Kong Time', abbrev: 'HKT', region: '🇭🇰 Hong Kong' },
    'Asia/Singapore': { label: 'Singapore Time', abbrev: 'SGT', region: '🇸🇬 Singapore' },
    'UTC': { label: 'Coordinated Universal Time', abbrev: 'UTC', region: '🌍 UTC' },
};

/**
 * Get the user's preferred timezone from the store
 * Falls back to ET if not set
 */
export function getUserTimezone(): TimezoneOption {
    return useUserPreferencesStore.getState().theme.timezone || 'America/New_York';
}

/**
 * Get the abbreviation for a timezone (e.g., "ET", "CET")
 */
export function getTimezoneAbbrev(tz?: TimezoneOption): string {
    const timezone = tz || getUserTimezone();
    return TIMEZONE_LABELS[timezone]?.abbrev || timezone;
}

/**
 * Format a date/time string to the user's preferred timezone
 * @param isoString - ISO 8601 date string (e.g., "2025-12-30T07:32:06Z")
 * @param tz - Optional override timezone (uses user preference if not provided)
 * @returns Object with formatted date and time
 */
export function formatToUserTimezone(isoString: string, tz?: TimezoneOption): { date: string; time: string; full: string } {
    try {
        const timezone = tz || getUserTimezone();
        const d = new Date(isoString);

        if (isNaN(d.getTime())) {
            return { date: '—', time: '—', full: '—' };
        }

        const date = d.toLocaleDateString('en-US', {
            timeZone: timezone,
            month: '2-digit',
            day: '2-digit',
            year: '2-digit'
        });

        const time = d.toLocaleTimeString('en-US', {
            timeZone: timezone,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });

        const abbrev = getTimezoneAbbrev(timezone);
        const full = `${date} ${time} ${abbrev}`;

        return { date, time, full };
    } catch {
        return { date: '—', time: '—', full: '—' };
    }
}

/**
 * Format time only in user's timezone (for compact displays)
 */
export function formatTimeUserTz(isoString: string, tz?: TimezoneOption): string {
    try {
        const timezone = tz || getUserTimezone();
        const d = new Date(isoString);

        if (isNaN(d.getTime())) return '—';

        return d.toLocaleTimeString('en-US', {
            timeZone: timezone,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    } catch {
        return '—';
    }
}

/**
 * Format time with seconds in user's timezone
 */
export function formatTimeWithSecondsUserTz(isoString: string, tz?: TimezoneOption): string {
    try {
        const timezone = tz || getUserTimezone();
        const d = new Date(isoString);

        if (isNaN(d.getTime())) return '—';

        return d.toLocaleTimeString('en-US', {
            timeZone: timezone,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch {
        return '—';
    }
}

/**
 * Format date only in user's timezone (for tables, lists)
 */
export function formatDateUserTz(isoString: string, tz?: TimezoneOption): string {
    try {
        const timezone = tz || getUserTimezone();
        const d = new Date(isoString);

        if (isNaN(d.getTime())) return '—';

        return d.toLocaleDateString('en-US', {
            timeZone: timezone,
            month: '2-digit',
            day: '2-digit',
            year: '2-digit'
        });
    } catch {
        return '—';
    }
}

/**
 * Format date in short format (Dec 30)
 */
export function formatDateShortUserTz(isoString: string, tz?: TimezoneOption): string {
    try {
        const timezone = tz || getUserTimezone();
        const d = new Date(isoString);

        if (isNaN(d.getTime())) return '—';

        return d.toLocaleDateString('en-US', {
            timeZone: timezone,
            month: 'short',
            day: 'numeric'
        });
    } catch {
        return '—';
    }
}

/**
 * Format a Date object to user's timezone time string
 */
export function formatDateObjectToUserTz(date: Date, tz?: TimezoneOption): string {
    try {
        const timezone = tz || getUserTimezone();
        return date.toLocaleTimeString('en-US', {
            timeZone: timezone,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    } catch {
        return '—';
    }
}

/**
 * Get current time in user's timezone
 */
export function getCurrentTimeUserTz(tz?: TimezoneOption): string {
    const timezone = tz || getUserTimezone();
    return new Date().toLocaleTimeString('en-US', {
        timeZone: timezone,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

/**
 * Format Unix timestamp (milliseconds) to user's timezone
 */
export function formatTimestampToUserTz(timestamp: number, tz?: TimezoneOption): { date: string; time: string } {
    try {
        const timezone = tz || getUserTimezone();
        const d = new Date(timestamp);

        return {
            date: d.toLocaleDateString('en-US', {
                timeZone: timezone,
                month: '2-digit',
                day: '2-digit'
            }),
            time: d.toLocaleTimeString('en-US', {
                timeZone: timezone,
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            })
        };
    } catch {
        return { date: '—', time: '—' };
    }
}

/**
 * Create a time formatter function for lightweight-charts
 * This returns a function that can be used in chart options
 */
export function createChartTimeFormatter(tz?: TimezoneOption): (time: number) => string {
    const timezone = tz || getUserTimezone();
    return (time: number) => {
        const date = new Date(time * 1000);
        return date.toLocaleTimeString('en-US', {
            timeZone: timezone,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });
    };
}

/**
 * Create a localization time formatter for lightweight-charts tooltips
 */
export function createChartLocalizationFormatter(tz?: TimezoneOption): (time: number) => string {
    const timezone = tz || getUserTimezone();
    const abbrev = getTimezoneAbbrev(timezone);
    return (time: number) => {
        const date = new Date(time * 1000);
        return date.toLocaleString('en-US', {
            timeZone: timezone,
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }) + ` ${abbrev}`;
    };
}

// ============================================================================
// LEGACY FUNCTIONS (for backwards compatibility)
// These use the user's timezone automatically
// ============================================================================

/** @deprecated Use formatToUserTimezone instead */
export const formatToET = formatToUserTimezone;
/** @deprecated Use formatTimeUserTz instead */
export const formatTimeET = formatTimeUserTz;
/** @deprecated Use formatDateUserTz instead */
export const formatDateET = formatDateUserTz;
