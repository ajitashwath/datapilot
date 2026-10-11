export const BRAND_MARK_PATHS = [
  "M313 433L401 519V718L313 798Z",
  "M333 373H462Q486 373 502 389L629 514A172 172 0 0 1 507 809H331L413 727H504A76 76 0 0 0 557.5 597.5Z",
  "M560 373H835.5A144.5 144.5 0 0 1 980 517.5A144.5 144.5 0 0 1 835.5 662H784V775L698 858V584H831A64.5 64.5 0 0 0 895.5 519.5A64.5 64.5 0 0 0 831 455H642Z",
];

export const BRAND_MARK_VIEWBOX = "313 373 667 485";

export default function BrandMark({ className = "h-7 w-auto" }: { className?: string }) {
  return (
    <svg aria-hidden="true" focusable="false" viewBox={BRAND_MARK_VIEWBOX} className={`shrink-0 text-brand-500 ${className}`} fill="currentColor">
      {BRAND_MARK_PATHS.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
