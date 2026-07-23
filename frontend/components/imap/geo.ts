/**
 * Equirectangular projection + proximity clustering for IMAP.
 * Coordinate space matches Natural Earth coastline path: 1000 × 500 (−90°…90°).
 */

import type {
  ClusterStatus,
  ExchangeCoord,
  ImapRegion,
  ImapVenue,
  ProjectedPoint,
  VenueCluster,
} from './types';

export const MAP_WIDTH = 1000;
export const MAP_HEIGHT = 500;
export const LAT_TOP = 90;
export const LAT_BOTTOM = -90;
const LAT_RANGE = LAT_TOP - LAT_BOTTOM;

/** Static fallback coords for FMP all-exchange-market-hours codes. */
export const EXCHANGE_COORDS: Record<string, ExchangeCoord> = {
  NASDAQ: { lat: 40.7489, lng: -73.9680, city: 'New York', region: 'North America', country: 'US' },
  NYSE: { lat: 40.7069, lng: -74.0113, city: 'New York', region: 'North America', country: 'US' },
  AMEX: { lat: 40.7140, lng: -74.0060, city: 'New York', region: 'North America', country: 'US' },
  CBOE: { lat: 41.8781, lng: -87.6298, city: 'Chicago', region: 'North America', country: 'US' },
  CME: { lat: 41.8776, lng: -87.6369, city: 'Chicago', region: 'North America', country: 'US' },
  ICE: { lat: 64.1466, lng: -21.9426, city: 'Reykjavik', region: 'Europe', country: 'IS' },
  ICEF: { lat: 41.8781, lng: -87.6298, city: 'Chicago', region: 'North America', country: 'US' },
  OTC: { lat: 40.7580, lng: -73.9855, city: 'New York', region: 'North America', country: 'US' },
  PNK: { lat: 40.7589, lng: -73.9851, city: 'New York', region: 'North America', country: 'US' },
  NIM: { lat: 40.7128, lng: -74.0060, city: 'New York', region: 'North America', country: 'US' },
  ASE: { lat: 40.7069, lng: -74.0113, city: 'New York', region: 'North America', country: 'US' },
  TSX: { lat: 43.6481, lng: -79.3817, city: 'Toronto', region: 'North America', country: 'CA' },
  TSXV: { lat: 43.6487, lng: -79.3820, city: 'Toronto', region: 'North America', country: 'CA' },
  CNQ: { lat: 43.6532, lng: -79.3832, city: 'Toronto', region: 'North America', country: 'CA' },
  NEO: { lat: 43.6500, lng: -79.3800, city: 'Toronto', region: 'North America', country: 'CA' },
  AQS: { lat: 51.5074, lng: -0.1278, city: 'London', region: 'Europe', country: 'GB' },

  LSE: { lat: 51.5155, lng: -0.0922, city: 'London', region: 'Europe', country: 'GB' },
  IOB: { lat: 51.5150, lng: -0.0900, city: 'London', region: 'Europe', country: 'GB' },
  XETRA: { lat: 50.1109, lng: 8.6821, city: 'Frankfurt', region: 'Europe', country: 'DE' },
  FSX: { lat: 50.1155, lng: 8.6842, city: 'Frankfurt', region: 'Europe', country: 'DE' },
  BER: { lat: 52.5200, lng: 13.4050, city: 'Berlin', region: 'Europe', country: 'DE' },
  DUS: { lat: 51.2277, lng: 6.7735, city: 'Düsseldorf', region: 'Europe', country: 'DE' },
  HAM: { lat: 53.5511, lng: 9.9937, city: 'Hamburg', region: 'Europe', country: 'DE' },
  MUN: { lat: 48.1351, lng: 11.5820, city: 'Munich', region: 'Europe', country: 'DE' },
  STU: { lat: 48.7758, lng: 9.1829, city: 'Stuttgart', region: 'Europe', country: 'DE' },
  EURONEXT: { lat: 48.8698, lng: 2.3340, city: 'Paris', region: 'Europe', country: 'FR' },
  PAR: { lat: 48.8698, lng: 2.3340, city: 'Paris', region: 'Europe', country: 'FR' },
  AMS: { lat: 52.3740, lng: 4.8897, city: 'Amsterdam', region: 'Europe', country: 'NL' },
  BRU: { lat: 50.8503, lng: 4.3517, city: 'Brussels', region: 'Europe', country: 'BE' },
  LIS: { lat: 38.7223, lng: -9.1393, city: 'Lisbon', region: 'Europe', country: 'PT' },
  DUB: { lat: 53.3498, lng: -6.2603, city: 'Dublin', region: 'Europe', country: 'IE' },
  MIL: { lat: 45.4642, lng: 9.1900, city: 'Milan', region: 'Europe', country: 'IT' },
  BME: { lat: 40.4168, lng: -3.7038, city: 'Madrid', region: 'Europe', country: 'ES' },
  SIX: { lat: 47.3769, lng: 8.5417, city: 'Zurich', region: 'Europe', country: 'CH' },
  EBS: { lat: 47.3769, lng: 8.5417, city: 'Zurich', region: 'Europe', country: 'CH' },
  SSX: { lat: -33.8688, lng: 151.2093, city: 'Sydney', region: 'Asia Pacific', country: 'AU' },
  STO: { lat: 59.3293, lng: 18.0686, city: 'Stockholm', region: 'Europe', country: 'SE' },
  CPH: { lat: 55.6761, lng: 12.5683, city: 'Copenhagen', region: 'Europe', country: 'DK' },
  HEL: { lat: 60.1699, lng: 24.9384, city: 'Helsinki', region: 'Europe', country: 'FI' },
  OSL: { lat: 59.9139, lng: 10.7522, city: 'Oslo', region: 'Europe', country: 'NO' },
  WSE: { lat: 52.2297, lng: 21.0122, city: 'Warsaw', region: 'Europe', country: 'PL' },
  BUD: { lat: 47.4979, lng: 19.0402, city: 'Budapest', region: 'Europe', country: 'HU' },
  PRA: { lat: 50.0755, lng: 14.4378, city: 'Prague', region: 'Europe', country: 'CZ' },
  VIE: { lat: 48.2082, lng: 16.3738, city: 'Vienna', region: 'Europe', country: 'AT' },
  ATH: { lat: 37.9838, lng: 23.7275, city: 'Athens', region: 'Europe', country: 'GR' },
  BTS: { lat: 48.1486, lng: 17.1077, city: 'Bratislava', region: 'Europe', country: 'SK' },
  TAL: { lat: 59.4370, lng: 24.7536, city: 'Tallinn', region: 'Europe', country: 'EE' },
  RIS: { lat: 56.9496, lng: 24.1052, city: 'Riga', region: 'Europe', country: 'LV' },
  DXE: { lat: 50.1109, lng: 8.6821, city: 'Frankfurt', region: 'Europe', country: 'DE' },
  FGI: { lat: 51.5074, lng: -0.1278, city: 'London', region: 'Europe', country: 'GB' },

  JPX: { lat: 35.6812, lng: 139.7671, city: 'Tokyo', region: 'Asia Pacific', country: 'JP' },
  HKSE: { lat: 22.2855, lng: 114.1577, city: 'Hong Kong', region: 'Asia Pacific', country: 'HK' },
  SHH: { lat: 31.2304, lng: 121.4737, city: 'Shanghai', region: 'Asia Pacific', country: 'CN' },
  SHZ: { lat: 22.5431, lng: 114.0579, city: 'Shenzhen', region: 'Asia Pacific', country: 'CN' },
  ASX: { lat: -33.8688, lng: 151.2093, city: 'Sydney', region: 'Asia Pacific', country: 'AU' },
  NZE: { lat: -36.8485, lng: 174.7633, city: 'Auckland', region: 'Asia Pacific', country: 'NZ' },
  BSE: { lat: 18.9290, lng: 72.8334, city: 'Mumbai', region: 'Asia Pacific', country: 'IN' },
  NSE: { lat: 19.0760, lng: 72.8777, city: 'Mumbai', region: 'Asia Pacific', country: 'IN' },
  KSC: { lat: 37.5665, lng: 126.9780, city: 'Seoul', region: 'Asia Pacific', country: 'KR' },
  KOE: { lat: 37.5662, lng: 126.9778, city: 'Seoul', region: 'Asia Pacific', country: 'KR' },
  TAI: { lat: 25.0330, lng: 121.5654, city: 'Taipei', region: 'Asia Pacific', country: 'TW' },
  TWO: { lat: 25.0478, lng: 121.5319, city: 'Taipei', region: 'Asia Pacific', country: 'TW' },
  SET: { lat: 13.7563, lng: 100.5018, city: 'Bangkok', region: 'Asia Pacific', country: 'TH' },
  SES: { lat: 1.2797, lng: 103.8501, city: 'Singapore', region: 'Asia Pacific', country: 'SG' },
  KLS: { lat: 3.1390, lng: 101.6869, city: 'Kuala Lumpur', region: 'Asia Pacific', country: 'MY' },
  JKT: { lat: -6.2088, lng: 106.8456, city: 'Jakarta', region: 'Asia Pacific', country: 'ID' },
  HOSE: { lat: 10.8231, lng: 106.6297, city: 'Ho Chi Minh', region: 'Asia Pacific', country: 'VN' },
  MCX: { lat: 55.7558, lng: 37.6173, city: 'Moscow', region: 'Europe', country: 'RU' },

  SAO: { lat: -23.5505, lng: -46.6333, city: 'São Paulo', region: 'Latin America', country: 'BR' },
  BUE: { lat: -34.6037, lng: -58.3816, city: 'Buenos Aires', region: 'Latin America', country: 'AR' },
  MEX: { lat: 19.4326, lng: -99.1332, city: 'Mexico City', region: 'Latin America', country: 'MX' },
  SGO: { lat: -33.4489, lng: -70.6693, city: 'Santiago', region: 'Latin America', country: 'CL' },
  BVC: { lat: 4.7110, lng: -74.0721, city: 'Bogotá', region: 'Latin America', country: 'CO' },

  DFM: { lat: 25.2048, lng: 55.2708, city: 'Dubai', region: 'Middle East & Africa', country: 'AE' },
  DOH: { lat: 25.2854, lng: 51.5310, city: 'Doha', region: 'Middle East & Africa', country: 'QA' },
  SAU: { lat: 24.7136, lng: 46.6753, city: 'Riyadh', region: 'Middle East & Africa', country: 'SA' },
  KUW: { lat: 29.3759, lng: 47.9774, city: 'Kuwait City', region: 'Middle East & Africa', country: 'KW' },
  TLV: { lat: 32.0853, lng: 34.7818, city: 'Tel Aviv', region: 'Middle East & Africa', country: 'IL' },
  IST: { lat: 41.0082, lng: 28.9784, city: 'Istanbul', region: 'Europe', country: 'TR' },
  EGX: { lat: 30.0444, lng: 31.2357, city: 'Cairo', region: 'Middle East & Africa', country: 'EG' },
  JNB: { lat: -26.2041, lng: 28.0473, city: 'Johannesburg', region: 'Middle East & Africa', country: 'ZA' },
};

