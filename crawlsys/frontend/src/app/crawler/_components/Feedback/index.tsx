import type { ReactNode } from "react";
import { Alert, AlertDescription } from "@/app/_components/ui/alert";

type FeedbackVariant = "success" | "error" | "warning" | "info";

interface FeedbackProps {
  variant: FeedbackVariant;
  children: ReactNode;
}

const variantMap: Record<
  FeedbackVariant,
  "success" | "destructive" | "warning" | "info"
> = {
  success: "success",
  error: "destructive",
  warning: "warning",
  info: "info",
};

export function Feedback({ variant, children }: FeedbackProps) {
  const isUrgent = variant === "error";

  return (
    <Alert
      variant={variantMap[variant]}
      role={isUrgent ? "alert" : "status"}
      aria-live={isUrgent ? "assertive" : "polite"}
      className="px-3 py-2 text-sm"
    >
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
