import type { Metadata } from "next";
import Link from "next/link";
import PageIntro from "@/components/site/PageIntro";
import { formatDate, posts } from "@/lib/blog";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Blog",
  description: "Practical writing on trustworthy AI analysis, anomaly detection, data quality, SQL joins and reporting workflows.",
  path: "/blog",
});

export default function BlogPage() {
  return (
    <>
      <PageIntro
        crumbs={[{ name: "Blog", href: "/blog" }]}
        title="Blog"
        lead="Practical notes on getting answers from data that you can actually defend."
      />
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <ul className="divide-y divide-slate-200">
          {posts.map((post) => (
            <li key={post.slug} className="py-8 first:pt-0">
              <article>
                <p className="text-xs text-slate-500">
                  <time dateTime={post.published}>{formatDate(post.published)}</time> · {post.minutes} min read · {post.tags.join(", ")}
                </p>
                <h2 className="mt-2 text-xl font-semibold leading-snug text-slate-900">
                  <Link href={`/blog/${post.slug}`} className="hover:text-brand-600">
                    {post.title}
                  </Link>
                </h2>
                <p className="mt-2 leading-relaxed text-slate-600">{post.description}</p>
                <Link href={`/blog/${post.slug}`} className="mt-3 inline-block text-sm font-semibold text-brand-600 hover:underline" aria-label={`Read ${post.title}`}>
                  Read the post
                </Link>
              </article>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
