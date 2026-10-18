export default function AnalysisDetailLoading() {
  return <main className="mx-auto max-w-7xl px-4 py-8"><div className="mb-8 h-10 w-72 animate-pulse rounded-lg bg-muted" /><div className="grid gap-7 lg:grid-cols-[360px_1fr]"><div className="aspect-[9/16] animate-pulse rounded-lg bg-muted" /><div className="space-y-5">{Array.from({ length: 4 }, (_, index) => <div key={index} className="h-40 animate-pulse rounded-lg bg-muted" />)}</div></div></main>;
}
