import Breadcrumbs, { type Crumb } from "./Breadcrumbs";

interface PageIntroProps {
  crumbs: Crumb[];
  title: string;
  lead?: string;
  children?: React.ReactNode;
}

export default function PageIntro({ crumbs, title, lead, children }: PageIntroProps) {
  return (
    <section className="border-b border-slate-200">
      <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 sm:py-20">
        <Breadcrumbs items={crumbs} />
        <h1 className="mt-6 max-w-4xl text-[2.25rem] font-semibold leading-[1.11] tracking-tight text-slate-900 sm:text-[3rem]">{title}</h1>
        {lead && <p className="mt-5 max-w-[640px] text-lg leading-relaxed text-slate-700">{lead}</p>}
        {children}
      </div>
    </section>
  );
}