export function project(
  lat: number,
  lng: number,
  width: number = MAP_WIDTH,
  height: number = MAP_HEIGHT,
): ProjectedPoint {
  const x = ((lng + 180) / 360) * width;
  const y = ((LAT_TOP - lat) / LAT_RANGE) * height;
  return { x, y };
}

/** Enrich venue with fallback lat/lng/city/region/country when missing. */
export function enrichVenue(venue: ImapVenue): ImapVenue {
  const code = venue.exchange?.toUpperCase?.() ?? '';
  const fallback = EXCHANGE_COORDS[code];
  if (!fallback) {
    return {
      ...venue,
      lat: Number.isFinite(venue.lat) ? venue.lat : 0,
      lng: Number.isFinite(venue.lng) ? venue.lng : 0,
      city: venue.city || '',
      region: (venue.region as ImapRegion) || 'Other',
      country: venue.country || '',
      sessions: venue.sessions ?? [],
    };
  }
  const hasCoords =
    Number.isFinite(venue.lat) &&
    Number.isFinite(venue.lng) &&
    !(venue.lat === 0 && venue.lng === 0);
  return {
    ...venue,
    lat: hasCoords ? venue.lat : fallback.lat,
    lng: hasCoords ? venue.lng : fallback.lng,
    city: venue.city || fallback.city,
    region: (venue.region as ImapRegion) || fallback.region,
    country: venue.country || fallback.country,
    sessions: venue.sessions ?? [],
  };
}

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function clusterStatus(venues: ImapVenue[]): ClusterStatus {
  const open = venues.filter((v) => v.isMarketOpen).length;
  if (open === venues.length && open > 0) return 'open';
  if (open > 0) return 'partial';
  // no regular session live — amber if any venue is in pre/post market
  if (venues.some((v) => v.status === 'pre' || v.status === 'post')) return 'extended';
  return 'closed';
}

