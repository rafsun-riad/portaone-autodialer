import type { Metadata } from "next";
import { Roboto } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

const roboto = Roboto({
  variable: "--font-roboto",
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
});

export const metadata: Metadata = {
  title: "PortaOne Autodialer",
  description:
    "Campaign and autodialer operations for PortaOne-backed calling.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${roboto.variable} h-full antialiased`}>
      <body className="min-h-full font-sans text-slate-950">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
