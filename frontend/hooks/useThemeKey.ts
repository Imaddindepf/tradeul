import { useState, useEffect } from 'react';

/**
 * Returns a key that changes whenever the theme (dark/light) toggles.
 * Use as a dependency in useMemo/useEffect to re-compute theme-dependent values.
 *
 * Empieza SIEMPRE en 'light' (igual que el SSR) y lee la clase real en un
 * efecto: leer document en el useState inicial renderiza distinto en servidor
 * y cliente → error de hidratación React #425 con tema dark guardado.
 */
export function useThemeKey(): string {
    const [key, setKey] = useState('light');

    useEffect(() => {
        const read = () =>
            document.documentElement.classList.contains('dark') ? 'dark' : 'light';
        setKey(read());
        const observer = new MutationObserver(() => {
            setKey(prev => {
                const next = read();
                return prev !== next ? next : prev;
            });
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => observer.disconnect();
    }, []);

    return key;
}
