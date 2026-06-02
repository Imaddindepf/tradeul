/**
 * Drawings sync bus — cross-instance pub/sub for chart drawings.
 *
 * Every `useChartDrawings(...)` instance publishes its mutations here. Other
 * instances that share the same scope listen and reload from localStorage so
 * the on-screen state stays in lockstep.
 *
 * Scopes — controlled by `DrawingsSyncMode` and matched at subscriber side:
 *   • `off`       — instance does not publish nor subscribe (legacy behaviour).
 *   • `in_layout` — only siblings in the *same window* with the *same ticker*
 *                   are kept in sync (great for multi-chart of the same
 *                   symbol at different intervals).
 *   • `global`    — every chart instance with the same ticker, anywhere in
 *                   the workspace, stays in sync.
 *
 * Each event carries a `sourceInstanceId` so the emitter can ignore its own
 * echo and avoid infinite loops. The bus is a tiny singleton (one Subject)
 * because there's no benefit to per-window buses here: ticker is the natural
 * scope and we filter on emission.
 */

import { Subject } from 'rxjs';

export type DrawingsSyncMode = 'off' | 'in_layout' | 'global';

export interface DrawingsChangeEvent {
    /** Stable id of the emitting `useChartDrawings` instance. */
    sourceInstanceId: string;
    /** Ticker the drawings belong to. */
    ticker: string;
    /** Window the emitter lives in (may be null for non-window contexts). */
    windowId: string | null;
    /** Sync mode the emitter was using when this event was published. */
    mode: DrawingsSyncMode;
}

const drawings$ = new Subject<DrawingsChangeEvent>();

export const drawingsBus = {
    emit: (event: DrawingsChangeEvent) => drawings$.next(event),
    /**
     * Returns the underlying observable. Consumers should filter by ticker
     * and (when scope is `in_layout`) by windowId before reacting.
     */
    stream$: drawings$.asObservable(),
};

/**
 * Match a published event against a subscriber's identity + sync preference.
 * Returns true when the subscriber should reload its state in response.
 *
 *   • Subscriber's mode is `off` → never reload (unless its own echo, which
 *     we always ignore via sourceInstanceId).
 *   • Subscriber's mode is `in_layout` → only react when the emitter shares
 *     the same `windowId` AND the same ticker.
 *   • Subscriber's mode is `global` → react when the emitter shares the
 *     same ticker (ignoring windowId).
 *
 * Cross-mode case: if subscriber is `global` and emitter was `in_layout`,
 * we still react (the emitter intended layout-scoped sync but we want full
 * sync globally). Symmetric: subscriber `in_layout` ignores `global`
 * emissions from other windows. The matrix matches the *subscriber*'s
 * preference, not the emitter's.
 */
export function shouldReactToDrawingsEvent(
    event: DrawingsChangeEvent,
    subscriber: {
        instanceId: string;
        ticker: string;
        windowId: string | null;
        mode: DrawingsSyncMode;
    },
): boolean {
    if (event.sourceInstanceId === subscriber.instanceId) return false;
    if (event.ticker !== subscriber.ticker) return false;
    switch (subscriber.mode) {
        case 'off':
            return false;
        case 'in_layout':
            return event.windowId != null && event.windowId === subscriber.windowId;
        case 'global':
            return true;
        default:
            return false;
    }
}
