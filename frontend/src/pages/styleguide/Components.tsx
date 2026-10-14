import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { InfoIcon } from "../../components/brand/icons";
import { BarChart } from "../../components/charts/BarChart";
import { KpiCard } from "../../components/charts/KpiCard";
import { TimeSeriesChart } from "../../components/charts/TimeSeriesChart";
import { DataTable, type Column } from "../../components/data/DataTable";
import { useClientTable } from "../../components/data/useClientTable";
import { EmptyState } from "../../components/feedback/EmptyState";
import { ErrorState } from "../../components/feedback/ErrorState";
import { Loading, Skeleton } from "../../components/feedback/Skeleton";
import { useToast, type ToastTone } from "../../components/feedback/toast-context";
import { FilterBar } from "../../components/filters/FilterBar";
import { defaultFilters, type Filters } from "../../components/filters/filters";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { cn } from "../../lib/cn";
import {
  formatCompactRupees,
  formatInteger,
  formatPercent,
  formatRupees,
  formatSignedPercent,
} from "../../lib/format";
import {
  channelOptions,
  channelSeries,
  comparisonSeries,
  FIXTURE_AS_OF,
  FIXTURE_FORECAST_START,
  fourYearSeries,
  kpiTrend,
  productOptions,
  products,
  regionOptions,
  totalSeries,
  unitsByProduct,
  unitsByProductYearOnYear,
  unitsByRegion,
  unitsByRegionAndChannel,
  unitsByYear,
  unitsSeries,
  unitsWithForecast,
  yearSeries,
  type FixtureProduct,
} from "./fixtures";
import { StyleguideNav } from "./StyleguideNav";

const SECTIONS = [
  ["feedback", "Feedback"],
  ["kpi", "KPI card"],
  ["time-series", "Time series chart"],
  ["bar", "Bar chart"],
  ["table", "Data table"],
  ["filters", "Filter bar"],
  ["shell", "App shell"],
] as const;

/** A failure for the error states, worded as the API's would be. */
const FIXTURE_ERROR = new Error("The server didn’t respond. Check your connection and try again.");

/**
 * Every component in every state (loading, empty, error, populated) on fixture data:
 * the page phase 3 is reviewed on. Linked from nowhere, like /styleguide.
 */
export default function Components() {
  useEffect(() => {
    document.title = "Components · Meridian styleguide";
  }, []);
  return (
    <div className="mx-auto max-w-6xl space-y-12 px-4 py-10 sm:px-6 lg:px-8">
      <header className="space-y-4">
        <StyleguideNav current="components" />
        <h1 className="text-step-5">Components</h1>
        <p className="max-w-3xl text-fg-muted">
          The component library phase 4 builds the analytics pages from. Each one is shown loading,
          empty, failed and populated. Charts take at most three series; the time series section
          shows a fourth being refused.
        </p>
        <div className="flex max-w-3xl gap-3 rounded-card border border-line-strong bg-surface-muted p-4">
          <InfoIcon className="size-5 shrink-0 text-fg-muted" />
          <p className="text-step-n1 text-fg">
            <span className="font-medium">Fixture data.</span> Every number, product and date on
            this page is invented (
            <code className="font-mono text-step-n2">src/pages/styleguide/fixtures.ts</code>). None
            of it comes from the API or the seeded database.
          </p>
        </div>
        <nav aria-label="Sections" className="flex flex-wrap gap-x-4 gap-y-2 text-step-n1">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="text-primary underline-offset-4 hover:underline">
              {label}
            </a>
          ))}
        </nav>
      </header>
      <FeedbackSection />
      <KpiSection />
      <TimeSeriesSection />
      <BarSection />
      <TableSection />
      <FilterSection />
      <ShellSection />
    </div>
  );
}

// ------------------------------------------------------------------------------- layout

function Section({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="space-y-6 border-t border-line pt-10"
    >
      <div className="max-w-3xl space-y-2">
        <h2 id={`${id}-title`} className="text-step-3">
          {title}
        </h2>
        <p className="text-fg-muted">{intro}</p>
      </div>
      {children}
    </section>
  );
}

