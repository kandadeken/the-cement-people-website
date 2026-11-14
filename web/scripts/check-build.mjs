/* ===========================================================================
   check-build.mjs - "is this build safe to put on thecementpeople.com?"
   ---------------------------------------------------------------------------
   Runs after `npm run build`, on the files in web/dist/. The publishing
   workflow (.github/workflows/astro-publish.yml) runs it before packaging the
   site, so a build that fails any check is never packaged or published.

   It guards against the mistakes that would hurt the live site most:
     1. The homepage, the quotation engine and the stylesheet are present.
     2. The page is open to search engines: no "noindex" anywhere. (The
        preview copy made by make-preview.mjs adds noindex; that copy must
        never reach the real domain.)
     3. robots.txt lets search engines in and names the sitemap.
     4. CNAME says thecementpeople.com (the real domain, nothing else).
     5. The canonical address is https://thecementpeople.com/.
     6. Every file the homepage links to (images, scripts, styles, icons)
        is really in the build.
     7. All 17 products are written into the page, as the tests expect.

   Usage:  node scripts/check-build.mjs        (from web/)
   Exit code 0 = safe; anything else = a list of problems, and stop.
   Uses only Node's built-in features: no extra dependencies.
   =========================================================================== */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const problems = [];
const file = (p) => join(dist, p);
const read = (p) => readFileSync(file(p), "utf8");

// 1. The essentials are there.
for (const p of ["index.html", "scripts/quote-engine.js", "robots.txt", "sitemap.xml", "CNAME"]) {
  if (!existsSync(file(p))) problems.push(`missing ${p}`);
}
const astroDir = existsSync(file("_astro")) ? readdirSync(file("_astro")) : [];
if (!astroDir.some((n) => n.endsWith(".css"))) problems.push("no stylesheet in _astro/");

if (existsSync(file("index.html"))) {
  const html = read("index.html");

  // 2. Open to search engines.
  if (/<meta[^>]+name=["']robots["'][^>]*noindex/i.test(html) || /noindex/i.test(html)) {
    problems.push('index.html contains "noindex": this looks like the preview copy, not the production build');
  }

  // 3. robots.txt lets crawlers in and names the sitemap.
  const robots = existsSync(file("robots.txt")) ? read("robots.txt") : "";
  if (/^\s*Disallow:\s*\/\s*$/im.test(robots)) problems.push("robots.txt blocks the whole site");
  if (!/^\s*Sitemap:\s*https:\/\/thecementpeople\.com\/sitemap\.xml\s*$/im.test(robots)) {
    problems.push("robots.txt does not name https://thecementpeople.com/sitemap.xml");
  }

  // 4. CNAME is the real domain.
  const cname = existsSync(file("CNAME")) ? read("CNAME").trim() : "";
  if (cname && cname !== "thecementpeople.com") problems.push(`CNAME is "${cname}", expected "thecementpeople.com"`);

  // 5. Canonical address.
  const canonical = html.match(/<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']+)["']/i);
  if (!canonical || canonical[1] !== "https://thecementpeople.com/") {
    problems.push(`canonical address is ${canonical ? canonical[1] : "missing"}, expected https://thecementpeople.com/`);
  }

  // 6. Every local file the page links to exists. Covers src/href/srcset.
  const refs = new Set();
  for (const m of html.matchAll(/\s(?:src|href)=["'](\/[^"'#?]*)["']/g)) refs.add(m[1]);
  for (const m of html.matchAll(/\ssrcset=["']([^"']+)["']/g)) {
    for (const part of m[1].split(",")) {
      const url = part.trim().split(/\s+/)[0];
      if (url.startsWith("/")) refs.add(url);
    }
  }
  for (const r of refs) {
    if (r === "/") continue;
    if (!existsSync(file(r.replace(/^\//, "")))) problems.push(`page links to ${r}, which is not in the build`);
  }

  // 7. All products are in the page itself.
  const rows = (html.match(/data-inc="/g) || []).length;
  if (rows !== 17) problems.push(`expected 17 products in the page, found ${rows}`);

  if (problems.length === 0) {
    console.log(`Build check passed: ${refs.size} linked files present, open to search engines, CNAME ${cname}.`);
  }
}

if (problems.length) {
  console.error("Build check FAILED - this build must not be published:\n  - " + problems.join("\n  - "));
  process.exit(1);
}
