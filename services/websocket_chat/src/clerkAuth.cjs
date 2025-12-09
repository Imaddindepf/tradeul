/**
 * Clerk JWT Verification for WebSocket Server
 * 
 * Verifica tokens JWT de Clerk usando JWKS (JSON Web Key Set)
 * - JWKS se cachea por 1 hora
 * - Verificación local (~1ms)
 */

const jwt = require('jsonwebtoken');
const jwksClient = require('jwks-rsa');

// Obtener dominio de Clerk desde CLERK_PUBLISHABLE_KEY
function getClerkDomain() {
  const pk = process.env.CLERK_PUBLISHABLE_KEY || '';
  if (!pk) return null;
  
  const parts = pk.split('_');
  if (parts.length < 3) return null;
  
  try {
    // El dominio está en base64 en la tercera parte
    let encoded = parts[2];
    // Añadir padding si es necesario
    const padding = 4 - (encoded.length % 4);
    if (padding !== 4) {
      encoded += '='.repeat(padding);
    }
    const decoded = Buffer.from(encoded, 'base64').toString('utf-8');
    // Quitar $ del final
    return decoded.replace(/\$$/, '');
  } catch (e) {
    console.error('Failed to decode CLERK_PUBLISHABLE_KEY:', e);
    return null;
  }
}

// Cliente JWKS con caché
let jwksClientInstance = null;
let clerkDomain = null;

function getJwksClient() {
  if (!jwksClientInstance) {
    clerkDomain = getClerkDomain();
    if (!clerkDomain) {
      console.warn('⚠️ CLERK_PUBLISHABLE_KEY not set - WebSocket auth disabled');
      return null;
    }
    
    const jwksUri = `https://${clerkDomain}/.well-known/jwks.json`;
    console.log(`🔐 Clerk JWKS URL: ${jwksUri}`);
    
    jwksClientInstance = jwksClient({
      jwksUri,
      cache: true,
      cacheMaxAge: 3600000, // 1 hora en ms
      rateLimit: true,
      jwksRequestsPerMinute: 10,
    });
  }
  return jwksClientInstance;
}

// Función para obtener la signing key
function getSigningKey(header, callback) {
  const client = getJwksClient();
  if (!client) {
    return callback(new Error('JWKS client not initialized'));
  }
  
  client.getSigningKey(header.kid, (err, key) => {
    if (err) {
      return callback(err);
    }
    const signingKey = key.publicKey || key.rsaPublicKey;
    callback(null, signingKey);
  });
}

/**
 * Verificar token JWT de Clerk
 * @param {string} token - Token JWT sin el prefijo "Bearer "
 * @returns {Promise<object>} - Payload del token si es válido
 */
async function verifyClerkToken(token) {
  return new Promise((resolve, reject) => {
    if (!token) {
      return reject(new Error('Token is required'));
    }
    
    const client = getJwksClient();
    if (!client) {
      // Si no hay cliente JWKS, auth está desactivada
      return resolve({ sub: 'anonymous', email: null });
    }
    
    jwt.verify(
      token,
      getSigningKey,
      {
        algorithms: ['RS256'],
        issuer: `https://${clerkDomain}`,
      },
      (err, decoded) => {
        if (err) {
          return reject(err);
        }
        resolve(decoded);
      }
    );
  });
}

/**
 * Extraer token del query string de la URL
 * @param {string} url - URL completa o path con query
 * @returns {string|null} - Token o null
 */
function extractTokenFromUrl(url) {
  try {
    // Puede ser solo path+query o URL completa
    const fullUrl = url.startsWith('/') ? `http://localhost${url}` : url;
    const parsed = new URL(fullUrl);
    return parsed.searchParams.get('token');
  } catch (e) {
    return null;
  }
}

// Verificar si auth está habilitada
function isAuthEnabled() {
  const enabled = process.env.WS_AUTH_ENABLED === 'true';
  const hasPk = !!process.env.CLERK_PUBLISHABLE_KEY;
  return enabled && hasPk;
}

module.exports = {
  verifyClerkToken,
  extractTokenFromUrl,
  isAuthEnabled,
  getClerkDomain,
};

