/** @type {import('next').NextConfig} */

// When running in GitHub Actions we build a fully-static export for GitHub Pages.
// GITHUB_ACTIONS is set automatically to "true" by the runner.
const isGitHubPages = process.env.GITHUB_ACTIONS === "true";

const nextConfig = {
  // Static export — only activated in CI so local dev/start keep working.
  ...(isGitHubPages && {
    output: "export",
    basePath: "/tfm-cardiologia-fhir",
    trailingSlash: true,
  }),

  // next/image optimisation requires a server; disable for static builds.
  images: {
    unoptimized: true,
  },

  // CORS header for local FastAPI proxy — omitted entirely in static export
  // (GitHub Pages ignores custom headers; including the key causes a Next.js warning).
  ...(!isGitHubPages && {
    async headers() {
      return [
        {
          source: "/api/:path*",
          headers: [{ key: "Access-Control-Allow-Origin", value: "*" }],
        },
      ];
    },
  }),
};

export default nextConfig;
