/* ===========================================================================
   business.ts - The Cement People's business details, in one place
   ---------------------------------------------------------------------------
   Every page, the quotation engine, the WhatsApp links and the search-engine
   information read from here. Change a detail once and it changes everywhere.

   Rule: only facts the business has confirmed. A detail we do not have yet
   is left as null, and nothing is shown for it. Never fill a gap with a guess.
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

  /** Location as currently published. */
  town: "Kasoa, Ghana",

  /** Money. TAX_RATE 0 means no tax line appears on estimates. */
  currencyCode: "GHS",
  currencySymbol: "GH₵",
  taxRate: 0,

  // ---- Not provided yet: left empty on purpose ---------------------------
  // Fill these in only with confirmed details. Pages will start showing them
  // in a later phase; until then they have no effect.
  streetAddress: null,
  mapLocation: null,
  openingHours: null,
  publicEmail: null,
  deliveryAreas: null,
  paymentMethods: null,
} as const;
