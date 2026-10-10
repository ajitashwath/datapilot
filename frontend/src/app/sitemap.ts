import type { MetadataRoute } from "next";
import { posts } from "@/lib/blog";
import { features } from "@/lib/features";
import { absoluteUrl, site } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const updated = new Date(site.updated);
  const latestPost = new Date(posts.map((p) => p.published).sort().at(-1) ?? site.updated);
  const page = (path: string, priority: number, changeFrequency: "weekly" | "monthly" | "yearly", lastModified = updated) => ({
    url: absoluteUrl(path),
    lastModified,
    changeFrequency,
    priority,
  });
  return [
    page("/", 1, "weekly"),
    page("/features", 0.9, "monthly"),
    ...features.map((f) => page(`/features/${f.slug}`, 0.8, "monthly")),
    page("/examples", 0.7, "monthly"),
    page("/blog", 0.7, "weekly", latestPost),
    ...posts.map((p) => page(`/blog/${p.slug}`, 0.6, "yearly", new Date(p.published))),
    page("/about", 0.5, "yearly"),
    page("/contact", 0.5, "yearly"),
    page("/login", 0.4, "yearly"),
    page("/privacy", 0.2, "yearly"),
    page("/terms", 0.2, "yearly"),
  ];
}
