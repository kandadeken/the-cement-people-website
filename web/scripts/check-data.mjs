/* ===========================================================================
   check-data.mjs - safety checks that run before every build
   ---------------------------------------------------------------------------
   `npm run build` runs this first. If any check fails, the build stops and
   nothing is produced, so a broken price list can never be published.

   1. Every product is complete and sensible (name, unit, positive price,
      no duplicate IDs).
   2. The products match the independent reference copy kept with the tests
      (../tests/baseline/products.json). A price, name or unit can only
      change if both files are changed together, deliberately, in the same
      pull request.
   3. The phone number and website printed in the PDF footer (print.css,
      which cannot read business.ts) match business.ts.

   Uses only Node's built-in modules: no extra dependencies.
   =========================================================================== */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const read = (p) => readFileSync(here(p), "utf8");
const problems = [];

// ---- 1. Products are complete ---------------------------------------------
const products = JSON.parse(read("../src/data/products.json"));
const ids = new Set();
for (const p of products) {
  if (ids.has(p.id)) problems.push(`duplicate product id "${p.id}"`);
  ids.add(p.id);
  for (const field of ["id", "category", "name", "unit"]) {
    if (typeof p[field] !== "string" || !p[field].trim()) {
      problems.push(`product "${p.id}" is missing its ${field}`);
    }
  }
  if (typeof p.price !== "number" || !(p.price > 0)) {
    problems.push(`product "${p.id}" has an invalid price: ${p.price}`);
  }
}

// ---- 2. Products match the test baseline ----------------------------------
const baseline = JSON.parse(read("../../tests/baseline/products.json")).products;
const key = (p) => [p.id, p.category, p.name, p.unit, p.price].join(" | ");
const site = products.map(key);
const ref = baseline.map(key);
if (site.length !== ref.length) {
  problems.push(`site has ${site.length} products, baseline has ${ref.length}`);
}
ref.forEach((line, i) => {
  if (site[i] !== line) {
    problems.push(`product ${i + 1} differs from baseline:\n    site:     ${site[i]}\n    baseline: ${line}`);
  }
});

// ---- 3. Business details printed by CSS match business.ts -----------------
const config = read("../src/config/business.ts");
const value = (name) => (config.match(new RegExp(`${name}:\\s*"([^"]+)"`)) || [])[1];
const printCss = read("../src/styles/print.css");
for (const name of ["website", "phone"]) {
  const v = value(name);
  if (!v || !printCss.includes(v)) {
    problems.push(`print.css footer does not show ${name} "${v}" from business.ts`);
  }
}

// ---- Result ---------------------------------------------------------------
if (problems.length) {
  console.error("Data check FAILED:\n  - " + problems.join("\n  - "));
  process.exit(1);
}
console.log(`Data check passed: ${products.length} products match the baseline; print footer matches business.ts.`);
