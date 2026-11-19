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
  /** Square product photo (the 360 px file; smaller copies sit beside it). */
  img?: string;
  /** Description of that photo for screen readers. */
  alt?: string;
  /** Rods: the part of the name shown as a bold size tag, e.g. "16 mm". */
  size?: string;
}

/** A product as stored in src/data/products.json. */
interface StoredProduct {
  id: string;
  category: string;
  subgroup?: string;
  name: string;
  unit: string;
  price: number;
  image?: string;
  imageAlt?: string;
  size?: string;
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
    ...(p.image ? { img: p.image, alt: p.imageAlt || "" } : {}),
    ...(p.size ? { size: p.size } : {}),
  }));
}

/** A wide tab photo, from src/data/categories.json. */
export interface Banner { src: string; srcset: string; w: number; h: number }

/** Tab extras in the form the engine uses: {category: {banner?, note?}}. */
export type CategoryInfo = Record<string, { banner?: Banner; note?: string }>;

/** Resolve categories.json ("banner": "rods") into the banner objects themselves. */
export function toCategoryInfo(data: {
  banners: Record<string, Banner>;
  categories: Record<string, { banner?: string; note?: string }>;
}): CategoryInfo {
  const out: CategoryInfo = {};
  for (const [c, info] of Object.entries(data.categories)) {
    out[c] = { note: info.note, banner: info.banner ? data.banners[info.banner] : undefined };
  }
  return out;
}

/** Category names in the order they first appear. Mirrors the engine's `cats`. */
export function categories(P: EngineProduct[]): string[] {
  return [...new Set(P.map((p) => p.cat))];
}

