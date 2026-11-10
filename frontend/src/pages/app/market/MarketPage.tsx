import { useSearchParams } from "react-router";

import {
  useMarketOverview,
  useSignalSeries,
  type CategoryMarket,
  type MappedSeries,
  type SourceStatus,
} from "../../../api/market";
import { ErrorState } from "../../../components/feedback/ErrorState";
import { Loading, Skeleton } from "../../../components/feedback/Skeleton";
import { PageScaffold } from "../../../components/shell/PageScaffold";
import { Card } from "../../../components/ui/Card";
import { cn } from "../../../lib/cn";
import { formatDate, type IsoDate } from "../../../lib/dates";
import { errorMessage } from "../../../lib/format";
import { isPointerClick } from "../../../lib/pointer";
import { Headlines } from "./Headlines";
import { CONTEXT_NOTE, timestampDate } from "./present";
import { ContextNote, SignalChart, SignalStatusBadge } from "./SignalCard";

/** New Delhi first where a category has weather: the largest market of most cooling SKUs. */
const DEFAULT_CITY = "IN-DL-NDL";

interface Group {
  key: string;
  members: MappedSeries[];
}

/** Series of one variable in several cities form one group, shown one city at a time. */
function groupsOf(items: MappedSeries[]): Group[] {
  const groups: Group[] = [];
  for (const item of items) {
    const group = groups.find((g) => g.key === item.series.group_key);
    if (group) group.members.push(item);
    else groups.push({ key: item.series.group_key, members: [item] });
  }
  return groups;
}

function CategoryTabs({
  categories,
  active,
  onSelect,
}: {
  categories: string[];
  active: string | undefined;
  onSelect: (category: string) => void;
}) {
  return (
    <nav aria-label="Categories" className="flex flex-wrap gap-2 border-b border-line pb-2">
      {categories.map((category) => (
        <button
          key={category}
          type="button"
          aria-current={category === active ? "true" : undefined}
          onClick={(e) => {
            onSelect(category);
            if (isPointerClick(e)) e.currentTarget.blur();
          }}
          className={cn(
            "rounded-control px-3 py-2 text-step-n1 font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
            category === active ? "bg-surface-muted text-fg" : "text-fg-muted hover:text-fg",
          )}
        >
          {category}
        </button>
      ))}
    </nav>
  );
}

