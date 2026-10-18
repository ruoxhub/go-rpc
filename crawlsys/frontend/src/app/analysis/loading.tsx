import { Skeleton } from "../_components/ui/skeleton";

export default function AnalysisLoading() {
  return (
    <main className="mx-auto max-w-[1600px] px-4 py-8">
      <Skeleton className="mb-8 h-10 w-48 rounded-lg" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
        {Array.from({ length: 12 }, (_, index) => (
          <Skeleton key={index} className="aspect-[3/4] rounded-lg" />
        ))}
      </div>
    </main>
  );
}
