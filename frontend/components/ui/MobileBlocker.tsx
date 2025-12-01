'use client';

import { useState, useEffect } from 'react';
import { Monitor, ArrowRight } from 'lucide-react';

const MIN_DESKTOP_WIDTH = 1024;

export function MobileBlocker({ children }: { children: React.ReactNode }) {
    const [isMobile, setIsMobile] = useState(false);
    const [isChecking, setIsChecking] = useState(true);
    const [dismissed, setDismissed] = useState(false);

    useEffect(() => {
        const checkDevice = () => {
            setIsMobile(window.innerWidth < MIN_DESKTOP_WIDTH);
            setIsChecking(false);
        };

        checkDevice();
        window.addEventListener('resize', checkDevice);
        return () => window.removeEventListener('resize', checkDevice);
    }, []);

    if (isChecking) {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center">
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
        <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white flex flex-col">
            {/* Header con logo */}
            <div className="flex items-center gap-3 p-6 border-b border-slate-100">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
                    <span className="text-white font-bold text-xl">T</span>
                </div>
                <span className="text-lg font-semibold text-slate-900">Tradeul</span>
            </div>

            {/* Content */}
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                {/* Icon ilustrativo */}
                <div className="relative mb-8">
                    <div className="w-24 h-16 rounded-xl bg-white border-2 border-slate-200 shadow-xl flex items-center justify-center">
                        <Monitor className="w-10 h-10 text-blue-500" />
                    </div>
                    {/* Decorative elements */}
                    <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center">
                        <span className="text-white text-xs font-bold">!</span>
                    </div>
                    <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-8 h-1 rounded-full bg-slate-200" />
                </div>

                {/* Message */}
                <div className="max-w-xs space-y-4">
                    <h1 className="text-2xl font-bold text-slate-900">
                        Diseñado para escritorio
                    </h1>

                    <p className="text-slate-500 leading-relaxed">
                        Para operar con todas las herramientas profesionales,
                        necesitas una pantalla de al menos{' '}
                        <span className="font-semibold text-slate-700">{MIN_DESKTOP_WIDTH}px</span>.
                    </p>

                    {/* Visual hint */}
                    <div className="flex items-center justify-center gap-2 py-4">
                        <div className="w-8 h-6 rounded border-2 border-slate-300 bg-slate-100" />
                        <ArrowRight className="w-4 h-4 text-slate-400" />
                        <div className="w-16 h-10 rounded border-2 border-blue-400 bg-blue-50 flex items-center justify-center">
                            <div className="w-2 h-2 rounded-full bg-blue-500" />
                        </div>
                    </div>

                    <p className="text-sm text-slate-400">
                        Abre Tradeul desde tu ordenador
                    </p>
                </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-slate-100">
                <button
                    onClick={() => setDismissed(true)}
                    className="w-full py-3 px-4 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition-all active:scale-[0.98]"
                >
                    Continuar de todos modos
                </button>
            </div>
        </div>
    );
}
