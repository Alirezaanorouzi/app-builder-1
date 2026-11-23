import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "path";

// Load repo-root .env when running from apps/web
loadEnvConfig(path.join(__dirname, "..", ".."));

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

export default nextConfig;