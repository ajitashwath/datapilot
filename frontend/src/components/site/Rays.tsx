const COUNT = 64;
const CX = 600;
const CY = 300;
const LENGTH = 1400;

const lines = Array.from({ length: COUNT }, (_, i) => {
  const angle = (i / COUNT) * Math.PI * 2;
  return { x: Math.round(CX + Math.cos(angle) * LENGTH), y: Math.round(CY + Math.sin(angle) * LENGTH) };
});

export default function Rays({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 1200 600"
      preserveAspectRatio="xMidYMid slice"
      className={`pointer-events-none absolute inset-0 h-full w-full text-brand-100 ${className}`}
    >
      <g stroke="currentColor" strokeWidth="1">
        {lines.map((p, i) => (
          <line key={i} x1={CX} y1={CY} x2={p.x} y2={p.y} />
        ))}
      </g>
      <ellipse cx={CX} cy={CY} rx="360" ry="190" className="fill-surface" />
    </svg>
  );
}
