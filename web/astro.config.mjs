/* ===========================================================================
   astro.config.mjs - Astro's settings for The Cement People site
   ---------------------------------------------------------------------------
   Kept deliberately small. No integrations or plugins are installed.
   =========================================================================== */
import { defineConfig } from "astro/config";

export default defineConfig({
  // The live address. Used for canonical links, link previews and the sitemap.
  site: "https://thecementpeople.com",

  // Build a plain static site (HTML, CSS, images) into web/dist/.
  // No server is needed to host it.
  output: "static",

  // Keep the generated HTML readable instead of squashing it onto one line,
  // so it can be compared with the original page.
  compressHTML: false,
});
