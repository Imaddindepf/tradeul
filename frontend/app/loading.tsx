export default function Loading() {
  return (
    <div className="min-h-screen bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-solid border-blue-600 border-r-transparent mb-4"></div>
        <h2 className="text-xl font-semibold text-gray-900">Cargando...</h2>
        <p className="text-gray-600 mt-2">Por favor espera</p>
      </div>
    </div>
  );
}


