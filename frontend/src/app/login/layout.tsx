import type { Metadata } from "next";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata({
  title: "Sign in",
  description: "Sign in to DataPilot or create an account. Ask questions about your data and get answers computed by SQL and Python, with the code shown.",
  path: "/login",
});

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
