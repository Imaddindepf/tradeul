/** IMAP — World Venue Map types */

export type SessionType = 'regular' | 'break' | 'lunch' | 'pre' | 'post';

export type ImapRegion =
  | 'North America'
  | 'Europe'
  | 'Asia Pacific'
  | 'Latin America'
  | 'Middle East & Africa'
  | 'Other';

export interface SessionSegment {
  /** Minutes from local midnight [0, 1440] */
  startMin: number;
  endMin: number;
  type: SessionType;
}

export type VenueStatus = 'open' | 'closed' | 'break' | 'pre' | 'post';

export interface ImapVenue {
  exchange: string;
  /** ISO 10383 Market Identifier Code (display standard) */
  mic?: string;
  /** Derived live status from the API (includes pre/post market phases) */
  status?: VenueStatus;
  name: string;
  timezone: string;
  isMarketOpen: boolean;
  openingHour?: string;
  closingHour?: string;
  openingAdditional?: string | null;
  closingAdditional?: string | null;
  lat: number;
  lng: number;
  city: string;
  region: ImapRegion | string;
  country: string;
  sessions: SessionSegment[];
}

export interface ExchangeCoord {
  lat: number;
  lng: number;
  city: string;
  region: ImapRegion;
  country: string;
}

export interface ProjectedPoint {
  x: number;
  y: number;
}

export type ClusterStatus = 'open' | 'closed' | 'partial' | 'extended';

export interface VenueCluster {
  id: string;
  lat: number;
  lng: number;
  x: number;
  y: number;
  venues: ImapVenue[];
  openCount: number;
  breakCount: number;
  status: ClusterStatus;
}

export interface ImapWindowState {
  filter: string;
  selectedExchange: string | null;
  selectedClusterId: string | null;
  groupBy: 'region' | 'status';
  sidebarCollapsed: boolean;
  [key: string]: unknown;
}

export interface ImapExchangesResponse {
  venues?: ImapVenue[];
  exchanges?: ImapVenue[];
  total?: number;
  open?: number;
  closed?: number;
  break?: number;
  updated_at?: string;
  updatedAt?: string;
}
