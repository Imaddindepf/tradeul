/**
 * tapeReference — decodificación de condition codes y market centers para el
 * Time & Sales.
 *
 * Los prints llegan con IDs numéricos (Polygon): `c` = condition IDs y
 * `x` = exchange ID. La fuente canónica de los mapeos es el api_gateway
 * (GET /api/v1/tape/reference, que cachea /v3/reference/conditions y
 * /v3/reference/exchanges de Polygon). Este módulo mantiene además un
 * fallback estático verificado (2026-07) para que la ventana funcione
 * aunque el fetch falle.
 */

// ============================================================================
// Tipos del reference data (shape del endpoint /api/v1/tape/reference)
// ============================================================================

export interface TapeConditionRef {
    id: number;
    name: string;
    type?: string;
    sip_mapping?: Record<string, string>;
    update_rules?: {
        consolidated?: {
            updates_high_low?: boolean;
            updates_open_close?: boolean;
            updates_volume?: boolean;
        };
        market_center?: {
            updates_high_low?: boolean;
            updates_open_close?: boolean;
            updates_volume?: boolean;
        };
    };
    legacy?: boolean;
}

export interface TapeExchangeRef {
    id: number;
    type?: string;   // exchange | TRF | SIP
    name: string;
    participant_id?: string;
    mic?: string;
    acronym?: string;
}

export interface TapeReferenceData {
    conditions: TapeConditionRef[];
    exchanges: TapeExchangeRef[];
    fetched_at?: number;
}

// ============================================================================
// Fallback estático (verificado contra docs/fixtures oficiales de Polygon)
// ============================================================================

/** id → [letra SIP, nombre] */
const CONDITION_FALLBACK: Record<number, [string, string]> = {
    0: ['@', 'Regular Sale'],
    1: ['A', 'Acquisition'],
    2: ['W', 'Average Price Trade'],
    3: ['E', 'Automatic Execution'],
    4: ['B', 'Bunched Trade'],
    5: ['G', 'Bunched Sold Trade'],
    6: ['I', 'CAP Election'],
    7: ['C', 'Cash Sale'],
    8: ['6', 'Closing Prints'],
    9: ['X', 'Cross Trade'],
    10: ['4', 'Derivatively Priced'],
    11: ['D', 'Distribution'],
    12: ['T', 'Form T (Extended Hours)'],
    13: ['U', 'Extended Hours (Sold Out of Sequence)'],
    14: ['F', 'Intermarket Sweep'],
    15: ['M', 'Market Center Official Close'],
    16: ['Q', 'Market Center Official Open'],
    17: ['O', 'Market Center Opening Trade'],
    18: ['5', 'Market Center Reopening Trade'],
    19: ['6', 'Market Center Closing Trade'],
    20: ['N', 'Next Day'],
    21: ['H', 'Price Variation Trade'],
    22: ['P', 'Prior Reference Price'],
    23: ['K', 'Rule 155 Trade (AMEX)'],
    24: ['K', 'Rule 127 (NYSE)'],
    25: ['O', 'Opening Prints'],
    26: ['O', 'Opened'],
    27: ['1', 'Stopped Stock (Regular Trade)'],
    28: ['5', 'Re-Opening Prints'],
    29: ['R', 'Seller'],
    30: ['L', 'Sold Last'],
    32: ['Z', 'Sold Out'],
    33: ['Z', 'Sold (Out of Sequence)'],
    34: ['S', 'Split Trade'],
    35: ['V', 'Stock Option Trade'],
    36: ['Y', 'Yellow Flag Regular Trade'],
    37: ['I', 'Odd Lot Trade'],
    38: ['9', 'Corrected Consolidated Close'],
    39: ['?', 'Unknown'],
    40: ['·', 'Held'],
    41: ['·', 'Trade Thru Exempt'],
    42: ['·', 'NonEligible'],
    43: ['·', 'NonEligible Extended'],
    44: ['·', 'Cancelled'],
    45: ['·', 'Recovery'],
    46: ['·', 'Correction'],
    47: ['·', 'As of'],
    48: ['·', 'As of Correction'],
    49: ['·', 'As of Cancel'],
    52: ['V', 'Contingent Trade'],
    53: ['7', 'Qualified Contingent Trade (QCT)'],
    54: ['·', 'Errored'],
    60: ['·', 'SSR in Effect'],
};

