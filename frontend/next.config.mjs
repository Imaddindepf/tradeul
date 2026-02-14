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

  // Optimización de producción
  swcMinify: true,
  
  // React strict mode
  reactStrictMode: true,

  // Configuración de imágenes (si usas next/image)
  images: {
    domains: ['localhost'],
  },

  // Generar ETags para mejor cache
  generateEtags: true,

  // Comprimir respuestas (Caddy también puede hacerlo)
  compress: true,

  // Asegurar que los assets estáticos tengan rutas estables
  generateBuildId: async () => {
    // Usar git commit hash o timestamp consistente durante el build
    return process.env.BUILD_ID || `build-${Date.now()}`;
  },
};

export default nextConfig;

