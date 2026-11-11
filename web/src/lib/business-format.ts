/* ===========================================================================
   business-format.ts - turns the details in business.ts into display text
   ---------------------------------------------------------------------------
   Small helpers so every component writes the address and opening hours the
   same way. They only rearrange confirmed details; they add nothing.
   =========================================================================== */
import { business } from "../config/business";

/** "Krispol City Road, Krispol City, Kasoa, Central Region, Ghana" */
export function addressLine(): string {
  const a = business.address;
  return [a.street, a.area, a.locality, a.region, a.country].join(", ");
}

/** "07:00" -> "7:00 am", "17:00" -> "5:00 pm" */
function clock(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const suffix = h < 12 ? "am" : "pm";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${String(m).padStart(2, "0")} ${suffix}`;
}

/** "Monday–Saturday, 7:00 am–5:00 pm" (one entry per block of opening hours) */
export function openingHoursLines(): string[] {
  return business.openingHours.map((block) => {
    const first = block.days[0];
    const last = block.days[block.days.length - 1];
    const days = first === last ? first : `${first}–${last}`;
    return `${days}, ${clock(block.opens)}–${clock(block.closes)}`;
  });
}

/** "Sunday closed" (empty when there are no closed days) */
export function closedLine(): string {
  return business.closedDays.length ? `${business.closedDays.join(", ")} closed` : "";
}

/** "Kasoa and Greater Accra" */
export function deliveryAreasLine(): string {
  const areas = [...business.deliveryAreas];
  if (areas.length <= 1) return areas.join("");
  return `${areas.slice(0, -1).join(", ")} and ${areas[areas.length - 1]}`;
}
