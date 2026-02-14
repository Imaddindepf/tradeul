'use client';

import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MapPin,
  CheckCircle2,
  ArrowRight,
  User,
  Mail,
  MessageSquare,
} from 'lucide-react';

// --- Types (TypeScript estricto) ---
export type EventInterest =
  | 'workshops'
  | 'networking'
  | 'live_trading'
  | 'q_and_a'
  | 'all';

export interface EventSignupPayload {
  name: string;
  email: string;
  interest: EventInterest;
  message: string;
}

export interface EventSignupFormProps {
  /** Título principal del evento */
  eventTitle?: string;
  /** Subtítulo o descripción corta */
  eventSubtitle?: string;
  /** Lugar (ej. Madrid) */
  location?: string;
  /** Texto del botón de envío */
  submitLabel?: string;
  /** Callback al enviar (aquí conectarías tu API/backend) */
  onSubmit?: (payload: EventSignupPayload) => Promise<void> | void;
  /** Clases extra para el contenedor */
  className?: string;
}

const INTEREST_OPTIONS: { value: EventInterest; label: string }[] = [
  { value: 'all', label: 'Todo me interesa' },
  { value: 'workshops', label: 'Workshops prácticos' },
  { value: 'networking', label: 'Networking con traders' },
  { value: 'live_trading', label: 'Live trading / demos' },
  { value: 'q_and_a', label: 'Q&A con el equipo' },
];

const defaultPayload: EventSignupPayload = {
  name: '',
  email: '',
  interest: 'all',
  message: '',
};

function validateEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function EventSignupForm({
  eventTitle = 'Tradeul Live',
  eventSubtitle = 'Encuentro de trading en Madrid. Reserva tu plaza.',
  location = 'Madrid',
  submitLabel = 'Reservar mi plaza',
  onSubmit,
  className = '',
}: EventSignupFormProps) {
  const [payload, setPayload] = useState<EventSignupPayload>(defaultPayload);
  const [touched, setTouched] = useState<Partial<Record<keyof EventSignupPayload, boolean>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const errors = {
    name: payload.name.trim().length < 2 ? 'Nombre demasiado corto' : null,
    email: !payload.email
      ? 'El email es obligatorio'
      : !validateEmail(payload.email)
        ? 'Email no válido'
        : null,
  };
  const isValid = !errors.name && !errors.email;

  const handleChange = useCallback(
    (field: keyof EventSignupPayload, value: string | EventInterest) => {
      setPayload((prev) => ({ ...prev, [field]: value }));
      setSubmitError(null);
    },
    []
  );

  const handleBlur = useCallback((field: keyof EventSignupPayload) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!isValid || isSubmitting) return;
      setIsSubmitting(true);
      setSubmitError(null);
      try {
        await onSubmit?.(payload);
        setSubmitted(true);
        setPayload(defaultPayload);
        setTouched({});
      } catch (err) {
        setSubmitError(err instanceof Error ? err.message : 'Error al enviar. Inténtalo de nuevo.');
      } finally {
        setIsSubmitting(false);
      }
    },
    [payload, isValid, isSubmitting, onSubmit]
  );

  return (
    <div
      className={`relative overflow-hidden rounded-2xl bg-white border border-slate-200 shadow-xl shadow-slate-200/50 ${className}`}
    >
      <div className="absolute inset-x-0 top-0 h-0.5 bg-blue-600 rounded-t-2xl" />

      <div className="relative px-6 sm:px-8 py-8 sm:py-10">
        <AnimatePresence mode="wait">
          {submitted ? (
            <motion.div
              key="success"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-center py-10"
            >
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-slate-100 text-blue-600 mb-5">
                <CheckCircle2 className="w-7 h-7" strokeWidth={2} />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-1">
                Plaza reservada
              </h3>
            </motion.div>
          ) : (
            <motion.form
              key="form"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              onSubmit={handleSubmit}
              className="space-y-6"
            >
              <div className="text-center space-y-2 pb-6 border-b border-slate-100">
                <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                  {eventTitle === 'Tradeul Live' ? (
                    <>
                      <span className="text-slate-900">Tradeul </span>
                      <span className="text-blue-600">Live</span>
                    </>
                  ) : (
                    <span className="text-slate-900">{eventTitle}</span>
                  )}
                </h2>
                <p className="text-slate-500 text-sm">{eventSubtitle}</p>
                <p className="text-slate-500 text-sm flex items-center justify-center gap-1.5">
                  <MapPin className="w-4 h-4 text-blue-500/80" aria-hidden />
                  <span>{location}</span>
                </p>
              </div>

              <div className="space-y-4">
                {/* Nombre */}
                <div>
                  <label
                    htmlFor="event-name"
                    className="block text-sm font-medium text-slate-700 mb-1.5"
                  >
                    Nombre
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                    <input
                      id="event-name"
                      type="text"
                      value={payload.name}
                      onChange={(e) => handleChange('name', e.target.value)}
                      onBlur={() => handleBlur('name')}
                      placeholder="Tu nombre"
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all"
                      autoComplete="name"
                    />
                  </div>
                  {touched.name && errors.name && (
                    <p className="mt-1 text-xs text-red-500">{errors.name}</p>
                  )}
                </div>

                {/* Email */}
                <div>
                  <label
                    htmlFor="event-email"
                    className="block text-sm font-medium text-slate-700 mb-1.5"
                  >
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                    <input
                      id="event-email"
                      type="email"
                      value={payload.email}
                      onChange={(e) => handleChange('email', e.target.value)}
                      onBlur={() => handleBlur('email')}
                      placeholder="tu@email.com"
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all"
                      autoComplete="email"
                    />
                  </div>
                  {touched.email && errors.email && (
                    <p className="mt-1 text-xs text-red-500">{errors.email}</p>
                  )}
                </div>

                {/* Interés */}
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    ¿En qué te interesa más?
                  </label>
                  <select
                    value={payload.interest}
                    onChange={(e) => handleChange('interest', e.target.value as EventInterest)}
                    className="w-full px-4 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all appearance-none cursor-pointer"
                    style={{
                      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
                      backgroundRepeat: 'no-repeat',
                      backgroundPosition: 'right 0.75rem center',
                      backgroundSize: '1.25rem',
                      paddingRight: '2.5rem',
                    }}
                  >
                    {INTEREST_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Mensaje opcional */}
                <div>
                  <label
                    htmlFor="event-message"
                    className="block text-sm font-medium text-slate-700 mb-1.5"
                  >
                    Mensaje <span className="text-slate-400 font-normal">(opcional)</span>
                  </label>
                  <div className="relative">
                    <MessageSquare className="absolute left-3 top-3 w-4 h-4 text-slate-400 pointer-events-none" />
                    <textarea
                      id="event-message"
                      value={payload.message}
                      onChange={(e) => handleChange('message', e.target.value)}
                      placeholder="Preguntas, sugerencias..."
                      rows={3}
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-slate-200 bg-white text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all resize-none"
                    />
                  </div>
                </div>
              </div>

              {submitError && (
                <p className="text-sm text-red-500 text-center">{submitError}</p>
              )}

              <motion.button
                type="submit"
                disabled={!isValid || isSubmitting}
                whileHover={isValid && !isSubmitting ? { scale: 1.01 } : {}}
                whileTap={isValid && !isSubmitting ? { scale: 0.99 } : {}}
                className="w-full py-3.5 rounded-lg font-medium text-white flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isSubmitting ? (
                  <span className="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    {submitLabel}
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </motion.button>
            </motion.form>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
