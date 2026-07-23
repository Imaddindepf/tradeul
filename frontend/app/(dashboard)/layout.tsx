import { AppShell } from '@/components/layout/AppShell';
import { MobileBlocker } from '@/components/ui/MobileBlocker';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // El aviso "diseñado para escritorio" solo aplica a la app (workspace, etc.).
  // La landing, sign-in/sign-up e invitaciones son accesibles desde móvil.
  return (
    <MobileBlocker>
      <AppShell>{children}</AppShell>
    </MobileBlocker>
  );
}


