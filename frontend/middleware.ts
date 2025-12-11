import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

// Rutas públicas que NO requieren autenticación
const isPublicRoute = createRouteMatcher([
  '/',                    // Landing page
  '/sign-in(.*)',         // Páginas de login
  '/sign-up(.*)',         // Páginas de registro
  '/api/public(.*)',      // APIs públicas (si las hay)
  '/icon',                // Favicon dinámico
  '/apple-icon',          // Apple touch icon
])

export default clerkMiddleware(async (auth, req) => {
  // Si NO es ruta pública, verificar autenticación
  if (!isPublicRoute(req)) {
    const { userId } = await auth()

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

