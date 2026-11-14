/* ===========================================================================
   make-preview.mjs - turns the production build into a private preview copy
   ---------------------------------------------------------------------------
   Used before the switch-over, so the real Astro site can be tried at a
   separate address (a free GitHub Pages site) without touching
   thecementpeople.com.

   Run after `npm run build`:
       node scripts/make-preview.mjs <output folder>

   It copies web/dist/ (the exact production build, nothing rebuilt) and then
   makes only these changes to the COPY:
     1. Removes CNAME. That file claims the domain thecementpeople.com; a
        preview must never claim it, or GitHub could move the domain to it.
     2. Adds <meta name="robots" content="noindex, nofollow"> to every page,
        so Google does not list the preview.
     3. Replaces robots.txt with "Disallow: /" for the same reason.
     4. Adds .nojekyll, so GitHub Pages serves the files exactly as they are
        (otherwise it hides the _astro/ folder, whose name starts with "_").
   The production build in web/dist/ itself is not changed.

   Note: the preview must be served from the ROOT of an address (for example
   https://<name>.github.io/), because the site links to its files as
   /images/..., /scripts/... and so on.
   =========================================================================== */
import { cpSync, existsSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const out = process.argv[2] ? resolve(process.argv[2]) : null;
if (!out) {
  console.error("Usage: node scripts/make-preview.mjs <output folder>");
  process.exit(1);
}
if (!existsSync(join(dist, "index.html"))) {
  console.error("No build found in web/dist/. Run `npm run build` first.");
  process.exit(1);
}

// Start from an empty output folder, but keep a git checkout's .git folder
// (the output is usually a clone of the preview repository).
if (existsSync(out)) {
  for (const name of readdirSync(out)) if (name !== ".git") rmSync(join(out, name), { recursive: true, force: true });
}
cpSync(dist, out, { recursive: true });

// 1. Never claim the real domain.
rmSync(join(out, "CNAME"), { force: true });

// 2. noindex on every HTML page.
const NOINDEX = '<meta name="robots" content="noindex, nofollow">';
const pages = [];
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (name === ".git") continue;
    if (statSync(p).isDirectory()) walk(p);
    else if (name.endsWith(".html")) pages.push(p);
  }
};
walk(out);
for (const p of pages) {
  const html = readFileSync(p, "utf8");
  if (!html.includes("<head>")) throw new Error(`${p} has no <head>`);
  writeFileSync(p, html.replace("<head>", `<head>${NOINDEX}`));
}

// 3. Ask all crawlers to stay out.
writeFileSync(join(out, "robots.txt"), "# Preview copy of thecementpeople.com: not for search engines.\nUser-agent: *\nDisallow: /\n");

// 4. Serve files exactly as they are.
writeFileSync(join(out, ".nojekyll"), "");

console.log(`Preview written to ${out}: ${pages.length} page(s) marked noindex, CNAME removed.`);
