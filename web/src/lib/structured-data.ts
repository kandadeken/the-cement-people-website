/* ===========================================================================
   structured-data.ts - describes the business to search engines (JSON-LD)
   ---------------------------------------------------------------------------
   Search engines and AI tools read a block of "structured data" in the page
   to learn, without guessing: who the business is, where it is, when it is
   open, how to contact it and where it delivers. This file builds that block
   in the Schema.org vocabulary, using ONLY the details in business.ts.

   Three linked descriptions are produced:
     Store    the business itself (a shop that sells building materials)
     WebSite  the website, published by the Store
     WebPage  this page, part of the WebSite and about the Store

   Deliberately NOT included, because nothing confirmed supports them yet:
   ratings, reviews, individual products, prices or stock. Product details
   belong on product pages (Phase 3). Details that are null in business.ts
   are left out rather than guessed.

   tests/test_seo.py checks every value here against the independent
   reference copy in tests/baseline/business.json.
   =========================================================================== */
import { business } from "../config/business";

interface PageInfo {
  /** Page title, as in the <title> tag. */
  title: string;
  /** Page description, as in the meta description. */
  description: string;
  /** Full address of this page. */
  url: string;
  /** Full address of the picture that represents the page. */
  image: string;
}

/** Build the structured data for one page. Returns an object ready for JSON.stringify. */
export function buildStructuredData(page: PageInfo) {
  const site = business.siteUrl;
  // Permanent names for each description, so they can point at each other.
  const storeId = `${site}/#store`;
  const websiteId = `${site}/#website`;
  const webpageId = `${page.url}#webpage`;
  const logoUrl = `${site}/images/logo.svg`;

  const store = {
    "@type": "Store",
    "@id": storeId,
    name: business.name,
    url: `${site}/`,
    description: page.description,
    logo: logoUrl,
    image: page.image,
    telephone: business.phoneInternational,
    email: business.publicEmail,
    address: {
      "@type": "PostalAddress",
      streetAddress: `${business.address.street}, ${business.address.area}`,
      addressLocality: business.address.locality,
      addressRegion: business.address.region,
      addressCountry: business.address.countryCode,
    },
    geo: {
      "@type": "GeoCoordinates",
      latitude: business.geo.latitude,
      longitude: business.geo.longitude,
    },
    hasMap: business.mapUrl,
    openingHoursSpecification: business.openingHours.map((block) => ({
      "@type": "OpeningHoursSpecification",
      dayOfWeek: [...block.days],
      opens: block.opens,
      closes: block.closes,
    })),
    // Where the business delivers (not where it is located).
    areaServed: business.deliveryAreas.map((name) => ({ "@type": "Place", name })),
    currenciesAccepted: business.currencyCode,
  };

  const website = {
    "@type": "WebSite",
    "@id": websiteId,
    url: `${site}/`,
    name: business.name,
    inLanguage: "en",
    publisher: { "@id": storeId },
  };

  const webpage = {
    "@type": "WebPage",
    "@id": webpageId,
    url: page.url,
    name: page.title,
    description: page.description,
    inLanguage: "en",
    isPartOf: { "@id": websiteId },
    about: { "@id": storeId },
    primaryImageOfPage: { "@type": "ImageObject", url: page.image },
  };

  return { "@context": "https://schema.org", "@graph": [store, website, webpage] };
}
