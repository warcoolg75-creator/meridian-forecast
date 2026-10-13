import { useState } from "react";

import { MenuIcon } from "../../components/brand/icons";
import { Wordmark } from "../../components/brand/Wordmark";
import { ButtonLink } from "../../components/ui/ButtonLink";
import { SECTIONS } from "./content";

/** Sticky, slim. Below md the section links fold into a menu; Sign in stays visible. */
export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-canvas/90 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4 sm:px-6 lg:px-8">
        <a href="#top" aria-label="Meridian, back to top">
          <Wordmark />
        </a>
        <nav aria-label="Sections" className="hidden items-center gap-8 md:flex">
          {SECTIONS.map(({ id, label }) => (
            <a
              key={id}
              href={`#${id}`}
              className="text-step-n1 text-fg-muted transition-colors hover:text-primary"
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <ButtonLink to="/login" size="sm">
            Sign in
          </ButtonLink>
          <button
            type="button"
            aria-expanded={open}
            aria-controls="mobile-sections"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
            className="inline-flex size-8 items-center justify-center rounded-control text-fg hover:bg-surface-muted md:hidden"
          >
            <MenuIcon open={open} className="size-5" />
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-sections" aria-label="Sections" className="border-t border-line md:hidden">
          <ul className="mx-auto max-w-6xl px-4 py-2 sm:px-6">
            {SECTIONS.map(({ id, label }) => (
              <li key={id}>
                <a href={`#${id}`} onClick={() => setOpen(false)} className="block py-3 text-fg">
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}
