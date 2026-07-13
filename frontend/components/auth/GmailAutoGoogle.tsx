'use client';

import { useEffect, useRef, type ReactNode } from 'react';

// gmail.com y googlemail.com (alias oficial de Gmail en algunos países)
const GMAIL_RE = /@(gmail|googlemail)\.com\s*$/i;

/**
 * Envuelve un <SignIn> de Clerk: si el usuario escribe un correo de Gmail y
 * pulsa "Continuar" (o Enter), disparamos el botón "Continue with Google" en
 * su lugar. Los usuarios de Gmail casi siempre crearon su cuenta con Google
 * y no saben que deben usar ese botón — con esto el flujo correcto es
 * automático y Clerk vincula la sesión a la misma cuenta.
 */
export default function GmailAutoGoogle({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;

    const clickGoogle = (): boolean => {
      const googleBtn = root.querySelector<HTMLButtonElement>(
        'button.cl-socialButtonsBlockButton__google, button[class*="socialButtonsBlockButton__google"]'
      );
      if (!googleBtn) return false;
      googleBtn.click();
      return true;
    };

    const identifierIsGmail = (): boolean => {
      const input = root.querySelector<HTMLInputElement>('input[name="identifier"]');
      return !!input && GMAIL_RE.test(input.value.trim());
    };

    // Click en "Continuar" con un correo de Gmail → redirigir a Google OAuth.
    // Fase de captura: llegamos antes de que Clerk procese el submit.
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target?.closest('button.cl-formButtonPrimary, button[class*="formButtonPrimary"]')) return;
      if (!identifierIsGmail()) return;
      if (clickGoogle()) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    // Enter dentro del campo de email con un correo de Gmail → ídem.
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return;
      const target = e.target as HTMLElement | null;
      if (!(target instanceof HTMLInputElement) || target.name !== 'identifier') return;
      if (!GMAIL_RE.test(target.value.trim())) return;
      if (clickGoogle()) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    root.addEventListener('click', onClick, true);
    root.addEventListener('keydown', onKeyDown, true);
    return () => {
      root.removeEventListener('click', onClick, true);
      root.removeEventListener('keydown', onKeyDown, true);
    };
  }, []);

  // display:contents — no altera el layout, solo captura eventos del subárbol
  return (
    <div ref={ref} className="contents">
      {children}
    </div>
  );
}