// Small icons shown beside each category heading. Mirrors the engine's `ICON`.
const ICON_CEMENT = `<svg viewBox="0 0 28 28" aria-hidden="true"><path d="M6 5h16l3 5v14H3V10z" fill="currentColor"/><rect x="8" y="12" width="12" height="8" fill="#ff9802"/></svg>`;
const ICON_RODS = `<svg viewBox="0 0 28 28" aria-hidden="true"><rect x="2" y="5" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="12" width="24" height="4" rx="2" fill="currentColor"/><rect x="2" y="19" width="24" height="4" rx="2" fill="currentColor"/><rect x="11" y="3" width="5" height="22" fill="#ff9802"/></svg>`;
const ICON_WIRE = `<svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="10" fill="none" stroke="currentColor" stroke-width="3"/><circle cx="14" cy="14" r="4.5" fill="none" stroke="#ff9802" stroke-width="3"/></svg>`;
const ICON: Record<string, string> = {
  "Cement": ICON_CEMENT,
  "Binding Wire": ICON_WIRE,
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

// Thumbnail sizes. Mirror the engine's THUMB_WIDTHS / THUMB_SIZES exactly.
const THUMB_WIDTHS = [80, 96, 120, 160, 192, 240, 288];
const THUMB_SIZES = "(max-width:560px) 80px, 96px";
/** Every size of one product photo. Mirrors `thumbSrcset()`. */
const thumbSrcset = (src: string) =>
  THUMB_WIDTHS.map((w) => `${src.replace(/\.webp$/, `-${w}.webp`)} ${w}w`).concat(`${src} 360w`).join(", ");
/** The square photo in front of a product name. Mirrors `thumb()`. */
const thumb = (p: EngineProduct) =>
  p.img
    ? `<img class="thumb" src="${p.img}" srcset="${thumbSrcset(p.img)}" sizes="${THUMB_SIZES}" alt="${p.alt || ""}" width="96" height="96">`
    : "";
/** Product name, with a rod's size as a bold tag. Mirrors `label()`. */
const label = (p: EngineProduct) =>
  p.size && p.name.endsWith(p.size)
    ? `<span class="rn">${p.name.slice(0, -p.size.length)}<b class="sz">${p.size}</b></span>`
    : p.name;
/** Width a tab banner is shown at. Mirrors the engine's BANNER_SIZES. */
const BANNER_SIZES = "(min-width:1100px) 652px, (min-width:900px) calc(100vw - 448px), calc(100vw - 32px)";

/** One product row. Mirrors `rowHTML()`. With `shared`, the tab's single
    price is shown once under the heading; the row's own price stays in the
    page for screen readers and search engines but is hidden from view. */
function rowHTML(p: EngineProduct, currency: string, shared = false): string {
  return `<div class="row${p.img ? " has-img" : ""}${shared ? " one" : ""}">${thumb(p)}<div class="nm">${label(p)}<small>per ${p.unit}</small></div><div class="buy"><div class="pr">${shared ? `<span class="vh">${money(p.price, currency)}</span>` : money(p.price, currency)}</div>${addButton(p)}</div></div>`;
}

/** The product whose price the whole tab shares (same price and unit for
    every item, and more than one item), or null. Mirrors `sharedPrice()`. */
function sharedPrice(list: EngineProduct[]): EngineProduct | null {
  return list.length > 1 && list.every((p) => p.price === list[0].price && p.unit === list[0].unit) ? list[0] : null;
}

/** Category arrows in each heading (18 Nov 2026). Mirrors the engine's
    `navHTML()`: previous / next category buttons, disabled at the ends. */
const ARR_L = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ARR_R = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
function catName(c: string): string {
  const [l, s] = TAB_LABEL[c] || [c, ""];
  return s ? `${l}, ${s.toLowerCase()}` : l;
}
function navHTML(cats: string[], g: string): string {
  const i = cats.indexOf(g), a = cats[i - 1], z = cats[i + 1];
  return (
    `<span class="snav">` +
    (a
      ? `<button type="button" class="sgo" data-go="${a}" aria-label="Previous category: ${catName(a)}">${ARR_L}</button>`
      : `<button type="button" class="sgo" disabled aria-label="Previous category">${ARR_L}</button>`) +
    (z
      ? `<button type="button" class="sgo" data-go="${z}" aria-label="Next category: ${catName(z)}">${ARR_R}</button>`
      : `<button type="button" class="sgo" disabled aria-label="Next category">${ARR_R}</button>`) +
    `</span>`
  );
}

/** One category: optional banner, heading (h3) with its arrows, optional
    note, optional subgroup headings (h4), then rows. Mirrors `sec()` while
    browsing. */
function sectionHTML(category: string, list: EngineProduct[], currency: string, info: CategoryInfo, cats: string[]): string {
  const subgroups = [...new Set(list.map((p) => p.sub || ""))];
  const extra = info[category] || {};
  const b = extra.banner;
  const one = sharedPrice(list);
  const body = subgroups
    .map(
      (sub) =>
        (sub ? `<h4>${sub}</h4>` : "") +
        list
          .filter((p) => (p.sub || "") === sub)
          .map((p) => rowHTML(p, currency, !!one))
          .join(""),
    )
    .join("");
  return (
    `<section>` +
    (b
      ? `<img class="banner" src="${b.src}" srcset="${b.srcset}" sizes="${BANNER_SIZES}" alt="" width="${b.w}" height="${b.h}" fetchpriority="low" onerror="this.closest('section').classList.add('nobanner')">`
      : "") +
    `<h3>${ICON[category] || ""}${category}${navHTML(cats, category)}</h3>` +
    (extra.note ? `<p class="cat-note">${extra.note}</p>` : "") +
    (one ? `<p class="cat-price"><b>${money(one.price, currency)}</b> per ${one.unit}, all sizes</p>` : "") +
    `${body}</section>`
  );
}

/** The category tabs, first one selected. Mirrors `renderTabs()` on first load. */
/** Tile labels: material and how it is sold (17 Nov 2026). Mirrors TAB_LABEL. */
const TAB_LABEL: Record<string, [string, string]> = {
  "Cement": ["Cement", "Bags"],
  "Iron Rods (Single Piece)": ["Iron rods", "Single pieces"],
  "Iron Rods (Per Ton)": ["Iron rods", "Per ton"],
  "Binding Wire": ["Binding wire", "Rolls"],
};
function tabHTML(c: string, i: number, on: boolean): string {
  const [l, s] = TAB_LABEL[c] || [c, ""];
  return `<button data-cat="${c}" aria-pressed="${on}"><span class="tno">${String(i + 1).padStart(2, "0")}</span><b>${l}</b>${s ? `<small>${s}</small>` : ""}</button>`;
}
export function tabsHTML(P: EngineProduct[]): string {
  const cats = categories(P);
  return cats.map((c, i) => tabHTML(c, i, c === cats[0])).join("");
}

/** The whole price list, one swipeable slide per category. Mirrors `renderList()` with no search. */
export function listHTML(P: EngineProduct[], currency: string, info: CategoryInfo = {}): string {
  const cats = categories(P);
  return cats
    .map((g) => `<div class="slide">${sectionHTML(g, P.filter((p) => p.cat === g), currency, info, cats)}</div>`)
    .join("");
}

