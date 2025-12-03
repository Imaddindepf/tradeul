'use client';

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Sparkles, Newspaper, Globe, Zap } from 'lucide-react';

const ANNOUNCEMENT_KEY = 'announcement_catalyst_alerts_v1';

export function AnnouncementBanner() {
    const { t } = useTranslation();
    const [isVisible, setIsVisible] = useState(false);

    // Verificar si ya fue cerrado (solo en cliente)
    useEffect(() => {
        const dismissed = localStorage.getItem(ANNOUNCEMENT_KEY);
        if (!dismissed) {
            // Mostrar después de un pequeño delay para no interrumpir la carga inicial
            const timer = setTimeout(() => setIsVisible(true), 1500);
            return () => clearTimeout(timer);
        }
    }, []);

    const handleDismiss = () => {
        localStorage.setItem(ANNOUNCEMENT_KEY, 'true');
        setIsVisible(false);
    };

    if (!isVisible) return null;

    return (
        <div
            className="fixed bottom-6 right-6 max-w-sm bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden animate-in slide-in-from-bottom-5 fade-in duration-300"
            style={{ zIndex: 9999 }}
        >
            {/* Header con gradiente */}
            <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 px-4 py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-2 text-white">
                    <div className="flex items-center gap-1.5 bg-white/20 px-2 py-0.5 rounded-full">
                        <Sparkles className="w-3.5 h-3.5" />
                        <span className="text-xs font-semibold uppercase tracking-wide">
                            {t('announcement.newFeature')}
                        </span>
                    </div>
                </div>
                <button
                    onClick={handleDismiss}
                    className="text-white/80 hover:text-white transition-colors p-1 hover:bg-white/20 rounded"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>

            {/* Content */}
            <div className="p-4 space-y-3">
                {/* Feature 1: Scanner + News */}
                <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-blue-50 rounded-lg flex-shrink-0">
                        <Newspaper className="w-4 h-4 text-blue-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-slate-900 text-sm">
                            {t('announcement.scannersWithNews')}
                        </h3>
                        <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                            {t('announcement.scannersWithNewsDesc')}
                        </p>
                    </div>
                </div>

                {/* Feature 2: Catalyst Alerts */}
                <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-amber-50 rounded-lg flex-shrink-0">
                        <Zap className="w-4 h-4 text-amber-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-slate-900 text-sm">
                            {t('announcement.catalystAlerts')}
                        </h3>
                        <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                            {t('announcement.catalystAlertsDesc')}
                        </p>
                    </div>
                </div>

                {/* Feature 3: Multi-language */}
                <div className="flex items-start gap-3">
                    <div className="p-1.5 bg-emerald-50 rounded-lg flex-shrink-0">
                        <Globe className="w-4 h-4 text-emerald-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-slate-900 text-sm">
                            {t('announcement.multiLanguage')}
                        </h3>
                        <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
                            {t('announcement.multiLanguageDesc')}
                        </p>
                    </div>
                </div>

                {/* Footer */}
                <div className="pt-2 flex justify-end">
                    <button
                        onClick={handleDismiss}
                        className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                        {t('announcement.dismiss')}
                    </button>
                </div>
            </div>
        </div>
    );
}
