/**
 * Landing-page copy, kept in one place. House rules: describe what the product does,
 * plainly; no invented customers, logos, testimonials or statistics; the goals are
 * labelled targets, not results.
 */
import type { ComponentType } from "react";

import { ForecastIcon, MarketIcon, PlanningIcon } from "../../components/brand/icons";

export const SECTIONS = [
  { id: "what-we-do", label: "What we do" },
  { id: "how-it-works", label: "How it works" },
  { id: "our-goals", label: "Our goals" },
] as const;

export const SERVICES: Array<{
  title: string;
  body: string;
  Icon: ComponentType<{ className?: string }>;
}> = [
  {
    title: "Demand Forecasting",
    body: "Weekly forecasts for every product, region and channel, 1 to 26 weeks ahead, each with a confidence range instead of a single guess.",
    Icon: ForecastIcon,
  },
  {
    title: "Production Planning",
    body: "Turns the forecast into a production plan that respects line capacity, changeover time and safety stock.",
    Icon: PlanningIcon,
  },
  {
    title: "Market Intelligence",
    body: "Festivals, promotions and seasonal peaks are flagged weeks ahead, so a spike in demand is planned for, not discovered.",
    Icon: MarketIcon,
  },
];

export const STEPS = [
  {
    title: "Connect your sales history",
    body: "Upload daily sales by product, region and channel, or let Meridian roll them up from your orders.",
  },
  {
    title: "Blend in market signals",
    body: "Holidays, festivals, promotions and seasonality become signals the forecast can learn from.",
  },
  {
    title: "Forecast with confidence intervals",
    body: "Every forecast comes with a range, so you can see how sure it is and plan for the high end when it matters.",
  },
  {
    title: "Plan production",
    body: "Turn the forecast into line-by-line production, with capacity and safety stock built in.",
  },
];

// Targets against a seasonal-naive baseline (a forecast that repeats the same week last
// year). Deliberately conservative, and never presented as achieved.
export const GOALS = [
  {
    figure: "−15%",
    title: "Forecast error",
    body: "15% lower forecast error than the seasonal-naive baseline.",
  },
  {
    figure: "−20%",
    title: "Stockout days",
    body: "20% fewer days out of stock than planning from the seasonal-naive baseline.",
  },
  {
    figure: "−12%",
    title: "Excess inventory",
    body: "12% less stock held above safety level than planning from the seasonal-naive baseline.",
  },
];

export const FOOTER_COLUMNS: Array<{
  title: string;
  links: Array<{ label: string; to?: string; href?: string }>;
}> = [
  {
    title: "Platform",
    links: SECTIONS.map(({ id, label }) => ({ label, href: `/#${id}` })),
  },
  {
    title: "Account",
    links: [
      { label: "Sign in", to: "/login" },
      { label: "Dashboard", to: "/app/dashboard" },
    ],
  },
  {
    title: "Developers",
    links: [{ label: "API reference", href: "/docs" }],
  },
];
