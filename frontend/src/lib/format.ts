/**
 * Formatting for numbers shown as data. Indian grouping (12,34,567) and compact units
 * (12K, 1.2L, 3.4Cr), because the planners and the money (paise) are Indian.
 */

const integer = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
// Three significant digits, so an axis tick at 2,250 reads "2.25K", not a rounded "2.3K".
const compact = new Intl.NumberFormat("en-IN", {
  notation: "compact",
  maximumSignificantDigits: 3,
});
const signedPercent = new Intl.NumberFormat("en-IN", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});
const percent = new Intl.NumberFormat("en-IN", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const rupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const compactRupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumSignificantDigits: 3,
});

/** 1234567 -> "12,34,567" */
export function formatInteger(value: number): string {
  return integer.format(value);
}

/** 1234567 -> "12.3L", 2250 -> "2.25K": axis ticks and other tight spots. */
export function formatCompact(value: number): string {
  return compact.format(value);
}

/** A fraction as a signed percentage: 0.062 -> "+6.2%", 0 -> "0.0%". */
export function formatSignedPercent(fraction: number): string {
  return signedPercent.format(fraction);
}

/** A fraction as a percentage: 0.062 -> "6.2%". */
export function formatPercent(fraction: number): string {
  return percent.format(fraction);
}

/** Money is stored in minor units (paise): 84732000 -> "₹8,47,320". */
export function formatRupees(minor: number): string {
  return rupees.format(minor / 100);
}

/** 84732000 paise -> "₹8.47L". */
export function formatCompactRupees(minor: number): string {
  return compactRupees.format(minor / 100);
}

/** A readable message for whatever a failed request or render threw. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error) return error;
  return "Something went wrong.";
}
