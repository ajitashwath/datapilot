import Breadcrumbs, { type Crumb } from "./Breadcrumbs";

interface PageIntroProps {
  crumbs: Crumb[];
  title: string;
  lead?: string;
  children?: React.ReactNode;
}

export default function PageIntro({ crumbs, title, lead, children }: PageIntroProps) {
  return (
    <section className="border-b border-slate-200 bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
        <Breadcrumbs items={crumbs} />
        <h1 className="mt-4 max-w-3xl text-3xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl">{title}</h1>
        {lead && <p className="mt-4 max-w-2xl text-lg leading-relaxed text-slate-600">{lead}</p>}
        {children}
      </div>
    </section>
  );
}
