import { NavLink } from "react-router";

import type { RunInfo } from "../../../api/forecast";
import { cn } from "../../../lib/cn";
import { formatDate } from "../../../lib/dates";
import { isPointerClick } from "../../../lib/pointer";
import { modelsPhrase } from "./present";

/** Overview and Model evidence: two views of the same stored forecast. */
export function ForecastTabs() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    cn(
      "rounded-control px-3 py-2 text-step-n1 font-medium",
      isActive ? "bg-surface-muted text-fg" : "text-fg-muted hover:text-fg",
    );
  return (
    <nav aria-label="Forecast views" className="flex gap-2 border-b border-line pb-2">
      <NavLink
        to="/app/forecast"
        end
        className={tab}
        onClick={(e) => isPointerClick(e) && e.currentTarget.blur()}
      >
        Overview
      </NavLink>
      <NavLink
        to="/app/forecast/evidence"
        className={tab}
        onClick={(e) => isPointerClick(e) && e.currentTarget.blur()}
      >
        Model evidence
      </NavLink>
    </nav>
  );
}

/** What the stored run is: which model, the data end, the cutoff and its assumption. */
export function RunFacts({
  run,
  models,
  promotionsAssumed,
  modelText,
}: {
  run: RunInfo;
  models: string[];
  promotionsAssumed: string;
  /** Overrides the model names, e.g. for a short-history SKU. */
  modelText?: string;
}) {
  const facts: [string, string][] = [
    ["Model", modelText ?? modelsPhrase(models)],
    ["Data ends", formatDate(run.data_end_date)],
    ["Trained on weeks up to", `w/c ${formatDate(run.training_cutoff)}`],
    ["Promotions", `Assumes no promotions after ${formatDate(run.data_end_date)}`],
  ];
  return (
    <dl
      className="grid gap-x-8 gap-y-3 text-step-n1 sm:grid-cols-2 xl:grid-cols-4"
      title={`Forecast run ${run.id}: ${promotionsAssumed}`}
    >
      {facts.map(([term, detail]) => (
        <div key={term} className="space-y-1">
          <dt className="text-fg-muted">{term}</dt>
          <dd className="font-medium text-fg">{detail}</dd>
        </div>
      ))}
    </dl>
  );
}
