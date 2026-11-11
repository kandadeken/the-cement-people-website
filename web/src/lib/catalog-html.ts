/* ===========================================================================
   catalog-html.ts - writes the price list into the page when the site is built
   ---------------------------------------------------------------------------
   WHY THIS EXISTS
   The quotation engine (public/scripts/quote-engine.js) draws the category
   tiles, the category tabs and the price list in the visitor's browser.
   Search engines and AI tools that do not run scripts therefore saw an empty
   catalogue. These functions produce the SAME markup at build time, so all
   17 products are in the HTML itself.

   HOW IT STAYS CORRECT
   Each function below mirrors one piece of the engine and says which. When
   the page loads, the engine still redraws everything, so it remains the one
   in charge of behaviour. A test (tests/test_seo.py) opens the page with
   scripts switched off and again with them on, and fails unless the two
   versions of the markup are identical. If you change markup in the engine,
   change it here too; the test will tell you if you forget.

   The one deliberate difference: prices here are always written the
   English way (GH₵1,392.00). The engine then rewrites them in the number
   style of the visitor's own phone or computer, exactly as before.
   =========================================================================== */

/** A product in the short form the engine uses: {id, cat, sub?, name, unit, price}. */
export interface EngineProduct {
  id: string;
  cat: string;
  sub?: string;
  name: string;
  unit: string;
  price: number;
}

/** A product as stored in src/data/products.json. */
interface StoredProduct {
  id: string;
  category: string;
  subgroup?: string;
  name: string;
  unit: string;
  price: number;
}

/** Convert products.json entries to the engine's short field names. */
export function toEngineProducts(products: StoredProduct[]): EngineProduct[] {
  return products.map((p) => ({
    id: p.id,
    cat: p.category,
    ...(p.subgroup ? { sub: p.subgroup } : {}),
    name: p.name,
    unit: p.unit,
    price: p.price,
  }));
}

/** Category names in the order they first appear. Mirrors the engine's `cats`. */
export function categories(P: EngineProduct[]): string[] {
  return [...new Set(P.map((p) => p.cat))];
}

// Small icons shown beside each category heading. Mirrors the engine's `ICON`.
const ICON_CEMENT = `<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M6 5h16l3 5v14H3V10z" fill="currentColor"/><rect x="8" y="12" width="12" height="8" fill="#f2c300"/></svg>`;
const ICON_RODS = `<svg viewBox="0 0 28 28" aria-hidden="true"><rect x="2" y="5" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="12" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="19" width="24" height="4" rx="2" fill="currentColor"/><rect x="11" y="3" width="5" height="22" fill="#f2c300"/></svg>`;
const ICON: Record<string, string> = {
  "Cement": ICON_CEMENT,
  "Iron rods and wire": ICON_RODS,
  "Iron Rods (Single Piece)": ICON_RODS,
  "Iron Rods (Per Ton)": ICON_RODS,
};

/** GH₵1,392.00 - mirrors the engine's `money()`, fixed to English number style. */
export function money(n: number, currency: string): string {
  return currency + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** The "Add" button of a product not yet in the estimate. Mirrors `ctrl()` at quantity 0. */
function addButton(p: EngineProduct): string {
  return `<button class="add" data-inc="${p.id}" aria-label="Add ${p.name} to estimate">Add</button>`;
}

/** One product row. Mirrors `rowHTML()`. */
function rowHTML(p: EngineProduct, currency: string): string {
  return `<div class="row"><div class="nm">${p.name}<small>per ${p.unit}</small></div><div class="pr">${money(p.price, currency)}</div>${addButton(p)}</div>`;
}

/** One category: heading (h3), optional subgroup headings (h4), then rows. Mirrors `sec()`. */
function sectionHTML(category: string, list: EngineProduct[], currency: string): string {
  const subgroups = [...new Set(list.map((p) => p.sub || ""))];
  const body = subgroups
    .map(
      (sub) =>
        (sub ? `<h4>${sub}</h4>` : "") +
        list
          .filter((p) => (p.sub || "") === sub)
          .map((p) => rowHTML(p, currency))
          .join(""),
    )
    .join("");
  return `<section><h3>${ICON[category] || ""}${category}</h3>${body}</section>`;
}

/** The category tabs, first one selected. Mirrors `renderTabs()` on first load. */
export function tabsHTML(P: EngineProduct[]): string {
  const cats = categories(P);
  return cats.map((c) => `<button data-cat="${c}" aria-pressed="${c === cats[0]}">${c}</button>`).join("");
}

/** The whole price list, one swipeable slide per category. Mirrors `renderList()` with no search. */
export function listHTML(P: EngineProduct[], currency: string): string {
  return categories(P)
    .map((g) => `<div class="slide">${sectionHTML(g, P.filter((p) => p.cat === g), currency)}</div>`)
    .join("");
}

/** The two category tiles under the hero. Mirrors the engine's "Category tiles" section. */
export function tilesHTML(P: EngineProduct[]): string {
  const S = 'fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"';
  const bag = `<svg class="ic" viewBox="0 0 48 48" aria-hidden="true"><path d="M13 8h22l5 9v26H8V17z" ${S}/><path d="M8 17h32" ${S}/></svg>`;
  const rodsIcon = `<svg class="ic" viewBox="0 0 48 48" aria-hidden="true"><rect x="5" y="12" width="32" height="8" rx="4" ${S}/><rect x="11" y="22" width="32" height="8" rx="4" ${S}/><rect x="5" y="32" width="32" height="8" rx="4" ${S}/></svg>`;
  const rodSizes = P.filter((p) => p.unit === "30 ft rod")
    .map((p) => p.name.replace("Iron rod ", ""))
    .reverse()
    .join(", ");
  const tiles: [string, string, string, string][] = [
    ["Cement", "Cement", "50 kg bags: " + P.filter((p) => p.cat === "Cement").map((p) => p.name).join(", "), bag],
    ["Iron Rods (Single Piece)", "Iron rods", "By the piece or the ton: " + rodSizes + ", and binding wire", rodsIcon],
  ];
  return tiles
    .map(
      ([c, t, s, i]) =>
        `<a href="#products" data-go="${c}">${i}<div><b>${t}</b><small>${s}</small></div><span class="go" aria-hidden="true">›</span></a>`,
    )
    .join("");
}
