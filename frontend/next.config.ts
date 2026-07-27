import type { NextConfig } from "next";
import path from "path";
const allowedDevOrigins = (
  process.env.NEXT_ALLOWED_DEV_ORIGINS ?? "*.trycloudflare.com"
)
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  allowedDevOrigins,
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
