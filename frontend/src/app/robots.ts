import type { MetadataRoute } from "next";

// Every page here requires login and shows one person's private library - there's nothing
// public to index, so this just keeps crawlers out rather than listing sitemap entries that
// would all 404 or redirect to /login for an anonymous bot anyway.
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
