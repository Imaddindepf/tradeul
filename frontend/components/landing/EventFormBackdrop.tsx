'use client';

// Centros dentro de viewBox: x en [44, 76] (rect 80px ancho), y en [30, 470] (rect 52px alto)
const LEFT_POSTITS = [
  { ticker: 'NVDA', rotate: -4, x: 58, y: 52, color: '#fef08a', delay: 0 },
  { ticker: 'TSLA', rotate: -2, x: 70, y: 185, color: '#fca5a5', delay: 0.4 },
  { ticker: 'AMZN', rotate: 1.5, x: 52, y: 325, color: '#c4b5fd', delay: 0.3 },
  { ticker: 'PLTR', rotate: 2.5, x: 60, y: 145, color: '#fdba74', delay: 0.35 },
  { ticker: 'META', rotate: -2.5, x: 64, y: 405, color: '#f87171', delay: 0.25 },
];

const RIGHT_POSTITS = [
  { ticker: 'AAPL', rotate: 2, x: 62, y: 75, color: '#7dd3fc', delay: 0.2 },
  { ticker: 'MSTR', rotate: 3, x: 58, y: 270, color: '#93c5fd', delay: 0.1 },
  { ticker: 'GME', rotate: -3, x: 68, y: 365, color: '#fde047', delay: 0.5 },
  { ticker: 'MSFT', rotate: -1.5, x: 54, y: 170, color: '#6ee7b7', delay: 0.15 },
  { ticker: 'GOOGL', rotate: 1, x: 60, y: 200, color: '#38bdf8', delay: 0.45 },
];

function PostItPanel({
  postits,
  viewBoxWidth,
  filterId,
}: {
  postits: typeof LEFT_POSTITS;
  viewBoxWidth: number;
  filterId: string;
}) {
  return (
    <svg
      className="w-full h-full min-h-[480px]"
      viewBox={`0 0 ${viewBoxWidth} 500`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#64748b" floodOpacity="0.2" />
        </filter>
      </defs>
      <g filter={`url(#${filterId})`}>
        {postits.map((p) => (
          <g key={p.ticker} transform={`translate(${p.x}, ${p.y}) rotate(${p.rotate})`}>
            <g
              className="event-postit-float"
              style={{ animationDelay: `${p.delay}s` }}
            >
              <rect
                x="-40"
                y="-26"
                width="80"
                height="52"
                rx="4"
                fill={p.color}
                stroke="rgba(100, 116, 139, 0.35)"
                strokeWidth="1"
              />
              <text
                x="0"
                y="5"
                textAnchor="middle"
                fill="#334155"
                fontSize="15"
                fontFamily="ui-monospace, monospace"
                fontWeight="700"
              >
                {p.ticker}
              </text>
            </g>
          </g>
        ))}
      </g>
    </svg>
  );
}

export function EventFormBackdropLeft() {
  return (
    <div className="w-full h-full min-h-[480px] pointer-events-none" aria-hidden>
      <PostItPanel postits={LEFT_POSTITS} viewBoxWidth={120} filterId="event-postit-shadow-left" />
    </div>
  );
}

export function EventFormBackdropRight() {
  return (
    <div className="w-full h-full min-h-[480px] pointer-events-none" aria-hidden>
      <PostItPanel postits={RIGHT_POSTITS} viewBoxWidth={120} filterId="event-postit-shadow-right" />
    </div>
  );
}
