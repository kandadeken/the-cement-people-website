# Product images: full-size originals

These are the master copies of the product pictures. The four cement bags were
regenerated on 12 November 2026 with OpenAI's Sunburst image model
(gpt-image-2.6-sunburst), using each manufacturer's official product photo as
the design reference. They are PNG, 1024 × 1024 pixels, 1.2 to 1.4 MB each,
exactly as downloaded from the OpenAI playground (bag on a white background). Binding wire and iron rods are still the ChatGPT originals
(PNG, about 2172 × 724 pixels).
They are kept here so a better crop or a new size can always be made from the
best available version. This folder is **not published** on the website
(see `_config.yml`).

The website uses the small optimised copies in `images/products/` instead:

| Original (here) | Used on the site | What was done |
| --- | --- | --- |
| `supacem-32-5.png` | `images/products/supacem-32-5.webp` | square crop of the bag, 360 × 360, WebP |
| `supacem-42-5.png` | `images/products/supacem-42-5.webp` | square crop of the bag, 360 × 360, WebP |
| `dzata-42-5.png` | `images/products/dzata-42-5.webp` | square crop of the bag, 360 × 360, WebP |
| `ghacem-waterproof-42-5.png` | `images/products/ghacem-waterproof-42-5.webp` | square crop of the bag, 360 × 360, WebP |
| `binding-wire.png` | `images/products/binding-wire.webp` | square crop of the coil, 360 × 360, WebP |

### Smaller copies for the price list thumbnails

The price list shows the thumbnails at 96 × 96 px on computers and tablets and
80 × 80 px on phones. Each thumbnail also exists in smaller copies, named with
the width added: `supacem-32-5-80.webp`, `-96`, `-120`, `-160`, `-192`, `-240`
and `-288` (the 360 px file without a number stays as the fallback). The
browser downloads the smallest copy that is still sharp on the visitor's screen,
for example `-120` on a PC with 125% display scaling and `-240` on a typical
phone.

How they were made (12 November 2026), so they can be remade the same way:

- **Cement bags:** from the 1024 × 1024 masters in this folder. The square crop
  is the one used for the 360 px file: the bag and its shadow (every pixel darker
  than 215 in any colour channel), plus 5%, centred. Each size is a Lanczos
  shrink of that crop, saved as WebP quality 86 (method 6).
- **Binding wire:** from the approved 360 px `images/products/binding-wire.webp`,
  because its exact crop from `binding-wire.png` could not be reproduced. The
  copies are only ever smaller than 360 px, so nothing is enlarged.
| `iron-rods.png` | `images/products/iron-rods-720.webp`, `-1086.webp`, `-1440.webp` | whole image at three widths (720, 1086, 1440 px), WebP quality 82; one shared photo for both rod tabs, labelled only "8 mm to 16 mm \| 30 ft length" |

## The Sunburst cement bags

| Bag | Design reference used |
| --- | --- |
| Supacem Supa Fast 32.5R | CBI Ghana product photo (cbighana.com) |
| Supacem Supa Power 42.5R | CBI Ghana product photo (cbighana.com) |
| Dzata 42.5R | Dzata Cement product photo (dzatacement.com) |
| Ghacem Super Strong Waterproof 42.5N | Ghacem product image (ghacem.com) |

All four were generated at Medium quality, one attempt each. All the main
packaging text is correct. Known small differences from the real bags, too
small to read at the size the website shows them:

- Supa Fast: the small leaf badge reads "ECO-FRIENDLY PRODUCTION" (the real bag says "INNOVATION").
- Supa Power: the vertical "SUPA POWER" text sits on the front edge rather than on the side panel.
- Ghacem: the tiny vertical text on the blue side strip garbles "CEMENT".
- Dzata: the lion is drawn slightly differently from Dzata's official artwork.

## Important

The cement bags are AI reconstructions based on reference photos, not
manufacturer photographs. Small details on the packaging may differ from the
real bags. Replace them with real photos of the stock when available: put the
new original here, make the square WebP copy with the same file name in
`images/products/`, and nothing else needs to change.
