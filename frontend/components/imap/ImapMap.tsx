'use client';

/**
 * Interactive equirectangular venue map.
 *
 * GREYLINE redesign:
 *  - Responsive viewBox (aspect == container) → geography never distorts;
 *    the old preserveAspectRatio="none" stretch and the markerYScale hack are gone.
 *  - Smooth zoom/pan: rAF-interpolated view (translate+scale) with inertial glide
 *    and zoom-to-cursor.
 *  - Screen-constant markers (Godel-style chips) rendered as a viewBox-space overlay.
 *  - Live day/night terminator (solar) — the one earned tonal field.
 * The onSelectCluster(cluster) / onClearSelection contract matches ImapContent; the sidebar
 * and cluster panel keep working untouched.
 */

import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { Minus, Plus, LocateFixed } from 'lucide-react';
import { cn } from '@/lib/utils';
import { WorldMapSvg } from './WorldMapSvg';
import { ImapClusterPanel } from './ImapClusterPanel';
import {
  clusterVenues,
  computeOpenBand,
  computeViewBox,
  MAP_HEIGHT,
  MAP_WIDTH,
  project,
  terminatorPaths,
} from './geo';
import type { ClusterStatus, ImapVenue, VenueCluster } from './types';

interface ImapMapProps {
  venues: ImapVenue[];
  selectedClusterId: string | null;
  selectedExchange: string | null;
  onSelectCluster: (cluster: VenueCluster) => void;
  onClearSelection: () => void;
  className?: string;
}

interface ViewState {
  scale: number;
  tx: number;
  ty: number;
}

const MIN_SCALE = 1;
const MAX_SCALE = 8;
const HOME: ViewState = { scale: 1, tx: 0, ty: 0 };

/** Reference palette: light clean green / soft amber / cool neutral grey. */
function statusFill(status: ClusterStatus): string {
  if (status === 'open') return '#34d399';
  if (status === 'partial' || status === 'extended') return '#fbbf24';
  return '#8b93a1';
}

/** Godel-scale chip: single venue ~9px radius, clusters grow to ~15px. */
function clusterPx(count: number): number {
  return Math.min(15, Math.max(9, 7 + Math.sqrt(count) * 2.1));
}

function clampScale(s: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
}

