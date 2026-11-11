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

The regression tests in `../tests/` (47 at the time of the product images
change; the 5 product-image browser checks are skipped for this build until
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
| `iron-rods-single-piece.webp` | banner for the "Iron Rods (Single Piece)" tab | 1086 × 362 |
| `iron-rods-per-ton.webp` | banner for the "Iron Rods (Per Ton)" tab | 1086 × 362 |

Full-size originals are in `../design/product-originals/` (not published).
For Astro, copy the seven WebP files to `public/images/products/` so the paths
stay `/images/products/...`.

### Product data

Three optional fields were added to each product (in `index.html` these sit
in the `P` list; here they belong in `src/data/products.json`):

- `img`: path of the square photo, e.g. `images/products/dzata-42-5.webp`
- `alt`: short description of the photo for screen readers
- `size`: for iron rods, the part of the name shown as a bold tag (`"16 mm"`)

and one map from tab name to banner image:

```js
const BANNER = {
  "Iron Rods (Single Piece)": "images/products/iron-rods-single-piece.webp",
  "Iron Rods (Per Ton)": "images/products/iron-rods-per-ton.webp"
};
```

`tests/baseline/products.json` does not need these fields: the tests still
compare only id, category, name, unit and price. Keep `check-data.mjs`
ignoring them.

### Layout rules

1. **Photo rows.** A product with `img` gets a 64 × 64 thumbnail in front of
   the name (`<img class="thumb" width="64" height="64" loading="lazy">`).
   On phones (560 px and narrower) the thumbnail sits on the left across two
   lines; the name on the first line, price and Add/quantity on the second.
2. **Banner tabs.** When browsing the tabs, a category with a banner shows
   the banner at the top of its section. The real `<h2>` stays first in the
   section, with the exact category text, but is visually hidden (class
   `vh`) because the banner already shows the name. The banner has `alt=""`.
   Search results show the normal visible heading and no banner.
3. **Banner fallback.** If a banner fails to load, the section gets the class
   `nobanner`, the banner is hidden and the heading becomes visible.
4. **Rod size tags.** For products with `size`, the name is written as
   `<span class="rn">Iron rod <b class="sz">16 mm</b></span>`. CSS
   (`order:-1`) moves the bold black tag to the front, so it reads
   "**16 mm** Iron rod" on screen, while the text in the page is still
   "Iron rod 16 mm". The estimate, PDF and WhatsApp message use `name` and
   are unchanged.
5. **Sections are `position:relative`.** Required: without it the visually
   hidden headings in the other tabs push the page wider than a phone screen.
6. **Height.** The price list re-measures its height when any image loads or
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
