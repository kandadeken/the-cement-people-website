/* ===========================================================================
   sitemap.xml.ts - builds /sitemap.xml, the list of pages search engines read
   ---------------------------------------------------------------------------
   Written by hand instead of adding a sitemap plugin: with one page today,
   a plugin would be an extra dependency for very little. When product pages
   arrive (Phase 3), add their addresses to PAGES, or replace this with the
   official @astrojs/sitemap integration.
   =========================================================================== */
import type { APIRoute } from "astro";
import { business } from "../config/business";

// Every public page, as a path on the site.
const PAGES = ["/"];

export const GET: APIRoute = () => {
  const urls = PAGES.map(
    (path) => `  <url><loc>${new URL(path, business.siteUrl).href}</loc></url>`,
  ).join("\n");
  const xml =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
  return new Response(xml, { headers: { "Content-Type": "application/xml" } });
};
