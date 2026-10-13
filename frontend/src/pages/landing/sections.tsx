import type { ReactNode } from "react";

import { ForecastArt } from "../../components/brand/ForecastArt";
import { Reveal } from "../../components/Reveal";
import { ButtonLink } from "../../components/ui/ButtonLink";
import { Card } from "../../components/ui/Card";
import { cn } from "../../lib/cn";
import { GOALS, SERVICES, STEPS } from "./content";

// Siblings in a row reveal one after another.
const STAGGER = [undefined, cn("delay-100"), cn("delay-200"), cn("delay-300")];

function Section({
  id,
  eyebrow,
  title,
  intro,
  muted = false,
  children,
}: {
  id: string;
  eyebrow?: ReactNode;
  title: string;
  intro: ReactNode;
  muted?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn(
        "scroll-mt-16 py-20 lg:py-24",
        muted && "border-y border-line bg-surface-muted",
      )}
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <Reveal className="max-w-2xl space-y-4">
          {eyebrow}
          <h2 id={`${id}-title`} className="text-step-4">
            {title}
          </h2>
          <p className="text-step-1 text-fg-muted">{intro}</p>
        </Reveal>
        <div className="mt-12">{children}</div>
      </div>
    </section>
  );
}

export function Hero() {
  return (
    <section id="top" className="scroll-mt-16">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-16 pb-20 sm:px-6 lg:grid-cols-12 lg:gap-12 lg:px-8 lg:pt-24 lg:pb-24">
        <Reveal className="space-y-6 lg:col-span-7">
          <p className="text-step-n1 font-medium tracking-wide text-primary uppercase">
            Demand forecasting for manufacturers
          </p>
          <h1 className="text-step-6 tracking-tight">
            Plan production around the demand that’s coming.
          </h1>
          <p className="max-w-xl text-step-1 text-fg-muted">
            Meridian turns your sales history and market signals into weekly demand forecasts with
            honest confidence ranges, then into a production plan you can act on.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <ButtonLink to="/login">Sign in</ButtonLink>
            <ButtonLink href="#how-it-works" variant="ghost">
              See how it works
            </ButtonLink>
          </div>
        </Reveal>
        <Reveal className="mx-auto w-full max-w-xl delay-100 lg:col-span-5 lg:max-w-none">
          <ForecastArt className="w-full" />
        </Reveal>
      </div>
    </section>
  );
}

export function WhatWeDo() {
  return (
    <Section
      id="what-we-do"
      title="What we do"
      intro="Three jobs, done in the open: every number comes with the range it could fall in."
    >
      <ul role="list" className="grid gap-6 md:grid-cols-3">
        {SERVICES.map(({ title, body, Icon }, i) => (
          <li key={title}>
            <Reveal className={cn("h-full", STAGGER[i])}>
              <Card className="hover-lift h-full space-y-4">
                <span className="inline-flex size-10 items-center justify-center rounded-control bg-primary-subtle text-primary">
                  <Icon />
                </span>
                <h3 className="text-step-2">{title}</h3>
                <p className="text-fg-muted">{body}</p>
              </Card>
            </Reveal>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function HowItWorks() {
  return (
    <Section
      id="how-it-works"
      muted
      title="How it works"
      intro="Four steps from the sales you already have to a plan you can run."
    >
      {/* Phones: a vertical line down through the markers. md and up: a horizontal one. */}
      <ol className="md:grid md:grid-cols-4">
        {STEPS.map(({ title, body }, i) => {
          const last = i === STEPS.length - 1;
          return (
            <li key={title} className={cn("relative", last ? "pb-0" : "pb-10 md:pb-0")}>
              {!last && (
                <span
                  aria-hidden="true"
                  className="absolute top-10 bottom-0 left-5 w-px bg-primary md:hidden"
                />
              )}
              {/* items-start: the marker sits at the top, where the vertical line begins. */}
              <Reveal className={cn("flex items-start gap-4 md:block", STAGGER[i])}>
                <div className="flex items-center md:mb-6">
                  <span className="figure flex size-10 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-surface-muted text-step-n1 font-semibold text-primary">
                    {i + 1}
                  </span>
                  {!last && (
                    <span
                      aria-hidden="true"
                      className="ml-3 hidden h-px flex-1 bg-primary md:block"
                    />
                  )}
                </div>
                <div className="space-y-2 pt-2 md:pt-0 md:pr-6">
                  <h3 className="text-step-1">{title}</h3>
                  <p className="text-fg-muted">{body}</p>
                </div>
              </Reveal>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

export function OurGoals() {
  return (
    <Section
      id="our-goals"
      eyebrow={
        <p className="inline-flex rounded-full border border-line-strong px-3 py-1 text-step-n1 font-medium text-fg">
          Target outcomes, not results achieved
        </p>
      }
      title="Our goals"
      intro="These are the outcomes we are building toward, each measured against a seasonal-naive baseline: a forecast that simply repeats the same week last year. We have not achieved them yet, and we have no customers to quote."
    >
      <ul role="list" className="grid gap-6 md:grid-cols-3">
        {GOALS.map(({ figure, title, body }, i) => (
          <li key={title}>
            <Reveal className={cn("h-full", STAGGER[i])}>
              <div className="h-full rounded-card border border-line bg-surface p-6">
                <p className="text-step-n2 font-semibold tracking-wide text-primary uppercase">
                  Target
                </p>
                <p className="figure mt-3 text-step-6 font-semibold text-fg">{figure}</p>
                <h3 className="mt-3 text-step-2">{title}</h3>
                <p className="mt-2 text-fg-muted">{body}</p>
              </div>
            </Reveal>
          </li>
        ))}
      </ul>
    </Section>
  );
}
