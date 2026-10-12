/**
 * Join class names, skipping falsy ones. Named `cn` on purpose: ESLint's Tailwind rules
 * lint the arguments of cn() calls, so class strings kept in variables stay checked.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