/** A labelled specimen: the state or variant it shows, then the component. */
function Specimen({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("min-w-0 space-y-2", className)}>
      <h3 className="font-sans text-step-n1 font-medium text-fg-muted">{label}</h3>
      {children}
    </div>
  );
}

function Grid({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("grid gap-6 lg:grid-cols-2", className)}>{children}</div>;
}

/** Retry buttons on this page only say that they were pressed. */
function useFixtureRetry() {
  const toast = useToast();
  return () =>
    toast.show({
      title: "Retry pressed",
      description: "Fixture data: there is nothing to reload.",
    });
}

// ------------------------------------------------------------------------------- feedback

const TOASTS: Array<{ tone: ToastTone; label: string; title: string; description: string }> = [
  {
    tone: "neutral",
    label: "Neutral",
    title: "Forecast is recalculating",
    description: "This takes about a minute.",
  },
  {
    tone: "positive",
    label: "Positive",
    title: "Plan saved",
    description: "Week 42 production is locked.",
  },
  {
    tone: "warning",
    label: "Warning",
    title: "Peak season in 3 weeks",
    description: "Review capacity for festive lines.",
  },
  {
    tone: "negative",
    label: "Negative",
    title: "Import failed",
    description: "Row 18: quantity must be a whole number.",
  },
];

function FeedbackSection() {
  const toast = useToast();
  const retry = useFixtureRetry();
  return (
    <Section
      id="feedback"
      title="Feedback"
      intro="The states every data component is built from. Skeletons hold the shape of what is loading; errors are clay with a way to retry; toasts are for transient news."
    >
      <Grid className="lg:grid-cols-3">
        <Specimen label="Skeleton">
          <Card>
            <Loading label="example content" className="space-y-3">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-20" />
            </Loading>
          </Card>
        </Specimen>
        <Specimen label="Empty state">
          <Card>
            <EmptyState
              title="No sales in this range"
              description="Try a longer date range or fewer filters."
              action={
                <Button variant="secondary" size="sm">
                  Clear filters
                </Button>
              }
            />
          </Card>
        </Specimen>
        <Specimen label="Error state">
          <Card>
            <ErrorState
              title="Couldn’t load sales"
              message={FIXTURE_ERROR.message}
              onRetry={retry}
            />
          </Card>
        </Specimen>
      </Grid>
      <Specimen label="Toast: press to show (bottom right; negative ones are announced at once)">
        <div className="flex flex-wrap gap-3">
          {TOASTS.map(({ tone, label, title, description }) => (
            <Button
              key={tone}
              variant={tone === "negative" ? "destructive" : "secondary"}
              onClick={() => toast.show({ tone, title, description })}
            >
              {label}
            </Button>
          ))}
        </div>
      </Specimen>
    </Section>
  );
}

// ------------------------------------------------------------------------------- KPI

function KpiSection() {
  const retry = useFixtureRetry();
  const units = kpiTrend(11_200, 0.012, 3);
  return (
    <Section
      id="kpi"
      title="KPI card"
      intro="A headline figure, its change and its trend. The arrow gives the direction; the colour says whether that is good. With upIsGood off (stockouts, forecast error) a rise is clay."
    >
      <Grid className="sm:grid-cols-2 lg:grid-cols-4">
        <Specimen label="Loading">
          <KpiCard label="Units sold" value={undefined} sparkline={units} isLoading />
        </Specimen>
        <Specimen label="Empty">
          <KpiCard label="Units sold" value={null} emptyMessage="No sales in this period." />
        </Specimen>
        <Specimen label="Error">
          <KpiCard label="Units sold" value={undefined} error={FIXTURE_ERROR} onRetry={retry} />
        </Specimen>
        <Specimen label="Populated">
          <KpiCard
            label="Units sold"
            value={units[units.length - 1] * 4}
            delta={0.062}
            comparison="vs previous 4 weeks"
            sparkline={units}
            sparklineSpan="last 12 weeks"
          />
        </Specimen>
      </Grid>
      <Grid className="sm:grid-cols-2 lg:grid-cols-4">
        <Specimen label="Down, bad">
          <KpiCard
            label="Revenue"
            value={8_47_32_000}
            formatValue={formatRupees}
            delta={-0.031}
            comparison="vs previous 4 weeks"
            sparkline={kpiTrend(2_10_00_000, -0.004, 4)}
            sparklineSpan="last 12 weeks"
          />
        </Specimen>
        <Specimen label="Flat">
          <KpiCard
            label="Forecast accuracy"
            value={0.912}
            formatValue={formatPercent}
            delta={0.0002}
            comparison="vs previous 4 weeks"
          />
        </Specimen>
        <Specimen label="Up, bad (upIsGood off)">
          <KpiCard
            label="Stockout days"
            value={14}
            delta={0.167}
            upIsGood={false}
            comparison="vs previous 4 weeks"
            sparkline={kpiTrend(10, 0.03, 6)}
            sparklineSpan="last 12 weeks"
          />
        </Specimen>
        <Specimen label="Down, good (upIsGood off)">
          <KpiCard
            label="Returns"
            value={212}
            delta={-0.084}
            upIsGood={false}
            comparison="vs previous 4 weeks"
          />
        </Specimen>
      </Grid>
    </Section>
  );
}

