import { Sparkle } from "./Icons";

interface SectionHeadingProps {
  id: string;
  first: string;
  second: string;
  lead?: string;
}

export default function SectionHeading({ id, first, second, lead }: SectionHeadingProps) {
  return (
    <div className="mx-auto max-w-3xl text-center">
      <h2 id={id} className="text-[2rem] font-semibold leading-[1.11] tracking-tight sm:text-[2.75rem]">
        <span className="block text-slate-900">{first}</span>
        <span className="block text-brand-500">
          {second}
          <Sparkle className="ml-3 hidden h-7 w-7 align-[-0.05em] sm:inline-block" />
        </span>
      </h2>
      {lead && <p className="mx-auto mt-5 max-w-[640px] text-lg leading-relaxed text-slate-700">{lead}</p>}
    </div>
  );
}
