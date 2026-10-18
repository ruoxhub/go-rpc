import { Skeleton } from "../_components/ui/skeleton";

export default function Loading() {
  return (
    <main aria-busy="true" className="mx-auto max-w-6xl space-y-6 px-4 py-6 md:px-6 md:py-8">
      <Skeleton className="h-20 rounded-lg" />
      <Skeleton className="h-12 rounded-lg" />
      <div className="grid gap-5 xl:grid-cols-2">
        <Skeleton className="h-96 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    </main>
  );
}