// ------------------------------------------------------------------------------- time series

function TimeSeriesSection() {
  const retry = useFixtureRetry();
  const common = {
    xAxisLabel: "Week starting",
    yAxisLabel: "Units sold (units per week)",
  };
  return (
    <Section
      id="time-series"
      title="Time series chart"
      intro="Maroon is the primary series; the forecast continues it dashed after a divider at the last actual week, inside a maroon band. Every chart carries its plotted values as a table only screen readers see."
    >
      <Grid>
        <Specimen label="Loading">
          <TimeSeriesChart
            title="Weekly units: Copper water bottle"
            description="Fixture: 26 weeks of actual sales, then an 8-week forecast with its 80% interval."
            series={unitsSeries}
            data={[]}
            {...common}
            isLoading
          />
        </Specimen>
        <Specimen label="Empty">
          <TimeSeriesChart
            title="Weekly units: Copper water bottle"
            description="Fixture: 26 weeks of actual sales, then an 8-week forecast with its 80% interval."
            series={unitsSeries}
            data={[]}
            {...common}
            emptyTitle="No sales in this range"
            emptyMessage="This product has no sales between these dates."
          />
        </Specimen>
        <Specimen label="Error">
          <TimeSeriesChart
            title="Weekly units: Copper water bottle"
            description="Fixture: 26 weeks of actual sales, then an 8-week forecast with its 80% interval."
            series={unitsSeries}
            data={[]}
            {...common}
            error={FIXTURE_ERROR}
            onRetry={retry}
          />
        </Specimen>
        <Specimen label="Populated: actuals, forecast and band">
          <TimeSeriesChart
            title="Weekly units: Copper water bottle"
            description="Fixture: 26 weeks of actual sales, then an 8-week forecast with its 80% interval."
            series={unitsSeries}
            data={unitsWithForecast}
            forecastStart={FIXTURE_FORECAST_START}
            bandLabel="80% interval"
            {...common}
          />
        </Specimen>
        <Specimen label="At the cap: three series">
          <TimeSeriesChart
            title="Weekly units, year on year"
            description="Fixture: the same 26 weeks in each of the last three years."
            series={yearSeries}
            data={unitsByYear}
            {...common}
          />
        </Specimen>
        <Specimen label="Over the cap: a fourth series is refused">
          <TimeSeriesChart
            title="Weekly units, four years"
            description="Fixture: the same 26 weeks in each of the last four years."
            series={fourYearSeries}
            data={unitsByYear}
            {...common}
          />
        </Specimen>
      </Grid>
    </Section>
  );
}

// ------------------------------------------------------------------------------- bar

