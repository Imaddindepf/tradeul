import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

// Rutas públicas que NO requieren autenticación
const isPublicRoute = createRouteMatcher([
  '/',                    // Landing page
  '/sign-in(.*)',         // Páginas de login
  '/sign-up(.*)',         // Páginas de registro
  '/api/public(.*)',      // APIs públicas (si las hay)
])

export default clerkMiddleware(async (auth, req) => {
  // Si NO es ruta pública, requiere autenticación
  if (!isPublicRoute(req)) {
    await auth.protect()
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

