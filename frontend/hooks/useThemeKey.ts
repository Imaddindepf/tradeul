import { useState, useEffect } from 'react';

/**
 * Returns a key that changes whenever the theme (dark/light) toggles.
 * Use as a dependency in useMemo/useEffect to re-compute theme-dependent values.
 */
export function useThemeKey(): string {
    const [key, setKey] = useState(() =>
        typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
            ? 'dark'
            : 'light'
    );

    useEffect(() => {
        const observer = new MutationObserver(() => {
            const next = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
            setKey(prev => prev !== next ? next : prev);
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => observer.disconnect();
    }, []);

    return key;
}