function BarSection() {
  const retry = useFixtureRetry();
  const regional = {
    title: "Units sold by region",
    description: "Fixture: units sold in the last 4 weeks, by region.",
    categoryAxisLabel: "Region",
    valueAxisLabel: "Units sold (units)",
  };
  return (
    <Section
      id="bar"
      title="Bar chart"
      intro="Columns or horizontal bars, single or grouped: at most 24px thick, 4px rounded ends, 2px apart within a group. Horizontal bars suit long labels such as product names."
    >
      <Grid>
        <Specimen label="Loading">
          <BarChart {...regional} series={totalSeries} data={[]} isLoading />
        </Specimen>
        <Specimen label="Empty">
          <BarChart
            {...regional}
            series={totalSeries}
            data={[]}
            emptyTitle="No sales in this range"
            emptyMessage="No region sold anything between these dates."
          />
        </Specimen>
        <Specimen label="Error">
          <BarChart
            {...regional}
            series={totalSeries}
            data={[]}
            error={FIXTURE_ERROR}
            onRetry={retry}
          />
        </Specimen>
        <Specimen label="Populated: vertical, single">
          <BarChart {...regional} series={totalSeries} data={unitsByRegion} />
        </Specimen>
        <Specimen label="Vertical, grouped">
          <BarChart
            {...regional}
            title="Units sold by region and channel"
            description="Fixture: units sold in the last 4 weeks, by region, split by sales channel."
            series={channelSeries}
            data={unitsByRegionAndChannel}
          />
        </Specimen>
        <Specimen label="Horizontal, single">
          <BarChart
            title="Top products by units"
            description="Fixture: the eight best-selling products in the last 4 weeks."
            series={totalSeries}
            data={unitsByProduct}
            orientation="horizontal"
            categoryAxisLabel="Product"
            valueAxisLabel="Units sold (units)"
            height="lg"
          />
        </Specimen>
        <Specimen label="Horizontal, grouped" className="lg:col-span-2">
          <BarChart
            title="Top products, year on year"
            description="Fixture: the five best-selling products, last 4 weeks against the same 4 weeks a year earlier."
            series={comparisonSeries}
            data={unitsByProductYearOnYear}
            orientation="horizontal"
            categoryAxisLabel="Product"
            valueAxisLabel="Units sold (units)"
            height="lg"
          />
        </Specimen>
      </Grid>
    </Section>
  );
}

// ------------------------------------------------------------------------------- table

const PRODUCT_COLUMNS: Column<FixtureProduct>[] = [
  { key: "sku", header: "SKU", value: (p) => p.sku, sortable: true },
  { key: "name", header: "Product", value: (p) => p.name, sortable: true },
  { key: "category", header: "Category", value: (p) => p.category, sortable: true },
  {
    key: "units",
    header: "Units (4 wk)",
    value: (p) => p.units,
    render: (p) => formatInteger(p.units),
    numeric: true,
    sortable: true,
  },
  {
    key: "revenue",
    header: "Revenue (4 wk)",
    value: (p) => p.revenueMinor,
    render: (p) => formatCompactRupees(p.revenueMinor),
    numeric: true,
    sortable: true,
  },
  {
    key: "change",
    header: "Change",
    value: (p) => p.change,
    render: (p) => (
      <span
        className={
          p.change > 0 ? "text-positive" : p.change < 0 ? "text-negative" : "text-fg-muted"
        }
      >
        {formatSignedPercent(p.change)}
      </span>
    ),
    numeric: true,
    sortable: true,
  },
];

