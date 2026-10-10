import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import Breadcrumbs from "@/components/site/Breadcrumbs";
import JsonLd from "@/components/site/JsonLd";
import { type Block, formatDate, postBySlug, posts } from "@/lib/blog";
import { pageMetadata } from "@/lib/seo";
import { absoluteUrl, site } from "@/lib/site";

type Props = { params: Promise<{ slug: string }> };

export const dynamicParams = false;

export function generateStaticParams() {
  return posts.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const post = postBySlug((await params).slug);
  if (!post) return {};
  return pageMetadata({ title: post.title, description: post.description, path: `/blog/${post.slug}`, type: "article", published: post.published });
}

function renderBlock(block: Block, i: number) {
  switch (block.kind) {
    case "h2":
      return (
        <h2 key={i} className="mt-10 text-xl font-semibold text-slate-900">
          {block.text}
        </h2>
      );
    case "list":
      return (
        <ul key={i} className="mt-4 list-disc space-y-2 pl-6 text-slate-700">
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );
    case "code":
      return (
        <pre key={i} tabIndex={0} className="scroll-thin mt-5 overflow-x-auto rounded-xl bg-code p-4 text-sm leading-relaxed text-code-fg">
          <code className={`language-${block.lang}`}>{block.text}</code>
        </pre>
      );
    case "note":
      return (
        <p key={i} className="mt-6 rounded-xl border border-brand-100 bg-brand-50 p-4 text-sm leading-relaxed text-slate-700">
          {block.text}
        </p>
      );
    default:
      return (
        <p key={i} className="mt-4 leading-relaxed text-slate-700">
          {block.text}
        </p>
      );
  }
}

export default async function PostPage({ params }: Props) {
  const post = postBySlug((await params).slug);
  if (!post) notFound();
  const index = posts.indexOf(post);
  const newer = posts[index - 1];
  const older = posts[index + 1];

  return (
    <article className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BlogPosting",
          headline: post.title,
          description: post.description,
          datePublished: post.published,
          dateModified: post.published,
          mainEntityOfPage: absoluteUrl(`/blog/${post.slug}`),
          image: absoluteUrl("/opengraph-image.png"),
          keywords: post.tags.join(", "),
          author: { "@type": "Organization", name: `${site.name} team`, url: absoluteUrl("/about") },
          publisher: { "@id": absoluteUrl("/#organization") },
        }}
      />
      <Breadcrumbs
        items={[
          { name: "Blog", href: "/blog" },
          { name: post.title, href: `/blog/${post.slug}` },
        ]}
      />
      <header className="mt-6">
        <p className="text-sm text-slate-500">
          <time dateTime={post.published}>{formatDate(post.published)}</time> · {post.minutes} min read · {site.name} team
        </p>
        <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl">{post.title}</h1>
        <p className="mt-4 text-lg leading-relaxed text-slate-600">{post.description}</p>
      </header>
      <div className="mt-6 border-t border-slate-200 pt-2">{post.body.map(renderBlock)}</div>
      <aside className="mt-12 rounded-2xl bg-gradient-to-br from-brand-700 to-sky-600 p-6 text-white">
        <p className="text-lg font-semibold">Try it on your own data</p>
        <p className="mt-1 text-sm text-white/85">Upload a CSV or load the sample datasets and ask your first question.</p>
        <Link href="/login?mode=register" className="mt-4 inline-block rounded-lg bg-white px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50">
          Get started
        </Link>
      </aside>
      <nav aria-label="More posts" className="mt-10 grid gap-4 sm:grid-cols-2">
        {older && (
          <Link href={`/blog/${older.slug}`} className="rounded-xl border border-slate-200 bg-surface p-4 hover:border-brand-500">
            <span className="text-xs text-slate-500">Older post</span>
            <span className="mt-1 block font-semibold text-slate-900">{older.title}</span>
          </Link>
        )}
        {newer && (
          <Link href={`/blog/${newer.slug}`} className="rounded-xl border border-slate-200 bg-surface p-4 text-right hover:border-brand-500 sm:col-start-2">
            <span className="text-xs text-slate-500">Newer post</span>
            <span className="mt-1 block font-semibold text-slate-900">{newer.title}</span>
          </Link>
        )}
      </nav>
    </article>
  );
}