function ImapMapInner({
  venues,
  selectedClusterId,
  selectedExchange,
  onSelectCluster,
  onClearSelection,
  className,
}: ImapMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ width: 800, height: 460 });
  const [view, setView] = useState<ViewState>(HOME);
  const [now, setNow] = useState<Date>(() => new Date());
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [isPanning, setIsPanning] = useState(false);

  const viewRef = useRef(view);
  const targetRef = useRef(view);
  const rafRef = useRef<number | null>(null);
  const hoveredRef = useRef<string | null>(null);
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number; moved: boolean } | null>(null);
  const velRef = useRef({ x: 0, y: 0 });
  const didPanRef = useRef(false);

  // ---- responsive viewBox (no distortion) ----------------------------------
  const viewBox = useMemo(
    () => computeViewBox(viewport.width, viewport.height),
    [viewport],
  );
  const unit = viewport.width > 0 ? viewBox.w / viewport.width : 1; // viewBox units / screen px
  const viewBoxRef = useRef(viewBox);
  viewBoxRef.current = viewBox;
  const unitRef = useRef(unit);
  unitRef.current = unit;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) setViewport({ width: r.width, height: r.height });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ---- live terminator tick ------------------------------------------------
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);
  const terminator = useMemo(() => terminatorPaths(now), [now]);

  // ---- clustering (re-merge by screen distance per zoom bucket) -------------
  const zoomBucket = Math.round(Math.log2(view.scale) * 4) / 4;
  const clusterRadiusKm = useMemo(
    () => Math.max(90, Math.min(1400, 520 / Math.pow(2, zoomBucket))),
    [zoomBucket],
  );
  const clusters = useMemo(
    () =>
      clusterVenues(
        // drop venues with missing / (0,0) coords so no stray marker lands in the ocean
        venues.filter(
          (v) => Number.isFinite(v.lat) && Number.isFinite(v.lng) && !(v.lat === 0 && v.lng === 0),
        ),
        MAP_WIDTH,
        MAP_HEIGHT,
        clusterRadiusKm,
      ),
    [venues, clusterRadiusKm],
  );

  // OPEN NOW band — longitude range of venues currently in session
  const openBand = useMemo(
    () =>
      computeOpenBand(
        venues
          .filter(
            (v) =>
              v.isMarketOpen &&
              Number.isFinite(v.lat) &&
              Number.isFinite(v.lng) &&
              !(v.lat === 0 && v.lng === 0),
          )
          .map((v) => project(v.lat, v.lng).x),
      ),
    [venues],
  );

  const activeCluster = useMemo(() => {
    if (selectedClusterId) {
      const byId = clusters.find((c) => c.id === selectedClusterId);
      if (byId) return byId;
    }
    if (selectedExchange) {
      return clusters.find((c) => c.venues.some((v) => v.exchange === selectedExchange)) ?? null;
    }
    return null;
  }, [clusters, selectedClusterId, selectedExchange]);
  const activeId = activeCluster?.id ?? null;

  // ---- rAF view interpolation ----------------------------------------------
  const step = useCallback(() => {
    const t = targetRef.current;
    const c = viewRef.current;
    const e = 0.24;
    const nc: ViewState = {
      scale: c.scale + (t.scale - c.scale) * e,
      tx: c.tx + (t.tx - c.tx) * e,
      ty: c.ty + (t.ty - c.ty) * e,
    };
    const done =
      Math.abs(t.scale - nc.scale) < 0.001 &&
      Math.abs(t.tx - nc.tx) < 0.12 &&
      Math.abs(t.ty - nc.ty) < 0.12;
    const next = done ? t : nc;
    viewRef.current = next;
    setView(next);
    rafRef.current = done ? null : requestAnimationFrame(step);
  }, []);
  const kick = useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(step);
  }, [step]);
  useEffect(() => () => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
  }, []);

  const applyImmediate = useCallback((v: ViewState) => {
    viewRef.current = v;
    targetRef.current = v;
    setView(v);
  }, []);

  const clientToMap = useCallback((clientX: number, clientY: number) => {
    const el = containerRef.current;
    const vb = viewBoxRef.current;
    if (!el) return { x: MAP_WIDTH / 2, y: MAP_HEIGHT / 2 };
    const r = el.getBoundingClientRect();
    return {
      x: vb.minX + ((clientX - r.left) / r.width) * vb.w,
      y: vb.minY + ((clientY - r.top) / r.height) * vb.h,
    };
  }, []);

  const zoomToward = useCallback((cx: number, cy: number, ns: number) => {
    const t = targetRef.current;
    const k = ns / t.scale;
    targetRef.current = { scale: ns, tx: cx - (cx - t.tx) * k, ty: cy - (cy - t.ty) * k };
    kick();
  }, [kick]);

  // non-passive wheel so preventDefault stops page scroll
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const m = clientToMap(e.clientX, e.clientY);
      const f = e.deltaY < 0 ? 1.3 : 1 / 1.3;
      zoomToward(m.x, m.y, clampScale(targetRef.current.scale * f));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [clientToMap, zoomToward]);

  // ---- fly-to the venue selected from the sidebar --------------------------
  useEffect(() => {
    if (!selectedExchange) return;
    const v = venues.find((x) => x.exchange === selectedExchange);
    if (!v || !Number.isFinite(v.lat) || !Number.isFinite(v.lng)) return;
    const p = project(v.lat, v.lng);
    const vb = viewBoxRef.current;
    const ns = Math.max(viewRef.current.scale, 2.6);
    targetRef.current = {
      scale: ns,
      tx: vb.minX + vb.w / 2 - p.x * ns,
      ty: vb.minY + vb.h / 2 - p.y * ns,
    };
    kick();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExchange]);

  // ---- marker screen geometry + hit testing --------------------------------
  const markerScreen = useCallback((c: VenueCluster) => {
    const el = containerRef.current;
    const vb = viewBoxRef.current;
    const v = viewRef.current;
    const vbx = c.x * v.scale + v.tx;
    const vby = c.y * v.scale + v.ty;
    if (!el) return { x: 0, y: 0 };
    const r = el.getBoundingClientRect();
    return { x: ((vbx - vb.minX) / vb.w) * r.width, y: ((vby - vb.minY) / vb.h) * r.height };
  }, []);

  const nearest = useCallback((mx: number, my: number): VenueCluster | null => {
    let best: VenueCluster | null = null;
    let bd = Infinity;
    for (const c of clusters) {
      const p = markerScreen(c);
      const d = Math.hypot(p.x - mx, p.y - my);
      const rad = clusterPx(c.venues.length) + 7;
      if (d < rad && d < bd) {
        best = c;
        bd = d;
      }
    }
    return best;
  }, [clusters, markerScreen]);

  // ---- pointer interaction --------------------------------------------------
  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    didPanRef.current = false;
    const v = viewRef.current;
    dragRef.current = { x: e.clientX, y: e.clientY, tx: v.tx, ty: v.ty, moved: false };
    velRef.current = { x: 0, y: 0 };
  }, []);

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const el = containerRef.current;
    if (!el) return;
    const d = dragRef.current;
    if (d) {
      const r = el.getBoundingClientRect();
      const vb = viewBoxRef.current;
      const dx = ((e.clientX - d.x) / r.width) * vb.w;
      const dy = ((e.clientY - d.y) / r.height) * vb.h;
      if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) {
        d.moved = true;
        didPanRef.current = true;
        if (!isPanning) setIsPanning(true);
      }
      const v = viewRef.current;
      const ntx = d.tx + dx;
      const nty = d.ty + dy;
      velRef.current = { x: ntx - v.tx, y: nty - v.ty };
      applyImmediate({ scale: v.scale, tx: ntx, ty: nty });
      return;
    }
    // hover hit-test
    const r = el.getBoundingClientRect();
    const hit = nearest(e.clientX - r.left, e.clientY - r.top);
    const id = hit?.id ?? null;
    if (id !== hoveredRef.current) {
      hoveredRef.current = id;
      setHoveredId(id);
    }
  }, [applyImmediate, nearest, isPanning]);

  const endPointer = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    dragRef.current = null;
    setIsPanning(false);
    if (d && d.moved) {
      const vel = velRef.current;
      if (Math.abs(vel.x) + Math.abs(vel.y) > 0.4) {
        const v = { ...vel };
        const glide = () => {
          v.x *= 0.9;
          v.y *= 0.9;
          const c = viewRef.current;
          applyImmediate({ scale: c.scale, tx: c.tx + v.x, ty: c.ty + v.y });
          if (Math.abs(v.x) + Math.abs(v.y) > 0.05) requestAnimationFrame(glide);
        };
        requestAnimationFrame(glide);
      }
    }
  }, [applyImmediate]);

  const handleClusterClick = useCallback((cluster: VenueCluster) => {
    if (didPanRef.current) {
      didPanRef.current = false;
      return;
    }
    onSelectCluster(cluster);
  }, [onSelectCluster]);

  // ---- controls -------------------------------------------------------------
  const zoomButton = useCallback((factor: number) => {
    const vb = viewBoxRef.current;
    zoomToward(vb.minX + vb.w / 2, vb.minY + vb.h / 2, clampScale(targetRef.current.scale * factor));
  }, [zoomToward]);
  const resetView = useCallback(() => {
    targetRef.current = { ...HOME };
    kick();
  }, [kick]);

  // ---- render ---------------------------------------------------------------
  const sceneTransform = `translate(${view.tx} ${view.ty}) scale(${view.scale})`;

  // Godel-style detail popup: the hovered cluster, or the selected one.
  const panelCluster =
    (hoveredId ? clusters.find((c) => c.id === hoveredId) : null) ?? activeCluster ?? null;
  const panelAnchor = panelCluster
    ? {
        x: ((panelCluster.x * view.scale + view.tx - viewBox.minX) / viewBox.w) * viewport.width,
        y: ((panelCluster.y * view.scale + view.ty - viewBox.minY) / viewBox.h) * viewport.height,
      }
    : null;

  return (
    <div
      ref={containerRef}
      className={cn(
        'relative h-full w-full overflow-hidden bg-background',
        isPanning ? 'cursor-grabbing' : 'cursor-grab',
        className,
      )}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPointer}
      onPointerCancel={endPointer}
      onPointerLeave={() => {
        if (hoveredRef.current) {
          hoveredRef.current = null;
          setHoveredId(null);
        }
      }}
      onClick={() => {
        if (didPanRef.current) {
          didPanRef.current = false;
          return;
        }
        onClearSelection();
      }}
      onDoubleClick={(e) => {
        const m = clientToMap(e.clientX, e.clientY);
        zoomToward(m.x, m.y, clampScale(targetRef.current.scale * 1.7));
      }}
    >
      <style>{`
        @keyframes imap-ping{0%{transform:scale(1);opacity:.4}70%,100%{transform:scale(2);opacity:0}}
        .imap-ping{animation:imap-ping 2.6s cubic-bezier(0.215,0.61,0.355,1) infinite;transform-box:fill-box;transform-origin:center}
        @media (prefers-reduced-motion:reduce){.imap-ping{animation:none;opacity:0}}
      `}</style>

      <WorldMapSvg
        className="absolute inset-0"
        viewBox={viewBox}
        sceneTransform={sceneTransform}
        terminator={terminator}
        openBand={openBand}
      >
        {clusters.map((cluster) => {
          const px = clusterPx(cluster.venues.length);
          const fill = statusFill(cluster.status);
          const selected = cluster.id === activeId;
          const hovered = cluster.id === hoveredId;
          // Godel-style: the chip grows on hover/selection (smooth).
          const r = px * unit * (hovered || selected ? 1.2 : 1);
          const vbx = cluster.x * view.scale + view.tx;
          const vby = cluster.y * view.scale + view.ty;
          const label = String(cluster.venues.length);
          // number scales with the chip so text and disc always read as one unit
          const fontSize = Math.max(6, px * 0.72) * unit;

          return (
            <g
              key={cluster.id}
              transform={`translate(${vbx.toFixed(2)} ${vby.toFixed(2)})`}
              className="cursor-pointer"
              style={{ pointerEvents: isPanning ? 'none' : 'auto' }}
              role="button"
              tabIndex={0}
              aria-label={`${cluster.venues.length} venues, ${cluster.openCount} open`}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                handleClusterClick(cluster);
              }}
              onKeyDown={(e: KeyboardEvent<SVGGElement>) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelectCluster(cluster);
                }
              }}
            >
              {/* halo — a crisp translucent disc, plus a clean expanding ping when open */}
              {cluster.status !== 'closed' && (
                <circle
                  r={r * 1.5}
                  fill={fill}
                  fillOpacity={0.12}
                  pointerEvents="none"
                />
              )}
              {cluster.status === 'open' && (
                <circle
                  className="imap-ping"
                  r={r}
                  fill="none"
                  stroke={fill}
                  strokeWidth={1.2 * unit}
                  pointerEvents="none"
                />
              )}

              {selected && (
                <circle
                  r={r + 2.4 * unit}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={0.9}
                  strokeWidth={0.9 * unit}
                  className="text-foreground"
                  pointerEvents="none"
                />
              )}

              {/* chip — clean solid disc with a thin light border */}
              <circle
                r={r}
                fill={fill}
                fillOpacity={
                  cluster.status === 'closed' ? (selected || hovered ? 0.85 : 0.55) : 1
                }
                stroke="var(--color-foreground)"
                strokeOpacity={selected || hovered ? 0.9 : 0.5}
                strokeWidth={1 * unit}
                style={{ transition: 'r 130ms ease-out' }}
              />

              {/* partial: open-share arc */}
              {cluster.status === 'partial' &&
                cluster.venues.length > 1 &&
                (() => {
                  const frac = cluster.openCount / cluster.venues.length;
                  const a0 = -Math.PI / 2;
                  const a1 = a0 + frac * 2 * Math.PI;
                  const rr = r + 1.7 * unit;
                  const x0 = rr * Math.cos(a0);
                  const y0 = rr * Math.sin(a0);
                  const x1 = rr * Math.cos(a1);
                  const y1 = rr * Math.sin(a1);
                  const large = frac > 0.5 ? 1 : 0;
                  return (
                    <path
                      d={`M${x0.toFixed(2)} ${y0.toFixed(2)}A${rr.toFixed(2)} ${rr.toFixed(2)} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`}
                      fill="none"
                      stroke="#34d399"
                      strokeWidth={1.2 * unit}
                      strokeLinecap="round"
                      pointerEvents="none"
                    />
                  );
                })()}

              {/* centered count (clusters) */}
              {cluster.venues.length > 1 && (
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#fff"
                  fontSize={fontSize}
                  fontWeight={600}
                  letterSpacing="-0.03em"
                  className="pointer-events-none select-none"
                >
                  {label}
                </text>
              )}

              {(hovered || selected) && (
                <title>
                  {cluster.venues.length === 1
                    ? `${cluster.venues[0].exchange} — ${cluster.venues[0].name}`
                    : `${cluster.venues.length} venues · ${cluster.openCount} open`}
                </title>
              )}
            </g>
          );
        })}
      </WorldMapSvg>

      {panelCluster && panelAnchor && (
        <ImapClusterPanel
          cluster={panelCluster}
          now={now}
          anchor={panelAnchor}
          containerWidth={viewport.width}
          containerHeight={viewport.height}
        />
      )}

      {/* zoom chrome */}
      <div
        className="absolute bottom-2.5 right-2.5 z-10 flex flex-col overflow-hidden rounded border border-border bg-surface/95 shadow-sm backdrop-blur-sm"
        onPointerDown={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() => zoomButton(1.5)}
          className="flex h-7 w-7 items-center justify-center text-muted-fg hover:bg-surface-hover hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
          aria-label="Zoom in"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
        <div className="h-px bg-border" />
        <button
          type="button"
          onClick={() => zoomButton(1 / 1.5)}
          className="flex h-7 w-7 items-center justify-center text-muted-fg hover:bg-surface-hover hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
          aria-label="Zoom out"
        >
          <Minus className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
        <div className="h-px bg-border" />
        <button
          type="button"
          onClick={resetView}
          className="flex h-7 w-7 items-center justify-center text-muted-fg hover:bg-surface-hover hover:text-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-primary/40"
          aria-label="Reset map"
        >
          <LocateFixed className="h-3 w-3" strokeWidth={1.75} />
        </button>
      </div>

      <div className="pointer-events-none absolute bottom-2.5 left-2.5 text-[9px] tabular-nums text-muted-fg/50">
        {view.scale.toFixed(1)}×
      </div>
    </div>
  );
}

export const ImapMap = memo(ImapMapInner);
export default ImapMap;
