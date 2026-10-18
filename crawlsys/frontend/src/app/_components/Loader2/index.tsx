export function Loader2({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={`size-4 animate-spin ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="M21 12a9 9 0 1 1-6.2-8.6" />
    </svg>
  );
}
