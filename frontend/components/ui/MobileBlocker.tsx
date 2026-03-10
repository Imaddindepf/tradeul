'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Monitor, ArrowRight } from 'lucide-react';

/**
 * Detecta si es un dispositivo móvil REAL (no ventana pequeña en desktop)
 * Usa User-Agent + touch detection
 */
function isMobileDevice(): boolean {
    if (typeof window === 'undefined') return false;

    const userAgent = navigator.userAgent.toLowerCase();

    // Detectar móviles y tablets por User-Agent
    const mobileKeywords = [
        'android',
        'webos',
        'iphone',
        'ipad',
        'ipod',
        'blackberry',
        'windows phone',
        'opera mini',
        'iemobile',
        'mobile',
    ];

    const isMobileUA = mobileKeywords.some(keyword => userAgent.includes(keyword));

    // Detectar por capacidades táctiles + pantalla pequeña (tablets grandes OK)
    const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    const isSmallScreen = window.screen.width < 1024; // screen.width es físico, no ventana

    // Es móvil si: User-Agent dice móvil O (tiene touch Y pantalla física pequeña)
    return isMobileUA || (hasTouch && isSmallScreen);
}

export function MobileBlocker({ children }: { children: React.ReactNode }) {
    const { t } = useTranslation();
    const [isMobile, setIsMobile] = useState(false);
    const [isChecking, setIsChecking] = useState(true);
    const [dismissed, setDismissed] = useState(false);

    useEffect(() => {
        // Solo detectar una vez al montar (no en resize)
        setIsMobile(isMobileDevice());
        setIsChecking(false);
    }, []);

    if (isChecking) {
        return (
            <div className="min-h-screen bg-surface-hover flex items-center justify-center">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center animate-pulse">
                    <span className="text-white font-bold text-xl">T</span>
                </div>
            </div>
        );
    }

    if (!isMobile || dismissed) {
        return <>{children}</>;
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-surface-hover to-surface flex flex-col">
            {/* Header con logo */}
            <div className="flex items-center gap-3 p-6 border-b border-border-subtle">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
                    <span className="text-white font-bold text-xl">T</span>
                </div>
                <span className="text-lg font-semibold text-foreground">Tradeul</span>
            </div>

            {/* Content */}
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                {/* Icon ilustrativo */}
                <div className="relative mb-8">
                    <div className="w-24 h-16 rounded-xl bg-surface border-2 border-border shadow-xl flex items-center justify-center">
                        <Monitor className="w-10 h-10 text-blue-500" />
                    </div>
                    <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center">
                        <span className="text-white text-xs font-bold">!</span>
                    </div>
                    <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-8 h-1 rounded-full bg-muted" />
                </div>

                {/* Message */}
                <div className="max-w-xs space-y-4">
                    <h1 className="text-2xl font-bold text-foreground">
                        {t('mobile.designedForDesktop')}
                    </h1>

                    <p className="text-muted-fg leading-relaxed">
                        {t('mobile.professionalPlatform')}
                    </p>

                    {/* Visual hint */}
                    <div className="flex items-center justify-center gap-2 py-4">
                        <div className="w-8 h-6 rounded border-2 border-border bg-surface-inset" />
                        <ArrowRight className="w-4 h-4 text-muted-fg" />
                        <div className="w-16 h-10 rounded border-2 border-primary bg-primary/10 flex items-center justify-center">
                            <div className="w-2 h-2 rounded-full bg-blue-500" />
                        </div>
                    </div>

                    <p className="text-sm text-muted-fg">
                        {t('mobile.openFromComputer')}
                    </p>
                </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-border-subtle">
                <button
                    onClick={() => setDismissed(true)}
                    className="w-full py-3 px-4 rounded-xl border border-border text-sm font-medium text-foreground/80 hover:bg-surface-hover hover:border-border transition-all active:scale-[0.98]"
                >
                    {t('mobile.continueAnyway')}
                </button>
            </div>
        </div>
    );
}
