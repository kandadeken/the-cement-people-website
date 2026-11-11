# The Cement People website (Astro version)

This folder is the new foundation for thecementpeople.com, built with
[Astro](https://astro.build). It produces a plain static website: HTML, CSS,
images and one script. No server, database or paid service is needed.

> **Status (Phase 2):** not live. The live site is still the single file
> `index.html` at the top of the repository, published by GitHub Pages from
> `main`. Nothing in `web/` is published until the switch-over is approved.
> Phase 1 rebuilt the site to look and behave identically. Phase 2 made it
> readable by search engines and AI tools (see "Search engines" below).

## How it fits together

```
web/
├─ astro.config.mjs          Astro settings (site address, static output)
├─ package.json              one dependency: astro (exact version, pinned)
├─ scripts/check-data.mjs    safety checks run before every build
├─ public/                   copied to the website exactly as-is
│  ├─ scripts/quote-engine.js   the quotation engine (see below)
│  ├─ images/                   hero photos and logo.svg (the reusable logo file)
│  ├─ robots.txt                tells search engines they may read the site
│  └─ CNAME                     the custom domain, for when this goes live
└─ src/
   ├─ data/products.json     the 17 products: the price list's source of truth
   ├─ config/business.ts     name, phone, email, address, hours, delivery areas,
   │                         currency, tax: every business fact, in one place
   ├─ styles/                tokens.css (brand colours), site.css (screen),
   │                         print.css (the A4 PDF quotation)
   ├─ lib/
   │  ├─ catalog-html.ts     writes the price list into the HTML at build time
   │  ├─ structured-data.ts  describes the business to search engines (JSON-LD)
   │  └─ business-format.ts  address and opening hours as display text
   ├─ layouts/Base.astro     page shell: <head>, title, description, canonical
   │                         address, link previews, structured data, fonts
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
| Phone, email, address, opening hours, delivery areas | `src/config/business.ts` **and** `../tests/baseline/business.json` (the build refuses to run if they differ). Phone and website also appear in the PDF footer in `src/styles/print.css`; the build checks they match |
| Page title or description | `src/pages/index.astro` **and** the `page` entry in `../tests/baseline/business.json` |
| Brand colours | `src/styles/tokens.css` |
| Page wording | the component in `src/components/` |

### The quotation engine

`public/scripts/quote-engine.js` is the original site's script, moved here
with comments added. Its calculations are unchanged. It draws the price list, runs
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

## Search engines and AI tools (Phase 2)

- **Products in the HTML.** The category tiles, tabs and all 17 product rows
  are written into the page when the site is built (`src/lib/catalog-html.ts`),
  so they can be read without running any script. The quotation engine redraws
  the same markup when the page loads. A test fails if the two ever differ.
- **Structured data.** `src/lib/structured-data.ts` writes one block describing
  the business (as a Schema.org `Store`), the website and the page, using only
  the facts in `business.ts`. No ratings, reviews, products or prices.
- **Business details on the page.** Address, landmark, Plus Code, opening
  hours, email and delivery coverage appear in the Contact section, and the
  address in the footer, all read from `business.ts`.
- **Headings.** One main heading; in the price list, categories are `<h3>` and
  subgroups `<h4>` under "Products and prices".
- **Images.** The left hero photo has a description; the right one shows the
  same things and is marked decorative so it is not read out twice. Both
  declare their real size.
- **Title.** The brand name only: "The Cement People". Products and location
  are carried by the description, the page text and the structured data.

Two things to remember when editing business details:

- Kasoa is in the **Central Region**. "Greater Accra" is delivery coverage,
  not the address.
- `GGMX+F9 Kasoa` is a Google **Plus Code**, not a GhanaPost GPS address.

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

The regression tests in `../tests/` run against both versions of the site
on every pull request: 41 quotation and catalogue tests on both, plus 13
search-engine tests (`test_seo.py`) on this Astro version (see `../.github/workflows/tests.yml`):

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

## What is deliberately not here yet

- Product markup with prices in structured data (Phase 3, with dated prices).
- Individual product pages (Phase 3).
- Publishing: GitHub Pages still serves the original `index.html` (Phase 4).
- Accounts, payments, inventory, databases: out of scope for this migration.
