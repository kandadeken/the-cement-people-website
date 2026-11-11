/* ===========================================================================
   check-data.mjs - safety checks that run before every build
   ---------------------------------------------------------------------------
   `npm run build` runs this first. If any check fails, the build stops and
   nothing is produced, so a broken price list or wrong business detail can
   never be published.

   1. Every product is complete and sensible (name, unit, positive price,
      no duplicate IDs).
   2. The products match the independent reference copy kept with the tests
      (../tests/baseline/products.json). A price, name or unit can only
      change if both files are changed together, deliberately, in the same
      pull request.
   3. The business details in src/config/business.ts are well-formed (a real
      email shape, coordinates inside Ghana's range, opening times as HH:MM,
      and so on).
   4. The business details match their independent reference copy
      (../tests/baseline/business.json), under the same rule as the products.
   5. The phone number and website printed in the PDF footer (print.css,
      which cannot read business.ts) match business.ts.

   Uses only Node's built-in features: no extra dependencies. (Node 22 can
   read the TypeScript file business.ts directly.)
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

// ---- 3. Business details are well-formed ----------------------------------
const { business } = await import("../src/config/business.ts");
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const need = (ok, message) => { if (!ok) problems.push(message); };

need(/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(business.publicEmail), `publicEmail is not an email address: ${business.publicEmail}`);
need(business.publicEmail.endsWith("@" + business.website), "publicEmail is not at the business's own domain");
need(/^\+233\d{9}$/.test(business.phoneInternational), `phoneInternational is not +233 followed by 9 digits: ${business.phoneInternational}`);
need("0" + business.phoneInternational.slice(4) === business.phone.replace(/\s/g, ""), "phone and phoneInternational are different numbers");
need(/^233\d{9}$/.test(business.whatsapp), `whatsapp is not 233 followed by 9 digits: ${business.whatsapp}`);
need(business.siteUrl === "https://" + business.website, "siteUrl and website disagree");
for (const part of ["street", "area", "locality", "region", "country"]) {
  need(typeof business.address[part] === "string" && business.address[part].trim(), `address.${part} is empty`);
}
need(/^[A-Z]{2}$/.test(business.address.countryCode), "address.countryCode is not a two-letter country code");
// Ghana lies roughly between latitude 4.5 and 11.5, longitude -3.5 and 1.5.
need(business.geo.latitude > 4.5 && business.geo.latitude < 11.5, `geo.latitude is outside Ghana: ${business.geo.latitude}`);
need(business.geo.longitude > -3.5 && business.geo.longitude < 1.5, `geo.longitude is outside Ghana: ${business.geo.longitude}`);
need(/^[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}( .+)?$/.test(business.plusCode), `plusCode is not a Plus Code: ${business.plusCode}`);
need(/^https:\/\//.test(business.mapUrl), "mapUrl is not an https link");
const openDays = [];
for (const block of business.openingHours) {
  need(/^([01]\d|2[0-3]):[0-5]\d$/.test(block.opens) && /^([01]\d|2[0-3]):[0-5]\d$/.test(block.closes), `opening hours must be HH:MM, got ${block.opens}-${block.closes}`);
  need(block.opens < block.closes, `opening time ${block.opens} is not before closing time ${block.closes}`);
  for (const day of block.days) {
    need(DAYS.includes(day), `"${day}" is not a day of the week`);
    openDays.push(day);
  }
}
for (const day of business.closedDays) {
  need(DAYS.includes(day), `"${day}" is not a day of the week`);
  need(!openDays.includes(day), `${day} is listed as both open and closed`);
}
need([...openDays, ...business.closedDays].sort().join() === [...DAYS].sort().join(), "opening hours and closed days do not cover each day of the week exactly once");
need(business.deliveryAreas.length > 0 && business.deliveryAreas.every((a) => a.trim()), "deliveryAreas is empty");

// ---- 4. Business details match the test baseline --------------------------
const reference = JSON.parse(read("../../tests/baseline/business.json"));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
for (const field of [
  "name", "website", "siteUrl", "phone", "phoneInternational", "whatsapp", "publicEmail", "town",
  "address", "landmark", "plusCode", "geo", "mapUrl", "openingHours", "closedDays", "deliveryAreas",
  "currencyCode", "currencySymbol", "taxRate",
]) {
  if (!same(business[field], reference[field])) {
    problems.push(`business.${field} differs from tests/baseline/business.json:\n    site:     ${JSON.stringify(business[field])}\n    baseline: ${JSON.stringify(reference[field])}`);
  }
}

// ---- 5. Business details printed by CSS match business.ts -----------------
const printCss = read("../src/styles/print.css");
for (const name of ["website", "phone"]) {
  if (!printCss.includes(business[name])) {
    problems.push(`print.css footer does not show ${name} "${business[name]}" from business.ts`);
  }
}

// ---- Result ---------------------------------------------------------------
if (problems.length) {
  console.error("Data check FAILED:\n  - " + problems.join("\n  - "));
  process.exit(1);
}
console.log(`Data check passed: ${products.length} products and the business details match their baselines; print footer matches business.ts.`);