function TableSection() {
  const toast = useToast();
  const retry = useFixtureRetry();
  const table = useClientTable({
    rows: products,
    columns: PRODUCT_COLUMNS,
    pageSize: 8,
    initialSort: { key: "units", direction: "desc" },
  });
  const empty = useClientTable({ rows: [], columns: PRODUCT_COLUMNS, pageSize: 8 });
  return (
    <Section
      id="table"
      title="Data table"
      intro="Sortable headers, right-aligned tabular numbers and a sticky header inside a scrolling panel. Sorting and paging are controlled: here useClientTable does both in the browser; phase 4 can page on the server instead. Rows open on click, Enter or Space."
    >
      <Specimen label="Populated: sorted by units, 8 rows a page, rows clickable">
        <DataTable
          caption="Products, last 4 weeks"
          columns={PRODUCT_COLUMNS}
          rowKey={(p) => p.sku}
          {...table}
          onRowClick={(p) =>
            toast.show({ title: `${p.sku} · ${p.name}`, description: "Row opened (fixture)." })
          }
        />
      </Specimen>
      <div className="space-y-6">
        <Specimen label="Loading">
          <DataTable
            caption="Products, last 4 weeks"
            columns={PRODUCT_COLUMNS}
            rowKey={(p) => p.sku}
            rows={[]}
            pagination={{ ...table.pagination, pageSize: 4 }}
            isLoading
          />
        </Specimen>
        <Specimen label="Empty">
          <DataTable
            caption="Products, last 4 weeks"
            columns={PRODUCT_COLUMNS}
            rowKey={(p) => p.sku}
            {...empty}
            emptyTitle="No products match"
            emptyMessage="Try fewer filters."
          />
        </Specimen>
        <Specimen label="Error">
          <DataTable
            caption="Products, last 4 weeks"
            columns={PRODUCT_COLUMNS}
            rowKey={(p) => p.sku}
            rows={[]}
            error={FIXTURE_ERROR}
            onRetry={retry}
          />
        </Specimen>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------- filters

const OPTIONS = { products: productOptions, regions: regionOptions, channels: channelOptions };
const NO_OPTIONS = { products: [], regions: [], channels: [] };

function FilterSection() {
  const retry = useFixtureRetry();
  const [filters, setFilters] = useState<Filters>(() => defaultFilters(FIXTURE_AS_OF));
  const [still, setStill] = useState<Filters>(() => defaultFilters(FIXTURE_AS_OF));
  return (
    <Section
      id="filters"
      title="Filter bar"
      intro="Date range (presets counting back from the last day with data, or custom), product, region and channel, and granularity. It owns no data: it receives options and emits a complete filter object. No selection means all."
    >
      <Specimen label="Populated (live): the object it emits is printed below">
        <Card className="space-y-4">
          <FilterBar value={filters} onChange={setFilters} options={OPTIONS} asOf={FIXTURE_AS_OF} />
          <pre className="overflow-x-auto rounded-control bg-surface-muted p-4 font-mono text-step-n2 text-fg">
            {JSON.stringify(filters, null, 2)}
          </pre>
        </Card>
      </Specimen>
      <Specimen label="Loading: options not loaded yet">
        <Card>
          <FilterBar
            value={still}
            onChange={setStill}
            options={NO_OPTIONS}
            asOf={FIXTURE_AS_OF}
            optionsLoading
          />
        </Card>
      </Specimen>
      <Specimen label="Empty: no options to choose from (open a list)">
        <Card>
          <FilterBar value={still} onChange={setStill} options={NO_OPTIONS} asOf={FIXTURE_AS_OF} />
        </Card>
      </Specimen>
      <Specimen label="Error: options failed to load (open a list)">
        <Card>
          <FilterBar
            value={still}
            onChange={setStill}
            options={NO_OPTIONS}
            asOf={FIXTURE_AS_OF}
            optionsError={FIXTURE_ERROR.message}
            onRetryOptions={retry}
          />
        </Card>
      </Specimen>
    </Section>
  );
}

// ------------------------------------------------------------------------------- shell

function ShellSection() {
  return (
    <Section
      id="shell"
      title="App shell"
      intro="The sidebar, top bar and page scaffold are live in the app rather than here, because they need a signed-in session."
    >
      <Card className="max-w-3xl space-y-3 text-step-n1">
        <ul className="list-disc space-y-2 pl-5 text-fg">
          <li>Below 768px: a top bar with a hamburger that opens the navigation drawer.</li>
          <li>768 to 1023px: the sidebar shows icons only, with labels on hover and focus.</li>
          <li>
            From 1024px: the full sidebar. Its collapse button is remembered per browser
            (localStorage,{" "}
            <code className="font-mono text-step-n2">meridian.sidebar.collapsed</code>
            ).
          </li>
          <li>Planning appears only for admins and planners.</li>
        </ul>
        <Link
          to="/app/dashboard"
          className="inline-block text-primary underline-offset-4 hover:underline"
        >
          Open the app
        </Link>
      </Card>
    </Section>
  );
}
