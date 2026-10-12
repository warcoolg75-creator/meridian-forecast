/** Empty page: only its name, so routing is visibly testable until its phase builds it. */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6">
      <h1 className="text-step-4">{title}</h1>
    </main>
  );
}
