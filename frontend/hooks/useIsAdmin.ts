'use client';

import { useUser } from '@clerk/nextjs';

/**
 * Returns true when the currently signed-in user has the "admin" role.
 *
 * The role lives in Clerk's `publicMetadata.roles` array (mirrored by the
 * backend `AuthenticatedUser.is_admin` property). The check happens client-
 * side ONLY for UI gating — every protected endpoint must still validate
 * the JWT and enforce `require_admin` on the server.
 *
 * Returns false until Clerk finishes loading, so consumers can safely
 * render this as a guard without flicker.
 */
export function useIsAdmin(): boolean {
  const { user, isLoaded } = useUser();
  if (!isLoaded || !user) return false;
  const metadata = user.publicMetadata as { roles?: unknown } | null | undefined;
  const roles = metadata?.roles;
  if (Array.isArray(roles)) {
    return roles.some((r) => typeof r === 'string' && r.toLowerCase() === 'admin');
  }
  if (typeof roles === 'string') {
    return roles.toLowerCase() === 'admin';
  }
  return false;
}
