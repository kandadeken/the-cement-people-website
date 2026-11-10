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

The 41 regression tests in `../tests/` run against both versions of the site
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

## What is deliberately not here yet

- Product rows written into the HTML for search engines (Phase 2).
- Structured data, image descriptions (Phase 2).
- Individual product pages (Phase 3).
- Publishing: GitHub Pages still serves the original `index.html` (Phase 4).
- Accounts, payments, inventory, databases: out of scope for this migration.
