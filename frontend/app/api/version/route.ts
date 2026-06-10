import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

// Leído UNA sola vez al arrancar el servidor: así devolvemos el build que este
// proceso está sirviendo realmente, no el que pueda haber en disco a mitad de
// un `npm run build` (evita avisar a los usuarios antes del restart).
let buildId = 'dev';
try {
  buildId = fs
    .readFileSync(path.join(process.cwd(), '.next', 'BUILD_ID'), 'utf8')
    .trim();
} catch {
  // Modo dev: .next/BUILD_ID no existe
}

export async function GET() {
  return NextResponse.json(
    { buildId },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
