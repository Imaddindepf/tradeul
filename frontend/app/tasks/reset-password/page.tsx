'use client';

import { useSession, useClerk } from '@clerk/nextjs';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function ResetPasswordTaskPage() {
  const { session, isLoaded } = useSession();
  const { signOut } = useClerk();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isLoaded) return;
    
    // Si no hay sesión o no hay task de reset-password, redirigir
    if (!session) {
      router.push('/sign-in');
      return;
    }

    // Verificar si hay un task de reset-password pendiente
    const currentTask = (session as any).currentTask;
    if (!currentTask || currentTask.key !== 'reset-password') {
      router.push('/workspace');
    }
  }, [session, isLoaded, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden');
      return;
    }

    if (newPassword.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres');
      return;
    }

    setLoading(true);

    try {
      // Actualizar la contraseña usando Clerk
      await session?.user?.updatePassword({
        newPassword,
        signOutOfOtherSessions: true,
      });

      // Resolver el task
      const currentTask = (session as any).currentTask;
      if (currentTask?.resolve) {
        await currentTask.resolve();
      }

      // Redirigir al workspace
      router.push('/workspace');
    } catch (err: any) {
      console.error('Error updating password:', err);
      setError(err.errors?.[0]?.message || 'Error al actualizar la contraseña');
    } finally {
      setLoading(false);
    }
  };

  if (!mounted || !isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="w-full max-w-md">
        {/* Logo/Branding */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            Tradeul
          </h1>
          <p className="text-slate-400">
            Actualiza tu contraseña
          </p>
        </div>

        {/* Reset Password Form */}
        <div className="bg-slate-800/50 border border-slate-700 shadow-2xl backdrop-blur-sm rounded-xl p-6">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-white mb-2">
              Restablece tu contraseña
            </h2>
            <p className="text-sm text-slate-400">
              Por seguridad, necesitas actualizar tu contraseña para continuar.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="newPassword" className="block text-sm font-medium text-slate-300 mb-1">
                Nueva contraseña
              </label>
              <input
                type="password"
                id="newPassword"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Mínimo 8 caracteres"
                required
                minLength={8}
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-300 mb-1">
                Confirmar contraseña
              </label>
              <input
                type="password"
                id="confirmPassword"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Repite la contraseña"
                required
              />
            </div>

            {error && (
              <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
            >
              {loading ? 'Actualizando...' : 'Actualizar contraseña'}
            </button>
          </form>

          <div className="mt-4 pt-4 border-t border-slate-700">
            <button
              onClick={() => signOut({ redirectUrl: '/sign-in' })}
              className="w-full text-center text-sm text-slate-400 hover:text-slate-300 transition-colors"
            >
              Cerrar sesión e intentar más tarde
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