/**
 * Distance-based clustering. Venues within `radiusKm` of a cluster centroid
 * are merged. Default ~450 km keeps NY metro / London / Frankfurt distinct
 * while collapsing dense city stacks.
 */
export function clusterVenues(
  venues: ImapVenue[],
  width: number = MAP_WIDTH,
  height: number = MAP_HEIGHT,
  radiusKm: number = 450,
): VenueCluster[] {
  const clusters: VenueCluster[] = [];

  for (const venue of venues) {
    if (!Number.isFinite(venue.lat) || !Number.isFinite(venue.lng)) continue;

    let best: VenueCluster | null = null;
    let bestDist = Infinity;

    for (const c of clusters) {
      const d = haversineKm(venue.lat, venue.lng, c.lat, c.lng);
      if (d < radiusKm && d < bestDist) {
        best = c;
        bestDist = d;
      }
    }

    if (best) {
      best.venues.push(venue);
      const n = best.venues.length;
      best.lat = best.venues.reduce((s, v) => s + v.lat, 0) / n;
      best.lng = best.venues.reduce((s, v) => s + v.lng, 0) / n;
    } else {
      clusters.push({
        id: `c-${venue.exchange}-${clusters.length}`,
        lat: venue.lat,
        lng: venue.lng,
        x: 0,
        y: 0,
        venues: [venue],
        openCount: 0,
        breakCount: 0,
        status: 'closed',
      });
    }
  }

  for (const c of clusters) {
    const { x, y } = project(c.lat, c.lng, width, height);
    c.x = x;
    c.y = y;
    c.openCount = c.venues.filter((v) => v.isMarketOpen).length;
    c.breakCount = 0;
    c.status = clusterStatus(c.venues);
    c.id = `c-${c.lat.toFixed(2)}_${c.lng.toFixed(2)}_${c.venues.length}`;
  }

  return clusters;
}

