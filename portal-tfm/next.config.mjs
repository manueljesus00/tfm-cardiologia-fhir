/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow cross-origin requests during development to the FastAPI backend
  async headers() {
    return [
      {
        source: "/api/:path*",
        headers: [
          { key: "Access-Control-Allow-Origin", value: "*" },
        ],
      },
    ];
  },
};

export default nextConfig;
