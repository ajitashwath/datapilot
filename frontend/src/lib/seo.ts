import type { Metadata } from "next";
import { site } from "./site";

interface PageMeta {
  title: string;
  description: string;
  path: string;
  type?: "website" | "article";
  published?: string;
}

const SHARE_IMAGE = { url: "/opengraph-image.png", width: 1200, height: 630, alt: "DataPilot: ask your data a question, get an answer you can check" };

export function pageMetadata({ title, description, path, type = "website", published }: PageMeta): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      type,
      siteName: site.name,
      locale: "en_GB",
      url: path,
      title: `${title} | ${site.name}`,
      description,
      images: [SHARE_IMAGE],
      ...(published ? { publishedTime: published } : {}),
    },
    twitter: { card: "summary_large_image", title: `${title} | ${site.name}`, description, images: [SHARE_IMAGE] },
  };
}
