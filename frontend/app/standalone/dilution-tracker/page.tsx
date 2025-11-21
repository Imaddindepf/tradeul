'use client';

import { DilutionTrackerContent } from '@/components/floating-window/DilutionTrackerContent';

/**
 * Página standalone de Dilution Tracker
 * Se abre en nueva ventana del navegador sin navbar ni sidebar
 */
export default function StandaloneDilutionTrackerPage() {
    return (
        <div className="h-screen w-screen overflow-hidden">
            <DilutionTrackerContent />
        </div>
    );
}

