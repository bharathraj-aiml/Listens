import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import GlassPreference from "@/components/GlassPreference";
import WakingBanner from "@/components/WakingBanner";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Shadow Listens",
  description: "Your private music streaming server",
  icons: { icon: "/favicon.svg" },
};
export const viewport: Viewport = { themeColor: "#0c0d11", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <GlassPreference />
        <WakingBanner />
        {children}
      </body>
    </html>
  );
}
