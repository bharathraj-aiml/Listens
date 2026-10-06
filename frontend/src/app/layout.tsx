import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shadow Listens",
  description: "Your private music streaming server",
  icons: { icon: "/favicon.svg" },
};
export const viewport: Viewport = { themeColor: "#0b0b12", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
