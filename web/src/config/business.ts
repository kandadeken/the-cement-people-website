/* ===========================================================================
   business.ts - The Cement People's business details, in one place
   ---------------------------------------------------------------------------
   Every page, the quotation engine, the WhatsApp links and the search-engine
   information (structured data) read from here. Change a detail once and it
   changes everywhere.

   Rule: only facts the business has confirmed. A detail we do not have yet
   is left as null, and nothing is shown for it. Never fill a gap with a guess.

   An independent copy of the confirmed details lives with the tests in
   ../../../tests/baseline/business.json. The build (scripts/check-data.mjs)
   and the tests both fail if this file and that copy disagree, so a change
   here must be made there too, deliberately, in the same pull request.

   Details below were confirmed by the owner on 11 November 2026.
   =========================================================================== */

export const business = {
  /** Trading name, exactly as written on the logo. */
  name: "The Cement People",

  /** Domain shown to customers, and the full address of the live site. */
  website: "thecementpeople.com",
  siteUrl: "https://thecementpeople.com",

  /** Phone number as customers read it, and in international form for "tap to call". */
  phone: "055 846 3468",
  phoneInternational: "+233558463468",

  /** WhatsApp number in the digits-only form wa.me links need (233 = Ghana). */
  whatsapp: "233558463468",

  /** Email address customers can write to. */
  publicEmail: "sales@thecementpeople.com",

  /** Short location line printed on the PDF quotation header. Unchanged. */
  town: "Kasoa, Ghana",

  /** Physical address. Kasoa is in the Central Region (not Greater Accra). */
  address: {
    street: "Krispol City Road",
    area: "Krispol City",
    locality: "Kasoa",
    region: "Central Region",
    country: "Ghana",
    countryCode: "GH",
  },

  /** How to find the place on the ground. */
  landmark: "Near GOIL Filling Station",

  /** Google Plus Code for the location. (This is NOT a GhanaPost GPS address.) */
  plusCode: "GGMX+F9 Kasoa",

  /** Map position, as shown on the business's Google Maps listing. */
  geo: { latitude: 5.5336575, longitude: -0.4515421 },

  /** Link to the Google Maps listing. */
  mapUrl: "https://maps.app.goo.gl/4SLMLa7DXVrXhDie8",

  /** Opening hours, 24-hour clock. Days not listed in a block are closed. */
  openingHours: [
    {
      days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
      opens: "07:00",
      closes: "17:00",
    },
  ],
  closedDays: ["Sunday"],

  /** Where the business delivers. (Delivery coverage, not the address.) */
  deliveryAreas: ["Kasoa", "Greater Accra"],

  /** Money. taxRate 0 means no tax line appears on estimates. */
  currencyCode: "GHS",
  currencySymbol: "GH₵",
  taxRate: 0,

  // ---- Not provided yet: left empty on purpose ---------------------------
  // Fill these in only with confirmed details.
  ghanaPostGps: null,
  paymentMethods: null,
} as const;
