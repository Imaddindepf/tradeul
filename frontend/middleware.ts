import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

// Rutas públicas que NO requieren autenticación
const isPublicRoute = createRouteMatcher([
  '/',                    // Landing page
  '/event',               // Formulario inscripción evento (Primer Tradeul Event)
  '/sign-in(.*)',         // Páginas de login
  '/sign-up(.*)',         // Páginas de registro
  '/tasks(.*)',           // Task pages (reset-password, etc.)
  '/invite(.*)',          // Páginas de invitación a grupos (reset-password, etc.)
  '/api/public(.*)',      // APIs públicas (si las hay)
  '/icon',                // Favicon dinámico
  '/apple-icon',          // Apple touch icon
])

// Rutas de tasks
const isTaskRoute = createRouteMatcher(['/tasks(.*)'])

export default clerkMiddleware(async (auth, req) => {
  const { userId, sessionClaims } = await auth()

  // Si está autenticado y tiene un session task pendiente
  if (userId && sessionClaims) {
    const currentTask = (sessionClaims as any)?.currentTask

    // Si hay un task de reset-password y NO estamos ya en la página de task
    if (currentTask?.key === 'reset-password' && !isTaskRoute(req)) {
      const taskUrl = new URL('/tasks/reset-password', req.url)
      return NextResponse.redirect(taskUrl)
    }
  }

  // Si NO es ruta pública, verificar autenticación
  if (!isPublicRoute(req)) {
    // Si no está autenticado, redirigir a la landing page
    if (!userId) {
      const landingUrl = new URL('/', req.url)
      return NextResponse.redirect(landingUrl)
    }
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}

