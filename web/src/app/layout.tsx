import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Airmate — Asthma Air Guard",
  description: "Live indoor air risk and proactive asthma companion",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-slate-100">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
