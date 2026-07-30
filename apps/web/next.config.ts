import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
