'use client';

import { motion } from 'framer-motion';
import { EventSignupForm, type EventSignupPayload } from '@/components/landing/EventSignupForm';
import { EventFormBackdropLeft, EventFormBackdropRight } from '@/components/landing/EventFormBackdrop';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

/**
 * Página prototipo del formulario de inscripción al evento.
 * Ruta: /event
 * Para producción: integrar la sección en la landing (/) o mantener esta ruta.
 */
export default function EventPage() {
  const handleSubmit = async (payload: EventSignupPayload) => {
    // Prototipo: solo log. En producción aquí iría tu API (ej. POST /api/event-signup)
    await new Promise((r) => setTimeout(r, 800));
  };

  return (
    <main className="min-h-screen bg-[#fafafa] text-slate-900 overflow-x-hidden">
      {/* Fondo con gradiente y patrón sutil */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-b from-white via-blue-50/30 to-slate-100" />
        <div
          className="absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage: 'radial-gradient(circle, #3b82f6 1px, transparent 1px)',
            backgroundSize: '28px 28px',
          }}
        />
      </div>

      <div className="relative z-10 py-12 sm:py-20 px-4 sm:px-6">
        {/* Link volver */}
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="max-w-md mx-auto mb-8 relative z-20"
        >
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-blue-600 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Volver a la landing
          </Link>
        </motion.div>

        {/* Layout: post-its a los lados del form (visibles, no detrás) */}
        <div className="flex flex-col sm:flex-row items-stretch justify-center gap-4 sm:gap-6 max-w-4xl mx-auto">
          <div className="hidden sm:block w-28 sm:w-36 flex-shrink-0 flex items-center justify-end">
            <EventFormBackdropLeft />
          </div>
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="flex-1 min-w-0 max-w-md mx-auto sm:mx-0 w-full"
          >
            <EventSignupForm onSubmit={handleSubmit} />
          </motion.div>
          <div className="hidden sm:block w-28 sm:w-36 flex-shrink-0 flex items-center justify-start">
            <EventFormBackdropRight />
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-slate-400">
          Tradeul Live · Madrid
        </p>
      </div>
    </main>
  );
}
