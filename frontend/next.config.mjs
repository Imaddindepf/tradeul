/** @type {import('next').NextConfig} */
const nextConfig = {
  // Build-time env vars (evaluated once during `npm run build`)
  // NEXT_PUBLIC_* are available in client-side code
  env: {
    NEXT_PUBLIC_BUILD_TIMESTAMP: Date.now().toString(),
  },

  // Transpilar paquetes ESM que Next.js no maneja por defecto
  transpilePackages: ['@tanstack/react-table', '@tanstack/table-core', '@tanstack/react-virtual'],

  // Configuración para SharedWorkers (sin worker-loader)
  webpack: (config, { isServer }) => {
    if (!isServer) {
      // Configuración mínima para SharedWorkers
      config.output.globalObject = 'self';
    }
    return config;
  },

  // Proxy same-origin hacia el API gateway SOLO en dev: el puerto 3002 no
  // está en la allowlist CORS del gateway, así que la ventana TradingView
  // (components/tvchart) pasa por aquí en desarrollo. En producción llama
  // a NEXT_PUBLIC_API_URL directamente y esta regla no se registra.
  async rewrites() {
    if (process.env.NODE_ENV !== 'development') return [];
    return [
      {
        source: '/tvproxy/:path*',
        destination: 'https://api.tradeul.com/:path*',
      },
    ];
  },

  // Optimización de producción
  swcMinify: true,
  
  // React strict mode
  reactStrictMode: true,

  // Configuración de imágenes (si usas next/image)
  images: {
    domains: ['localhost'],
  },
};

export default nextConfig;

