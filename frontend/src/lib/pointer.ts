import type { MouseEvent } from "react";

/**
 * Whether a click came from a mouse, pen or touch: a click the keyboard fires (Enter or
 * Space on a button) has `detail` 0.
 *
 * Use it to release focus after a pointer activation of a control that stays on the
 * page. Left focused, the control shows its :focus-visible ring as soon as any key is
 * pressed (a screenshot shortcut is enough), because browsers count a key press on a
 * focused element as keyboard use. Keyboard activation keeps focus where it is.
 */
export function isPointerClick(event: MouseEvent): boolean {
  return event.detail > 0;
}
