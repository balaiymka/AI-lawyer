import type { NextConfig } from "next";

// Демо через туннель (scripts/demo.sh): сайт и API идут через один адрес — запросы /backend/* проксируются в API,
// поэтому снаружи нужен только один публичный URL. Сборка демо лежит отдельно (.next-demo), чтобы не ломать `next dev`.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  compress: process.env.NEXT_DIST_DIR === ".next-demo" ? false : true, // без сжатия SSE-поток ответа AI не копится в буфере прокси
  async rewrites() {
    const api = process.env.API_ORIGIN || "http://127.0.0.1:8000";
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