export function formatLocalTime(timezone: string, now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: timezone || 'UTC',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(now);
  } catch {
    return '--:--';
  }
}

/** Minutes from local midnight in the venue timezone. */
export function localMinutesNow(timezone: string, now: Date = new Date()): number {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone || 'UTC',
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
    }).formatToParts(now);
    const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? 0) % 24;
    const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? 0);
    return hour * 60 + minute;
  } catch {
    return 0;
  }
}

export function minutesToLabel(min: number): string {
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
}

// ============================================================================
// Solar day/night terminator + responsive viewBox  (GREYLINE redesign)
// ============================================================================

export interface SolarPosition {
  /** solar declination in radians */
  decl: number;
  /** subsolar longitude in degrees */
  subsolarLng: number;
}

/** Solar declination + subsolar longitude for the given instant (UTC-based). */
export function solarPosition(date: Date = new Date()): SolarPosition {
  const start = Date.UTC(date.getUTCFullYear(), 0, 0);
  const dayOfYear = Math.floor((date.getTime() - start) / 86_400_000);
  const g =
    ((2 * Math.PI) / 365.24) * (dayOfYear - 1 + (date.getUTCHours() - 12) / 24);
  // equation of time (minutes) — NOAA/Spencer approximation
  const eqTime =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(g) -
      0.032077 * Math.sin(g) -
      0.014615 * Math.cos(2 * g) -
      0.040849 * Math.sin(2 * g));
  const decl =
    0.006918 -
    0.399912 * Math.cos(g) +
    0.070257 * Math.sin(g) -
    0.006758 * Math.cos(2 * g) +
    0.000907 * Math.sin(2 * g) -
    0.002697 * Math.cos(3 * g) +
    0.00148 * Math.sin(3 * g);
  const utcMin =
    date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
  const subsolarLng = -(utcMin + eqTime - 720) / 4;
  return { decl, subsolarLng };
}

export interface TerminatorPaths {
  /** SVG points for the night polygon (fills the dark hemisphere incl. polar cap) */
  nightPoints: string;
  /** SVG points for the terminator curve itself (the warm "grey line") */
  curvePoints: string;
  /** projected subsolar point */
  subsolar: ProjectedPoint;
  decl: number;
  subsolarLng: number;
}