/**
 * Condiciones que NO actualizan el last consolidado (updates_open_close=false).
 * Regla SIP: con varias condiciones, si cualquiera dice NO, gana el NO.
 * Fuente: update_rules de /v3/reference/conditions + specs CTA/UTP.
 */
const NO_UPDATE_LAST_FALLBACK = new Set([2, 5, 7, 10, 12, 13, 15, 16, 20, 21, 22, 29, 33, 37, 52, 53]);

/** exchange id → [letra participant, nombre] */
const EXCHANGE_FALLBACK: Record<number, [string, string]> = {
    1: ['A', 'NYSE American'],
    2: ['B', 'Nasdaq BX'],
    3: ['C', 'NYSE National'],
    4: ['D', 'FINRA (off-exchange)'],
    5: ['E', 'UTP SIP'],
    6: ['I', 'ISE Stocks'],
    7: ['J', 'Cboe EDGA'],
    8: ['K', 'Cboe EDGX'],
    9: ['M', 'NYSE Chicago'],
    10: ['N', 'New York Stock Exchange'],
    11: ['P', 'NYSE Arca'],
    12: ['T', 'Nasdaq'],
    13: ['S', 'CTA SIP'],
    14: ['L', 'Long-Term Stock Exchange'],
    15: ['V', 'IEX'],
    16: ['W', 'CBSX'],
    17: ['X', 'Nasdaq PSX'],
    18: ['Y', 'Cboe BYX'],
    19: ['Z', 'Cboe BZX'],
    20: ['H', 'MIAX Pearl'],
    21: ['U', 'MEMX'],
};

/** trf_id → nombre del Trade Reporting Facility (solo prints off-exchange) */
const TRF_NAMES: Record<number, string> = {
    201: 'FINRA / NYSE TRF',
    202: 'FINRA / Nasdaq TRF Carteret',
    203: 'FINRA / Nasdaq TRF Chicago',
};

// Condiciones "administrativas" (official open/close): no son trades reales.
export const OFFICIAL_PRINT_CONDITIONS = new Set([15, 16]);
// Extended hours
export const EXTENDED_HOURS_CONDITIONS = new Set([12, 13]);
// Prints de apertura/cierre/reapertura (subastas)
export const AUCTION_CONDITIONS = new Set([8, 17, 18, 19, 25, 28]);
// Odd lot
export const ODD_LOT_CONDITION = 37;

// ============================================================================
// Decoder
// ============================================================================

export class TapeDecoder {
    private condLetter = new Map<number, string>();
    private condName = new Map<number, string>();
    private noUpdateLast = new Set<number>(NO_UPDATE_LAST_FALLBACK);
    private exchLetter = new Map<number, string>();
    private exchName = new Map<number, string>();

    constructor(reference?: TapeReferenceData | null) {
        for (const [id, [letter, name]] of Object.entries(CONDITION_FALLBACK)) {
            this.condLetter.set(Number(id), letter);
            this.condName.set(Number(id), name);
        }
        for (const [id, [letter, name]] of Object.entries(EXCHANGE_FALLBACK)) {
            this.exchLetter.set(Number(id), letter);
            this.exchName.set(Number(id), name);
        }
        if (reference) this.merge(reference);
    }

    /** Superpone el reference data dinámico del gateway sobre el fallback. */
    merge(reference: TapeReferenceData) {
        for (const c of reference.conditions || []) {
            if (typeof c.id !== 'number') continue;
            if (c.name) this.condName.set(c.id, c.name);
            const letter = c.sip_mapping?.UTP || c.sip_mapping?.CTA;
            if (letter) this.condLetter.set(c.id, letter);
            const updatesLast = c.update_rules?.consolidated?.updates_open_close;
            if (updatesLast === false) this.noUpdateLast.add(c.id);
            else if (updatesLast === true) this.noUpdateLast.delete(c.id);
        }
        for (const e of reference.exchanges || []) {
            if (typeof e.id !== 'number') continue;
            // El id 4 aparece en varias filas (los 4 TRFs de FINRA) — con la
            // letra D nos vale cualquiera; no sobrescribir el nombre genérico.
            if (e.id === 4) continue;
            if (e.participant_id) this.exchLetter.set(e.id, e.participant_id);
            if (e.name) this.exchName.set(e.id, e.name);
        }
    }

