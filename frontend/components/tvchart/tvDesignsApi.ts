/**
 * Cliente del backend de diseños del chart TVC (/api/v1/tv-designs).
 * La lista trae solo metadatos; el payload se pide por id.
 */

const API_URL =
    process.env.NODE_ENV === 'development'
        ? '/tvproxy'
        : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface TVDesignMeta {
    id: string;
    name: string;
    favorite: boolean;
    symbol?: string | null;
    interval?: string | null;
    updatedAt: number;
}

export type GetToken = () => Promise<string | null>;

async function call<T>(
    getToken: GetToken,
    path: string,
    init?: RequestInit,
): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${API_URL}/api/v1${path}`, {
        ...init,
        headers,
        credentials: 'include',
        cache: 'no-store',
    });
    if (!res.ok) throw new Error(`tv-api ${path} ${res.status}`);
    return res.json() as Promise<T>;
}

/** Último estado TVC del usuario: diseño activo o estado sin nombre. */
export interface TVLastState {
    designId?: string | null;
    designName?: string | null;
    payload?: object | null;
}

/**
 * Dibujos GLOBALES por (usuario, símbolo) — modo "sincronizar a nivel global"
 * de TV: el estado de dibujos de un símbolo aparece en cualquier layout o
 * diseño que lo cargue.
 */
/**
 * CRÍTICO: LineToolsAndGroupsState de la CL usa `Map` en sources/groups y
 * JSON.stringify(Map) === '{}' — sin conversión explícita se guardaban
 * estados VACÍOS (bug 2026-07-26: 7 PUTs de ASML con cáscara vacía). Este
 * cliente posee el formato de cable: objetos planos en el backend, Maps
 * hacia/desde la librería.
 */
interface WireDrawingsState {
    symbol?: string;
    sources?: Record<string, unknown> | null;
    groups?: Record<string, unknown> | null;
}

export const tvDrawingsApi = {
    /** Devuelve el estado listo para applyLineToolsState (Maps), o null. */
    get: async (t: GetToken, symbol: string): Promise<object | null> => {
        const res = await call<{ symbol: string; state: WireDrawingsState | null }>(
            t,
            `/tv-drawings/${encodeURIComponent(symbol.toUpperCase())}`,
        );
        if (!res.state) return null;
        return {
            symbol: res.state.symbol,
            sources: new Map(Object.entries(res.state.sources ?? {})),
            groups: new Map(Object.entries(res.state.groups ?? {})),
        };
    },
    /**
     * MERGE por dibujo (semántica TV "los NUEVOS dibujos"): cada clave es el
     * id de un dibujo; su valor es el LineToolState o null (tombstone =
     * borrarlo). El servidor fusiona — jamás se reemplaza el estado entero,
     * los dibujos antiguos no se tocan.
     */
    patch: (t: GetToken, symbol: string, sources: Record<string, unknown | null>) =>
        call<{ ok: boolean; sources: number }>(
            t,
            `/tv-drawings/${encodeURIComponent(symbol.toUpperCase())}`,
            { method: 'PUT', body: JSON.stringify({ state: { sources } }) },
        ),
};

export const tvDesignsApi = {
    list: (t: GetToken) => call<TVDesignMeta[]>(t, '/tv-designs'),
    /** Ajustes de usuario del chart (independientes de los diseños). */
    getSettings: async (t: GetToken): Promise<Record<string, unknown>> =>
        (await call<{ settings: Record<string, unknown> }>(t, '/tv-designs/settings')).settings ?? {},
    /** Merge: solo pisa las claves enviadas. */
    setSettings: (t: GetToken, settings: Record<string, unknown>) =>
        call<{ ok: boolean }>(t, '/tv-designs/settings', {
            method: 'PUT',
            body: JSON.stringify({ settings }),
        }),
    /** Restauración al abrir la ventana TVC sin estado local. */
    getLast: (t: GetToken) => call<TVLastState>(t, '/tv-designs/last'),
    /** designId = diseño activo; payload = estado sin nombre (excluyentes). */
    setLast: (t: GetToken, body: { designId?: string | null; payload?: object | null }) =>
        call<{ ok: boolean }>(t, '/tv-designs/last', { method: 'PUT', body: JSON.stringify(body) }),
    create: (t: GetToken, name: string, payload: object) =>
        call<TVDesignMeta>(t, '/tv-designs', { method: 'POST', body: JSON.stringify({ name, payload }) }),
    getPayload: async (t: GetToken, id: string) =>
        (await call<{ payload: object }>(t, `/tv-designs/${id}`)).payload,
    update: (
        t: GetToken,
        id: string,
        patch: { name?: string; favorite?: boolean; payload?: object },
    ) => call<TVDesignMeta>(t, `/tv-designs/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
    remove: (t: GetToken, id: string) => call<{ ok: boolean }>(t, `/tv-designs/${id}`, { method: 'DELETE' }),
};
