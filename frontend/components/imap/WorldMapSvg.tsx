'use client';

import { memo, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { MAP_HEIGHT, type OpenBand, type TerminatorPaths, type ViewBoxRect } from './geo';
import { WORLD_BORDERS_PATH, WORLD_COAST_PATH } from './worldLandPath';

const BAND_COLOR = '#3E8B66';

interface WorldMapSvgProps {
  /** Responsive viewBox (aspect matches the container → no distortion). */
  viewBox: ViewBoxRect;
  /** translate()+scale() applied to the geographic scene (zoom/pan). */
  sceneTransform: string;
  terminator?: TerminatorPaths | null;
  showTerminator?: boolean;
  /** OPEN NOW band — longitude range of currently-open venues. */
  openBand?: OpenBand | null;
  className?: string;
  /** Marker overlay — rendered in viewBox space, OUTSIDE the scene transform. */
  children?: ReactNode;
}

function WorldMapSvgInner({
  viewBox,
  sceneTransform,
  terminator,
  showTerminator = true,
  openBand,
  className,
  children,
}: WorldMapSvgProps) {
  const vb = `${viewBox.minX} ${viewBox.minY} ${viewBox.w} ${viewBox.h}`;
  const showNight = showTerminator && !!terminator;

  return (
    <svg
      viewBox={vb}
      preserveAspectRatio="xMidYMid meet"
      className={cn('h-full w-full touch-none', className)}
      role="img"
      aria-label="World venue map"
    >
      <g transform={sceneTransform}>
        {/* black & white wireframe — coastlines bright, interior borders faint */}
        <path
          d={WORLD_COAST_PATH}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.55}
          strokeWidth={0.6}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          className="text-foreground"
        />
        <path
          d={WORLD_BORDERS_PATH}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.2}
          strokeWidth={0.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          className="text-foreground"
        />

        {/* live day/night: the night side is veiled with the page background color,
            so lines dim at night and the ocean never shows a tint of its own */}
        {showNight && (
          <polygon
            points={terminator!.nightPoints}
            fill="var(--color-background)"
            fillOpacity={0.55}
            pointerEvents="none"
          />
        )}

        {/* OPEN NOW band — soft Godel-style column over open-session longitudes */}
        {openBand && (
          <g pointerEvents="none">
            <defs>
              <linearGradient id="imap-open-band" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={BAND_COLOR} stopOpacity="0" />
                <stop offset="12%" stopColor={BAND_COLOR} stopOpacity="0.07" />
                <stop offset="50%" stopColor={BAND_COLOR} stopOpacity="0.12" />
                <stop offset="88%" stopColor={BAND_COLOR} stopOpacity="0.07" />
                <stop offset="100%" stopColor={BAND_COLOR} stopOpacity="0" />
              </linearGradient>
            </defs>
            {openBand.segments.map((s, i) => (
              <rect
                key={i}
                x={s.x0}
                y={0}
                width={Math.max(0, s.x1 - s.x0)}
                height={MAP_HEIGHT}
                fill="url(#imap-open-band)"
              />
            ))}
            {openBand.edges.map((x, i) => (
              <line
                key={`e-${i}`}
                x1={x}
                y1={0}
                x2={x}
                y2={MAP_HEIGHT}
                stroke={BAND_COLOR}
                strokeOpacity={0.28}
                strokeWidth={0.8}
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </g>
        )}
      </g>

      {children}
    </svg>
  );
}

export const WorldMapSvg = memo(WorldMapSvgInner);
export default WorldMapSvg;