function CategorySection({
  block,
  salesFrom,
  city,
  onCity,
}: {
  block: CategoryMarket;
  salesFrom: IsoDate | null;
  city: string | null;
  onCity: (code: string) => void;
}) {
  const demandGroups = groupsOf(block.demand_context);
  const seen = new Map<string, string>();
  for (const g of demandGroups) {
    if (g.members.length > 1) {
      for (const m of g.members) seen.set(m.series.geography, m.series.geography_name);
    }
  }
  const cities = [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const chosenCity =
    cities.find(([code]) => code === city)?.[0] ??
    cities.find(([code]) => code === DEFAULT_CITY)?.[0] ??
    cities[0]?.[0];
  const shown: MappedSeries[] = demandGroups.map((g) =>
    g.members.length > 1
      ? (g.members.find((m) => m.series.geography === chosenCity) ?? g.members[0])
      : g.members[0],
  );
  const keys = [
    ...shown.flatMap((m) => [
      m.series.key,
      ...(m.series.forecast_key ? [m.series.forecast_key] : []),
    ]),
    ...block.input_cost.map((m) => m.series.key),
  ];
  const values = useSignalSeries(keys, "week", salesFrom);
  const period = salesFrom ? `weekly from ${formatDate(salesFrom)}` : "weekly";
  const chart = (m: MappedSeries) => (
    <SignalChart
      key={m.series.key}
      mapped={m}
      observed={values.data?.get(m.series.key)}
      forecast={m.series.forecast_key ? values.data?.get(m.series.forecast_key) : undefined}
      period={
        m.series.frequency === "monthly" && salesFrom
          ? `monthly from ${formatDate(salesFrom)}`
          : period
      }
      isLoading={values.isPending}
      error={values.error}
      onRetry={() => void values.refetch()}
    />
  );

  return (
    <section aria-labelledby="category-title" className="space-y-8">
      <h2 id="category-title" className="text-step-3">
        {block.category}
      </h2>

      <div className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="space-y-1">
            <h3 className="text-step-2">Demand context</h3>
            <p className="max-w-3xl text-step-n1 text-fg-muted">
              Outside series that move with this category’s season. Shown beside our sales, never
              used to forecast them.
            </p>
          </div>
          {cities.length > 1 && (
            <label className="flex items-center gap-2 text-step-n1 text-fg-muted">
              Weather in
              <select
                className="h-10 rounded-control border border-line-strong bg-surface px-2 text-step-n1 text-fg"
                value={chosenCity}
                onChange={(event) => onCity(event.target.value)}
              >
                {cities.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {shown.length ? (
          <div className="grid gap-6 lg:grid-cols-2">{shown.map(chart)}</div>
        ) : (
          <Card className="text-step-n1 text-fg-muted">
            None of these sources carries a demand signal for {block.category}.
          </Card>
        )}
      </div>

      <div className="space-y-4">
        <div className="space-y-1">
          <h3 className="text-step-2">Input costs</h3>
          <p className="max-w-3xl text-step-n1 text-fg-muted">
            What our materials, fuel and imports cost. For production planning, not a demand signal.
          </p>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">{block.input_cost.map(chart)}</div>
      </div>

      <Headlines category={block.category} />
    </section>
  );
}

function SourcesPanel({ sources }: { sources: SourceStatus[] }) {
  const fred = sources.find((s) => s.code === "fred");
  return (
    <section aria-labelledby="sources-title" className="space-y-4">
      <h2 id="sources-title" className="text-step-2">
        Sources and licences
      </h2>
      <Card className="space-y-4">
        <ul className="divide-y divide-line">
          {sources.map((s) => {
            const updated = timestampDate(s.last_success_at);
            return (
              <li key={s.code} className="space-y-1 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={s.homepage}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-fg underline decoration-line-strong underline-offset-2 hover:decoration-fg"
                  >
                    {s.name}
                  </a>
                  <SignalStatusBadge status={s.status} reason={s.status_reason} />
                </div>
                <p className="text-step-n2 text-fg-muted">
                  {updated ? (
                    <>
                      {"Last refreshed "}
                      <span className="figure text-fg">{formatDate(updated)}</span>
                      {". "}
                    </>
                  ) : (
                    // Not "never": a run cut short can still have stored data (news, partial).
                    "No complete refresh yet. "
                  )}
                  {s.licence}{" "}
                  <a
                    href={s.terms_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline decoration-line-strong underline-offset-2 hover:decoration-fg"
                  >
                    Terms of use
                  </a>
                </p>
                {s.status !== "fresh" && s.status_reason && (
                  <p className="text-step-n2 break-words text-warning-text">{s.status_reason}</p>
                )}
              </li>
            );
          })}
        </ul>
        {fred && (
          <p className="text-step-n2 text-fg-muted">
            {`${fred.attribution} By using the FRED data on this page you agree to the `}
            <a
              href={fred.terms_url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-line-strong underline-offset-2 hover:decoration-fg"
            >
              FRED® API Terms of Use
            </a>
            .
          </p>
        )}
        <p className="text-step-n2 text-fg-muted">
          The attention series are views of English Wikipedia articles from anywhere in the world: a
          rough proxy for interest, not Indian search data.
        </p>
      </Card>
    </section>
  );
}

/** Outside market signals per category: context beside our sales, never forecast inputs. */
export default function MarketPage() {
  const overview = useMarketOverview();
  const [params, setParams] = useSearchParams();
  const categories = overview.data?.categories ?? [];
  const active = categories.find((c) => c.category === params.get("category")) ?? categories[0];

  const setParam = (key: string, value: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set(key, value);
        return next;
      },
      { replace: true },
    );

  return (
    <PageScaffold
      title="Market"
      subtitle="Outside signals beside our sales: weather, attention to the products, input costs and news."
    >
      <ContextNote>{CONTEXT_NOTE}</ContextNote>

      {overview.error && (
        <Card>
          <ErrorState
            title="Couldn’t load the market signals"
            message={errorMessage(overview.error)}
            onRetry={() => void overview.refetch()}
          />
        </Card>
      )}
      {overview.isPending && (
        <Loading label="Market signals" className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <div className="grid gap-6 lg:grid-cols-2">
            <Skeleton className="h-chart-md w-full" />
            <Skeleton className="h-chart-md w-full" />
          </div>
        </Loading>
      )}

      {overview.data && (
        <>
          <CategoryTabs
            categories={categories.map((c) => c.category)}
            active={active?.category}
            onSelect={(category) => setParam("category", category)}
          />
          {active && (
            <CategorySection
              key={active.category}
              block={active}
              salesFrom={overview.data.sales_first_date}
              city={params.get("city")}
              onCity={(code) => setParam("city", code)}
            />
          )}
          <SourcesPanel sources={overview.data.sources} />
        </>
      )}
    </PageScaffold>
  );
}