/**
 * Day/night terminator in map coordinates. Fills the night hemisphere; the
 * winter pole (opposite the sun) is entirely dark, handled by closing the
 * polygon along that pole's edge (the classic polar-cap bug).
 */
export function terminatorPaths(
  date: Date = new Date(),
  width: number = MAP_WIDTH,
  height: number = MAP_HEIGHT,
): TerminatorPaths {
  const { decl, subsolarLng } = solarPosition(date);
  const tanDecl = Math.tan(decl);
  const curve: ProjectedPoint[] = [];
  for (let lng = -180; lng <= 180; lng += 1.5) {
    const H = ((lng - subsolarLng) * Math.PI) / 180;
    const latTerm = (Math.atan(-Math.cos(H) / tanDecl) * 180) / Math.PI;
    curve.push(project(latTerm, lng, width, height));
  }
  const closeY =
    decl > 0 ? project(-90, 0, width, height).y : project(90, 0, width, height).y;
  const night: ProjectedPoint[] = curve.concat([
    { x: width, y: closeY },
    { x: 0, y: closeY },
  ]);
  const fmt = (arr: ProjectedPoint[]) =>
    arr.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  return {
    nightPoints: fmt(night),
    curvePoints: fmt(curve),
    subsolar: project((decl * 180) / Math.PI, subsolarLng, width, height),
    decl,
    subsolarLng,
  };
}

// ============================================================================
// OPEN NOW band — longitude range of currently-open venues
// ============================================================================

export interface OpenBand {
  /** horizontal band segments in map coords (two when wrapping the antimeridian) */
  segments: Array<{ x0: number; x1: number }>;
  /** west & east edge lines */
  edges: [number, number];
}

/**
 * Band spanning the projected X range of open venues, padded `pad` units.
 * If the open venues wrap around the antimeridian, the band is split at the
 * LARGEST empty gap into two edge-wrapping segments. A single open venue
 * collapses the band to 10 units centred on it.
 */
export function computeOpenBand(
  xs: number[],
  width: number = MAP_WIDTH,
  pad = 5,
): OpenBand | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  if (s.length === 1) {
    const x = s[0];
    return { segments: [{ x0: x - pad, x1: x + pad }], edges: [x - pad, x + pad] };
  }
  // largest circular gap between consecutive open venues
  let gapIdx = 0;
  let gapSize = -Infinity;
  for (let i = 0; i < s.length; i++) {
    const next = i === s.length - 1 ? s[0] + width : s[i + 1];
    const g = next - s[i];
    if (g > gapSize) {
      gapSize = g;
      gapIdx = i;
    }
  }
  const west = s[(gapIdx + 1) % s.length] - pad; // band starts after the gap
  const east = s[gapIdx] + pad; // band ends before the gap
  if (gapIdx === s.length - 1) {
    // the empty gap is the wrap itself → contiguous band
    return { segments: [{ x0: west, x1: east }], edges: [west, east] };
  }
  // band wraps the antimeridian → two segments meeting at the map edges
  return {
    segments: [
      { x0: Math.max(0, west), x1: width },
      { x0: 0, x1: Math.min(width, east) },
    ],
    edges: [west, east],
  };
}

export interface ViewBoxRect {
  minX: number;
  minY: number;
  w: number;
  h: number;
}

/**
 * Responsive viewBox that ALWAYS matches the container's aspect ratio — so the
 * equirectangular map never distorts and never letterboxes — vertically framed
 * on the venue band. Replaces the old preserveAspectRatio="none" stretch (and
 * makes the marker counter-scaling hack unnecessary).
 */
export function computeViewBox(
  containerW: number,
  containerH: number,
  topLat = 66,
  botLat = -54,
): ViewBoxRect {
  const w = MAP_WIDTH;
  const h = containerW > 0 ? (w * containerH) / containerW : MAP_HEIGHT;
  const bandTop = project(topLat, 0).y;
  const bandBot = project(botLat, 0).y;
  const mid = (bandTop + bandBot) / 2;
  const minY =
    h >= MAP_HEIGHT
      ? (MAP_HEIGHT - h) / 2
      : Math.max(0, Math.min(MAP_HEIGHT - h, mid - h / 2));
  return { minX: 0, minY, w, h };
}
