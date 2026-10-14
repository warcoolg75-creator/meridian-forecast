import { Link } from "react-router";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-5xl space-y-3 px-4 py-12 sm:px-6">
      <h1 className="text-step-4">Page not found</h1>
      <p className="text-fg-muted">There is nothing at this address.</p>
      <Link to="/" className="inline-block text-primary underline-offset-4 hover:underline">
        Go to the home page
      </Link>
    </main>
  );
}
