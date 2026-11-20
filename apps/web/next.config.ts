import type { NextConfig } from "next";

// Демо через туннель (scripts/demo.sh): сайт и API идут через один адрес — запросы /backend/* проксируются в API,
// поэтому снаружи нужен только один публичный URL. Сборка демо лежит отдельно (.next-demo), чтобы не ломать `next dev`.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Без сжатия SSE-поток ответа AI не копится в буфере прокси. На сервере сжимает Caddy (NEXT_NO_COMPRESS=1).
  compress: process.env.NEXT_DIST_DIR === ".next-demo" || process.env.NEXT_NO_COMPRESS === "1" ? false : true,
  experimental: {
    // Поиск на сервере без видеокарты идёт 15–60 с; по умолчанию прокси обрывает запрос через 30 с.
    proxyTimeout: 180_000,
  },
  async rewrites() {
    const api = process.env.API_ORIGIN || "http://127.0.0.1:8000";
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
