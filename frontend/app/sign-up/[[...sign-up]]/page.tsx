'use client';

import { SignUp } from '@clerk/nextjs';
import { useEffect, useState } from 'react';

export default function SignUpPage() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="w-full max-w-md">
        {/* Logo/Branding */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            Tradeul
          </h1>
          <p className="text-slate-400">
            Crea tu cuenta gratuita
          </p>
        </div>

        {/* Clerk Sign Up Component - Solo renderizar en cliente */}
        {mounted ? (
          <SignUp
            fallbackRedirectUrl="/workspace"
            appearance={{
              elements: {
                rootBox: "mx-auto",
                card: "bg-slate-800/50 border border-slate-700 shadow-2xl backdrop-blur-sm",
                headerTitle: "text-white",
                headerSubtitle: "text-slate-400",
                socialButtonsBlockButton: "bg-slate-700 border-slate-600 text-white hover:bg-slate-600",
                formFieldLabel: "text-slate-300",
                formFieldInput: "bg-slate-700 border-slate-600 text-white placeholder:text-slate-500",
                formButtonPrimary: "bg-blue-600 hover:bg-blue-500 text-white",
                footerActionLink: "text-blue-400 hover:text-blue-300",
                identityPreviewText: "text-white",
                identityPreviewEditButton: "text-blue-400",
                footer: "hidden",
              },
              layout: {
                socialButtonsPlacement: "bottom",
                socialButtonsVariant: "iconButton",
              }
            }}
          />
        ) : (
          <div className="flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
          </div>
        )}
      </div>
    </div>
  );
}

