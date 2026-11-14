import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LegalMind AI",
  description: "AI-assisted legal document analysis. Not legal advice.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
