import { auth, currentUser } from '@clerk/nextjs/server'

export type UserRole = 'admin' | 'user'

/**
 * Obtiene el rol del usuario actual (server-side)
 */
export async function getUserRole(): Promise<UserRole> {
  const user = await currentUser()
  return (user?.publicMetadata?.role as UserRole) || 'user'
}

/**
 * Verifica si el usuario actual es admin (server-side)
 */
export async function isAdmin(): Promise<boolean> {
  const role = await getUserRole()
  return role === 'admin'
}

/**
 * Obtiene el ID del usuario actual (server-side)
 */
export async function getUserId(): Promise<string | null> {
  const { userId } = await auth()
  return userId
}

/**
 * Verifica si el usuario está autenticado (server-side)
 */
export async function isAuthenticated(): Promise<boolean> {
  const { userId } = await auth()
  return !!userId
}

