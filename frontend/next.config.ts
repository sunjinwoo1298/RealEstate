import type { NextConfig } from "next";

// In production the browser talks only to the Vercel domain. `/api/v1/*` is proxied to the backend
// (BACKEND_URL, e.g. https://estateflow-api.onrender.com), so the refresh-token cookies stay
// first-party (no third-party-cookie problems on Safari/Brave) and no CORS is involved.
// Locally BACKEND_URL is unset and the app calls NEXT_PUBLIC_API_URL (http://localhost:8000/api/v1) directly.
const backendUrl = process.env.BACKEND_URL?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    if (!backendUrl) return [];
    return [{ source: "/api/v1/:path*", destination: `${backendUrl}/api/v1/:path*` }];
  },
};

export default nextConfig;
