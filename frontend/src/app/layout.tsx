import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import CookieConsent from "@/components/site/CookieConsent";
import { site } from "@/lib/site";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: { default: `${site.name}: AI data analyst with verified answers`, template: `%s | ${site.name}` },
  description: site.description,
  applicationName: site.name,
  openGraph: { type: "website", siteName: site.name, locale: "en_GB", url: "/" },
  twitter: { card: "summary_large_image" },
  verification: site.googleVerification ? { google: site.googleVerification } : undefined,
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fffafa" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0a0a" },
  ],
};

const themeScript = `try{var t=localStorage.getItem("datapilot-theme");if(t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${geist.variable} ${geistMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        {children}
        <CookieConsent />
      </body>
    </html>
  );
}
