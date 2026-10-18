import { Skeleton } from "./_components/ui/skeleton";

export default function Loading() {
  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 md:px-6 md:py-8">
      <div className="space-y-3 pb-6">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80" />
        <div className="h-px bg-border" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-44 rounded-lg" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:col-span-2">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-20 rounded-lg" />
          ))}
        </div>
      </div>
      {Array.from({ length: 3 }).map((_, index) => (
        <Skeleton key={index} className="h-72 rounded-lg" />
      ))}
    </main>
  );
}
