import type { Metadata } from "next";
import { Epilogue, Syne } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700", "800"],
});

const epilogue = Epilogue({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "replanme",
    template: "%s | replanme",
  },
  description: "AI-assisted scheduling for Google Calendar, weekly planning, and monthly planning.",
  applicationName: "replanme",
  category: "productivity",
  openGraph: {
    siteName: "replanme",
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
      <body className={`${syne.variable} ${epilogue.variable}`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
