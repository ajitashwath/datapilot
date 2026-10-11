import BrandMark from "@/components/BrandMark";

export default function LinkPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <section className="w-full max-w-sm rounded-2xl border border-slate-200 bg-surface p-6 shadow-card">
        <div className="mb-4 flex items-center gap-3">
          <BrandMark className="h-8 w-auto" />
          <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
        </div>
        {children}
      </section>
    </main>
  );
}
