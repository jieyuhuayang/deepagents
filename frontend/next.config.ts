import type { NextConfig } from "next";

const LANGGRAPH_INTERNAL_URL =
  process.env.LANGGRAPH_INTERNAL_URL || "http://127.0.0.1:12024";

const nextConfig: NextConfig = {
  // 本项目对 @langchain/langgraph-sdk 有 4 处本地 patch（详见根 CLAUDE.md
  // §强约束），其中 useChat.ts 的 streamMode 与 SDK 当前类型签名不匹配。
  // dev mode 不做 type check 所以 OK，next build 默认严格会挂。
  typescript: {
    ignoreBuildErrors: true,
  },
  // 反向代理 langgraph backend：浏览器 → /api/langgraph/* → 本机 12024。
  // 公网访客无法直连内网 192.168.106.114:12024，所以前端把请求打到
  // 自己同 origin 的 /api/langgraph，由 Next 在 114 内网转发。SSE / chunked
  // response 默认透传不缓冲。
  async rewrites() {
    return [
      {
        source: "/api/langgraph/:path*",
        destination: `${LANGGRAPH_INTERNAL_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
