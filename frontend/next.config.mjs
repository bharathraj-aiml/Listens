/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // small production image: `node server.js`
  poweredByHeader: false,
  reactStrictMode: true,
  // Local `next dev` (port 3000) has no gateway in front: proxy the API paths to it.
  async rewrites() {
    const gw = process.env.DEV_GATEWAY_URL;
    return gw ? [{ source: "/api/:path*", destination: `${gw}/api/:path*` }] : [];
  },
};
export default nextConfig;
