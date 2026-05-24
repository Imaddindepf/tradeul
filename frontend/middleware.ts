import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

/**
 * Routes that don't require authentication.
 *
 * Anything matched here is rendered as-is for anonymous visitors. Anything
 * NOT matched falls through to the auth gate and redirects unauthenticated
 * users to /sign-in (preserving the original URL via `redirect_url`).
 */
const isPublicRoute = createRouteMatcher([
    '/',                 // Landing page
    '/event',            // Event signup form (Primer Tradeul Event)
    '/sign-in(.*)',      // Clerk sign-in pages incl. SSO callback
    '/sign-up(.*)',      // Clerk sign-up pages
    '/invite(.*)',       // Group invitation pages — auto-join after auth
    '/api/public(.*)',   // Public API endpoints
    '/api/mockup',       // Design mockup (temporary)
    '/icon',             // Dynamic favicon
    '/apple-icon',       // Apple touch icon
])

/**
 * Pages that finalise a Clerk session task (e.g. mandatory password reset).
 * These pages must be reachable while the user has a `currentTask` even
 * though they're behind the auth gate.
 */
const isTaskRoute = createRouteMatcher(['/tasks(.*)'])

export default clerkMiddleware(async (auth, req) => {
    const { userId, sessionClaims } = await auth()

    // ── Pending session tasks (mandatory password reset, etc.) ─────────────
    // If the user is signed in but Clerk has flagged a `currentTask` we MUST
    // route them through the task page first. Without this, they'd land on
    // the dashboard with an unresolved security-critical action pending.
    if (userId && sessionClaims) {
        const currentTask = (sessionClaims as any)?.currentTask

        if (currentTask?.key === 'reset-password' && !isTaskRoute(req)) {
            const taskUrl = new URL('/tasks/reset-password', req.url)
            return NextResponse.redirect(taskUrl)
        }
    }

    // ── Auth gate ──────────────────────────────────────────────────────────
    // Protected route + no session → bounce to the dedicated /sign-in page,
    // preserving where the user was trying to go via `redirect_url`. Clerk's
    // <SignIn /> reads that query param and uses it instead of the global
    // fallback, so after Google OAuth the user lands on their original URL.
    if (!isPublicRoute(req)) {
        if (!userId) {
            const signInUrl = new URL('/sign-in', req.url)
            const originalPath = req.nextUrl.pathname + req.nextUrl.search
            // Don't echo back trivial paths that would loop into the gate.
            if (originalPath && originalPath !== '/' && !originalPath.startsWith('/sign-in')) {
                signInUrl.searchParams.set('redirect_url', originalPath)
            }
            return NextResponse.redirect(signInUrl)
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
