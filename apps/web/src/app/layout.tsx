import type { Metadata } from "next";
import { IBM_Plex_Sans, Sora } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-display",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Resched.me",
    template: "%s | Resched.me",
  },
  description: "AI-assisted scheduling for Google Calendar, weekly planning, and monthly planning.",
  applicationName: "Resched.me",
  category: "productivity",
  openGraph: {
    siteName: "Resched.me",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${sora.variable} ${plexSans.variable}`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
