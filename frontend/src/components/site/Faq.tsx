import { faqs } from "@/lib/faq";
import { Chevron } from "./Icons";
import JsonLd from "./JsonLd";

export default function Faq() {
  return (
    <>
      <div className="border-t border-slate-200">
        {faqs.map((item) => (
          <details key={item.q} className="group border-b border-slate-200">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-6 text-left text-lg font-medium text-slate-900 [&::-webkit-details-marker]:hidden">
              {item.q}
              <Chevron className="h-5 w-5 shrink-0 text-slate-500 transition-transform duration-200 group-open:rotate-180" />
            </summary>
            <p className="-mt-2 max-w-3xl pb-6 leading-relaxed text-slate-600">{item.a}</p>
          </details>
        ))}
      </div>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: faqs.map((item) => ({ "@type": "Question", name: item.q, acceptedAnswer: { "@type": "Answer", text: item.a } })),
        }}
      />
    </>
  );
}
