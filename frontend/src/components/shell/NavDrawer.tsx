import { useEffect, useRef } from "react";

import { isPointerClick } from "../../lib/pointer";
import { CloseIcon } from "../brand/icons";
import { Wordmark } from "../brand/Wordmark";
import { NavList } from "./NavList";

const WIDE = "(min-width: 48rem)"; // Tailwind's md: from here the sidebar takes over

/**
 * The navigation below 768px: a modal <dialog> that slides in from the left. The dialog
 * traps focus, closes on Escape and hands focus back to the hamburger by itself. It also
 * closes on a backdrop click, on choosing a link, and if the window widens past 768px.
 *
 * Focus opens on the panel itself, not its first control, and a drawer closed with the
 * mouse releases focus instead of leaving it on the hamburger: either control would
 * otherwise show its focus ring at the next key press (see lib/pointer.ts). Closed from
 * the keyboard (Escape, Enter on Close), focus returns to the hamburger as usual.
 */
export function NavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const closedByPointer = useRef(false);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      element.showModal();
      panel.current?.focus();
    }
    if (!open && element.open) {
      element.close(); // hands focus back to the hamburger
      if (closedByPointer.current) (document.activeElement as HTMLElement | null)?.blur();
    }
    closedByPointer.current = false;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const media = window.matchMedia(WIDE);
    const onChange = () => {
      if (media.matches) onClose();
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [open, onClose]);

  return (
    <dialog
      ref={dialog}
      aria-label="Navigation"
      onClose={onClose}
      // The panel fills the dialog, so a click whose target is the dialog itself landed
      // on the backdrop.
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        closedByPointer.current = true;
        onClose();
      }}
      className="fixed inset-y-0 right-auto left-0 m-0 h-full max-h-none w-3xs max-w-full border-0 bg-surface-muted p-0 shadow-overlay slide-over backdrop:bg-scrim"
    >
      <div ref={panel} tabIndex={-1} className="flex h-full flex-col focus-visible:outline-none">
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-line pr-3 pl-5">
          <Wordmark size="sm" />
          <button
            type="button"
            aria-label="Close navigation"
            onClick={(event) => {
              closedByPointer.current = isPointerClick(event);
              onClose();
            }}
            className="inline-flex size-8 items-center justify-center rounded-control text-fg hover:bg-line"
          >
            <CloseIcon className="size-5" />
          </button>
        </div>
        <NavList mode="drawer" onNavigate={onClose} />
      </div>
    </dialog>
  );
}
