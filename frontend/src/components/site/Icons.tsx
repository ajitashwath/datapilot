type IconProps = { className?: string };

export function Sparkle({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="currentColor">
      <path d="M10 1.5l1.9 5.3c.2.6.7 1.1 1.3 1.3l5.3 1.9-5.3 1.9c-.6.2-1.1.7-1.3 1.3L10 18.5l-1.9-5.3c-.2-.6-.7-1.1-1.3-1.3L1.5 10l5.3-1.9c.6-.2 1.1-.7 1.3-1.3z" />
    </svg>
  );
}

export function ArrowRight({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  );
}

export function Check({ className = "h-4 w-4" }: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 10.5l3.5 3.5 7.5-8" />
    </svg>
  );
}

export function Chevron({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 7.5l5 5 5-5" />
    </svg>
  );
}

const featurePaths: Record<string, string> = {
  "natural-language-analysis": "M3 5.5A2.5 2.5 0 0 1 5.5 3h9A2.5 2.5 0 0 1 17 5.5v6a2.5 2.5 0 0 1-2.5 2.5H9l-3.5 3v-3A2.5 2.5 0 0 1 3 11.5z",
  charts: "M3 17h14M5.5 14V9M10 14V5M14.5 14v-3",
  "anomaly-detection": "M2.5 12.5l3.5-3 3 2.5 4.5-6 4 3.5M14 4.5a1.5 1.5 0 1 0 0 .01",
  "data-quality": "M10 2.5l6 2.5v4.5c0 3.8-2.6 7-6 8-3.4-1-6-4.2-6-8V5zM7.2 10l2 2 3.6-3.8",
  "multi-file-joins": "M7 6.5a3.5 3.5 0 1 0 0 7M13 6.5a3.5 3.5 0 1 1 0 7M7 10h6",
  "data-connectors": "M7 3v4M13 3v4M5 7h10v3a5 5 0 0 1-10 0zM10 15v2.5",
  "scheduled-queries": "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM10 6.5V10l2.5 1.5",
  "teams-and-sharing": "M7 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM2.5 16a4.5 4.5 0 0 1 9 0M13.5 9a2 2 0 1 0 0-4M14 11.5a4 4 0 0 1 3.5 4",
  understand: "M10 3a5 5 0 0 0-3 9v2.5h6V12a5 5 0 0 0-3-9zM8 17h4",
  compute: "M4 5.5h12M4 10h12M4 14.5h7M14 13l2 2-2 2",
  verify: "M10 2.5l6 2.5v4.5c0 3.8-2.6 7-6 8-3.4-1-6-4.2-6-8V5zM7.2 10l2 2 3.6-3.8",
};

export function FeatureIcon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d={featurePaths[name] ?? featurePaths.compute} />
    </svg>
  );
}

export function IconBubble({ name }: { name: string }) {
  return (
    <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 text-brand-600">
      <FeatureIcon name={name} />
    </span>
  );
}
