/** @type {import('next').NextConfig} */
const nextConfig = {
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
};

export default nextConfig;

