import { useHeadlines } from "../../../api/market";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { ErrorState } from "../../../components/feedback/ErrorState";
import { Loading, Skeleton } from "../../../components/feedback/Skeleton";
import { Card } from "../../../components/ui/Card";
import { formatDate } from "../../../lib/dates";
import { errorMessage, formatInteger } from "../../../lib/format";
import { SignalStatusBadge } from "./SignalCard";
import { timestampDate } from "./present";

/** The newest headlines for a category: title linked to the publisher, never the article. */
export function Headlines({ category }: { category: string }) {
  const query = useHeadlines(category);
  const data = query.data;
  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-step-1">Recent headlines</h3>
          <p className="text-step-n1 text-fg-muted">
            Indian news matching this category’s keywords, newest first. Headlines and links only.
          </p>
        </div>
        {data && (
          <SignalStatusBadge status={data.source.status} reason={data.source.status_reason} />
        )}
      </div>

      {query.isPending && (
        <Loading label="Recent headlines" className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </Loading>
      )}
      {query.error && (
        <ErrorState
          title="Couldn’t load headlines"
          message={errorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      )}
      {data && data.items.length === 0 && (
        <EmptyState
          title="No headlines yet"
          description={data.source.status_reason ?? "Nothing stored for this category."}
        />
      )}
      {data && data.items.length > 0 && (
        <ul className="divide-y divide-line">
          {data.items.map((item) => {
            const day = timestampDate(item.published_at);
            return (
              <li key={item.url} className="space-y-1 py-3 first:pt-0 last:pb-0">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  lang={item.language === "English" ? undefined : languageTag(item.language)}
                  className="font-medium break-words text-fg underline decoration-line-strong underline-offset-2 hover:decoration-fg"
                >
                  {item.title}
                </a>
                <p className="text-step-n2 text-fg-muted">
                  {item.publisher}
                  {day && (
                    <>
                      {" · "}
                      <time dateTime={item.published_at} className="figure">
                        {formatDate(day)}
                      </time>
                    </>
                  )}
                  {item.language !== "English" && ` · ${item.language}`}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {data && (
        <p className="text-step-n2 text-fg-muted">
          {`${formatInteger(data.total)} headlines stored for ${category}. Dates are when the `}
          <a
            href={data.source.homepage}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-line-strong underline-offset-2 hover:decoration-fg"
          >
            GDELT Project
          </a>
          {" first saw an article; the articles belong to their publishers."}
        </p>
      )}
    </Card>
  );
}

const LANGUAGE_TAGS: Record<string, string> = {
  Hindi: "hi",
  Bengali: "bn",
  Tamil: "ta",
  Telugu: "te",
  Marathi: "mr",
  Gujarati: "gu",
  Kannada: "kn",
  Malayalam: "ml",
  Punjabi: "pa",
  Urdu: "ur",
};

/** A BCP 47 tag for the title, so a screen reader pronounces it in its own language. */
function languageTag(language: string): string | undefined {
  return LANGUAGE_TAGS[language];
}
