# The Cement People website (Astro version)

This folder is the new foundation for thecementpeople.com, built with
[Astro](https://astro.build). It produces a plain static website: HTML, CSS,
images and one script. No server, database or paid service is needed.

> **Status (Phase 1):** not live. The live site is still the single file
> `index.html` at the top of the repository, published by GitHub Pages from
> `main`. Nothing in `web/` is published until the switch-over (Phase 4) is
> approved. This version is designed to look and behave identically.

## How it fits together

```
web/
├─ astro.config.mjs          Astro settings (site address, static output)
├─ package.json              one dependency: astro (exact version, pinned)
├─ scripts/check-data.mjs    safety checks run before every build
├─ public/                   copied to the website exactly as-is
│  ├─ scripts/quote-engine.js   the quotation engine (see below)
│  ├─ images/                   hero photos
│  ├─ robots.txt                tells search engines they may read the site
│  └─ CNAME                     the custom domain, for when this goes live
└─ src/
   ├─ data/products.json     the 17 products: the price list's source of truth
   ├─ config/business.ts     name, phone, WhatsApp, location, currency, tax
   ├─ styles/                tokens.css (brand colours), site.css (screen),
   │                         print.css (the A4 PDF quotation)
   ├─ layouts/Base.astro     page shell: <head>, title, description, canonical
   │                         address, link previews, fonts, stylesheets
   ├─ components/            Header, Hero, Catalog, EstimatePanel, About,
   │                         Contact, Footer, QuotePieces, Logo, WhatsAppIcon
   └─ pages/
      ├─ index.astro         the home page, assembled from the components
      └─ sitemap.xml.ts      builds /sitemap.xml
```

### Where things are decided

| To change… | Edit |
| --- | --- |
| A price, product name or unit | `src/data/products.json` **and** `../tests/baseline/products.json` (the build refuses to run if they differ) |
| Phone, WhatsApp, location | `src/config/business.ts` (and the footer line in `src/styles/print.css`; the build checks they match) |
| Brand colours | `src/styles/tokens.css` |
| Page wording | the component in `src/components/` |

### The quotation engine

`public/scripts/quote-engine.js` is the original site's script, moved here
with comments added. Its logic is unchanged. It draws the price list, runs
the estimate, writes the WhatsApp message and fills in the printable A4
quotation.

It sits in `public/` rather than `src/` on purpose. Astro repackages scripts
in `src/` into "modules", which would hide variables such as the product list
`P` from the rest of the page. Files in `public/` are copied untouched, and
the page loads the engine as an ordinary script:

```html
<script is:inline type="application/json" id="tcp-data">…products and business details…</script>
<script is:inline src="/scripts/quote-engine.js"></script>
```

The only change to the engine is how it gets its data. It used to have the
products and phone number typed into it; it now reads them from the
`tcp-data` block, which Astro builds from `products.json` and `business.ts`.

## Running it on your own computer

You need [Node.js](https://nodejs.org) 22.23.4 or newer.

```bash
cd web
npm ci            # install the exact Astro version in package-lock.json
npm run dev       # live preview at http://localhost:4321 while editing
npm run build     # check the data, then build the website into web/dist/
npm run preview   # serve the built website at http://localhost:4321
```

## Testing

The regression tests in `../tests/` (48 at the time of the product images
change; the 6 product-image browser checks are skipped for this build until
it is carried over) run against both versions of the site
on every pull request (see `../.github/workflows/tests.yml`):

- **Original site:** the tests open `../index.html` directly.
- **Astro build:** GitHub builds `web/`, serves `web/dist/` from a local web
  server, and runs the same tests against it with
  `TCP_SITE_URL=http://127.0.0.1:4321/`.

To run the Astro check yourself, from the top of the repository:

```bash
(cd web && npm ci && npm run build)
python -m http.server 4321 --bind 127.0.0.1 --directory web/dist &
TCP_SITE_URL=http://127.0.0.1:4321/ python -m pytest tests -v
```

The built site must be served, not opened as a file: its pages load
stylesheets from `/_astro/…` addresses, which only work through a web server.

## Product images: carry over before the switch-over

Added to the **live** site (`../index.html`) on the `product-images` branch,
before the switch-over. This Astro version does not have it yet. It must be
carried over before Phase 4 so the switch-over doesn't remove it. Until then,
the browser checks in `../tests/test_product_images.py` are skipped when the
tests run against this build (they detect the local address
`http://127.0.0.1:4321`); remove that skip once this is done.

### Assets

| File (in `../images/products/`) | Used for | Size |
| --- | --- | --- |
| `supacem-32-5.webp` | Supacem 32.5 row (c1) | 360 × 360 |
| `supacem-42-5.webp` | Supacem 42.5 row (c2) | 360 × 360 |
| `dzata-42-5.webp` | Dzata 42.5 row (c3) | 360 × 360 |
| `ghacem-waterproof-42-5.webp` | Ghacem Waterproof 42.5 row (c4) | 360 × 360 |
| `binding-wire.webp` | Binding wire row (i8) | 360 × 360 |
| `iron-rods-720.webp` | shared rod photo, phones | 720 × 240 (~18 KB) |
| `iron-rods-1086.webp` | shared rod photo, default / mid-size screens | 1086 × 362 (~35 KB) |
| `iron-rods-1440.webp` | shared rod photo, sharp screens | 1440 × 480 (~55 KB) |

The rod photo shows "Iron Rods, 8 mm to 16 mm, 30 ft length" and is the same
for both rod tabs. How each tab is sold is page text, not part of the image.

Full-size originals are in `../design/product-originals/` (not published).
For Astro, copy the eight WebP files to `public/images/products/` so the paths
stay `/images/products/...`.

### Product data

Three optional fields were added to each product (in `index.html` these sit
in the `P` list; here they belong in `src/data/products.json`):

- `img`: path of the square photo, e.g. `images/products/dzata-42-5.webp`
- `alt`: short description of the photo for screen readers
- `size`: for iron rods, the part of the name shown as a bold tag (`"16 mm"`)

and per-tab extras:

```js
const ROD_PHOTO = {
  src: "images/products/iron-rods-1086.webp",
  srcset: "…720.webp 720w, …1086.webp 1086w, …1440.webp 1440w",
  w: 1086, h: 362
};
const CAT_INFO = {
  "Iron Rods (Single Piece)": {banner: ROD_PHOTO, note: "Sold by the piece. Each rod is 30 ft long."},
  "Iron Rods (Per Ton)":      {banner: ROD_PHOTO, note: "Sold by the ton, in each size."}
};
const BANNER_SIZES = "(min-width:1100px) 652px, (min-width:900px) calc(100vw - 448px), calc(100vw - 32px)";
```

`tests/baseline/products.json` does not need these fields: the tests still
compare only id, category, name, unit and price. Keep `check-data.mjs`
ignoring them.

### Layout rules

1. **Photo rows.** A product with `img` gets a 64 × 64 thumbnail in front of
   the name (`<img class="thumb" width="64" height="64">`, loaded straight
   away, not lazily: the cement photos are on the first screen). On phones
   (560 px and narrower) the thumbnail sits on the left across two lines; the
   name on the first line, price and Add/quantity on the second.
2. **Rod tabs.** When browsing the tabs, a tab with a `banner` shows, in this
   order: the shared rod photo, the normal visible `<h2>` with the exact
   category text, then the `note` as a `<p class="cat-note">`. The photo has
   `alt=""` because the heading and note say the same. Search results show
   the heading and note but no photo.
3. **Loading.** The photo uses `srcset` and `sizes` (above), so a phone
   downloads the 720 px copy and a large sharp screen the 1440 px copy. It is
   not lazy: it loads with the page with `fetchpriority="low"`, so it is
   ready before a customer opens a rod tab without slowing the first screen.
   Both tabs use the same file, so it is downloaded once.
4. **Fallback.** If the photo fails to load, the section gets the class
   `nobanner` and the photo is hidden; the heading is always visible.
5. **Rod size tags.** For products with `size`, the name is written as
   `<span class="rn">Iron rod <b class="sz">16 mm</b></span>`. CSS
   (`order:-1`) moves the bold black tag to the front, so it reads
   "**16 mm** Iron rod" on screen, while the text in the page is still
   "Iron rod 16 mm". The estimate, PDF and WhatsApp message use `name` and
   are unchanged.
6. **Width on phones.** The photo has `max-width:100%` and the price-list
   column (`#catalog`) has `min-width:0`; without these the photo's built-in
   size widened the page on phones once the Montserrat font loaded.
7. **Height.** The price list re-measures its height when any image loads or
   fails, so the swipeable tabs never cut a row off.

The CSS is in the block marked "Product images" in `../index.html`; the
rendering is in the `thumb`, `label`, `rowHTML` and `sec` functions there.
In Astro, the rendering belongs in `public/scripts/quote-engine.js` (it draws
the price list) and the CSS in `src/styles/site.css`.

## What is deliberately not here yet

- Product rows written into the HTML for search engines (Phase 2).
- Structured data, image descriptions (Phase 2).
- Individual product pages (Phase 3).
- Publishing: GitHub Pages still serves the original `index.html` (Phase 4).
- Accounts, payments, inventory, databases: out of scope for this migration.
