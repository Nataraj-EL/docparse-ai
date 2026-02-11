import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "katex/dist/katex.min.css";
import "./globals.css";

// Using Inter as a fallback font that's similar to Geist
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "DocuMind AI | Academic Intelligence",
  description: "A premium RAG powered research and study assistant.",
};

export const dynamic = 'force-dynamic';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable}`} suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        {/* Prevent any favicon.ico requests */}
        <link rel="icon" href="data:;base64,iVBORw0KGgo=" />
      </head>
      <body className="min-h-screen bg-slate-50 dark:bg-[#0f172a] font-sans antialiased overflow-x-hidden">
        {children}
      </body>
    </html>
  );
}