    conditionLetter(id: number): string {
        return this.condLetter.get(id) ?? String(id);
    }

    conditionName(id: number): string {
        return this.condName.get(id) ?? `Condition ${id}`;
    }

    /** Letras de todas las condiciones de un print (p.ej. "@ F"). */
    conditionLetters(ids?: number[]): string {
        if (!ids || ids.length === 0) return '@';
        return ids.map((id) => this.conditionLetter(id)).join(' ');
    }

    /** Nombres completos, para tooltip. */
    conditionNames(ids?: number[]): string {
        if (!ids || ids.length === 0) return 'Regular Sale';
        return ids.map((id) => this.conditionName(id)).join(' · ');
    }

    /** Letra del market center (participant id del SIP). */
    exchangeLetter(x?: number): string {
        if (x == null) return '·';
        return this.exchLetter.get(x) ?? String(x);
    }

    /** Nombre del market center; para exchange 4 detalla el TRF si viene. */
    exchangeName(x?: number, trfi?: number): string {
        if (x == null) return 'Unknown';
        if (x === 4 && trfi != null) {
            return TRF_NAMES[trfi] ?? 'FINRA TRF';
        }
        return this.exchName.get(x) ?? `Exchange ${x}`;
    }

    /** true ⇔ el print es off-exchange (dark pool / internalizador vía TRF). */
    isDarkPool(x?: number, trfi?: number): boolean {
        return x === 4 && trfi != null;
    }

    /**
     * true ⇔ el print NO actualiza el last consolidado (Average Price, Form T
     * fuera de horas, Odd Lot, Derivatively Priced...). Regla: cualquier
     * condición con NO gana.
     */
    doesNotUpdateLast(ids?: number[]): boolean {
        if (!ids || ids.length === 0) return false;
        return ids.some((id) => this.noUpdateLast.has(id));
    }

    /**
     * Variante para la UI del tape: qué prints atenuar. Excluye Form T (12),
     * Extended Hours Sold (13) y Odd Lot (37) — en after-hours TODOS los
     * prints son Form T y atenuar la cinta entera la deja ilegible; esos ya
     * van señalizados (hora en ámbar, letra I). Solo se atenúan los prints
     * genuinamente fuera de tape: Average Price, Derivatively Priced, Prior
     * Reference, Sold OOS, official open/close, etc.
     */
    isDimmedPrint(ids?: number[]): boolean {
        if (!ids || ids.length === 0) return false;
        return ids.some(
            (id) => this.noUpdateLast.has(id) && id !== 12 && id !== 13 && id !== ODD_LOT_CONDITION
        );
    }

    isExtendedHours(ids?: number[]): boolean {
        if (!ids) return false;
        return ids.some((id) => EXTENDED_HOURS_CONDITIONS.has(id));
    }

    isAuction(ids?: number[]): boolean {
        if (!ids) return false;
        return ids.some((id) => AUCTION_CONDITIONS.has(id));
    }

    isOfficialPrint(ids?: number[]): boolean {
        if (!ids) return false;
        return ids.some((id) => OFFICIAL_PRINT_CONDITIONS.has(id));
    }

    isOddLot(ids?: number[], size?: number): boolean {
        if (ids?.includes(ODD_LOT_CONDITION)) return true;
        return size != null && size > 0 && size < 100;
    }
}

// ============================================================================
// Carga (singleton por sesión)
// ============================================================================

const API_GATEWAY_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

let decoderPromise: Promise<TapeDecoder> | null = null;

/**
 * Devuelve el decoder compartido. El primer llamador dispara el fetch del
 * reference data; si falla, se sirve el fallback estático (y el siguiente
 * open de ventana reintenta).
 */
export function getTapeDecoder(): Promise<TapeDecoder> {
    if (!decoderPromise) {
        decoderPromise = fetch(`${API_GATEWAY_URL}/api/v1/tape/reference`)
            .then((r) => (r.ok ? r.json() : null))
            .then((data: TapeReferenceData | null) => new TapeDecoder(data))
            .catch(() => {
                decoderPromise = null; // permitir reintento en el próximo open
                return new TapeDecoder(null);
            });
    }
    return decoderPromise;
}
