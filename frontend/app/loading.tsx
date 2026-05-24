/**
 * Loading global (Next.js Suspense fallback entre rutas).
 *
 * Diseño: mismo fondo crema del landing ("bg-white") con el wordmark "tradeul"
 * centrado y una barra azul de progreso indeterminada debajo. Sin spinners
 * genéricos ni texto "Loading…". Lo más parecido a Linear / Stripe / Vercel.
 */
export default function Loading() {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-white">
      <div className="flex flex-col items-center gap-5">
        <span className="relative inline-flex items-baseline leading-none font-semibold tracking-[-0.035em] text-slate-900 text-[28px]">
          <span>tradeul</span>
          <span
            aria-hidden
            className="absolute left-0 bottom-[-5px] h-[3px] rounded-full bg-[#2563eb]"
            style={{ width: '0.48em' }}
          />
        </span>

        <div className="relative h-[2px] w-40 overflow-hidden rounded-full bg-slate-100">
          <span
            aria-hidden
            className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-[#2563eb] animate-[loading-slide_1.2s_ease-in-out_infinite]"
          />
        </div>
      </div>

      <style>{`
        @keyframes loading-slide {
          0%   { transform: translateX(-100%); }
          50%  { transform: translateX(150%); }
          100% { transform: translateX(400%); }
        }
      `}</style>
    </div>
  );
}
