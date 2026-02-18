import { INTERVAL_SECONDS, type Interval } from './constants';

export function formatVolume(vol: number): string {
    if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(2)}B`;
    if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(2)}M`;
    if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
    return vol.toString();
}

export function formatPrice(price: number): string {
    if (price >= 1000) return price.toFixed(0);
    if (price >= 100) return price.toFixed(1);
    if (price >= 1) return price.toFixed(2);
    return price.toFixed(4);
}

export function roundToInterval(timestamp: number, interval: Interval): number {
    const seconds = INTERVAL_SECONDS[interval];
    return Math.floor(timestamp / seconds) * seconds;
}
