import type { ButtonHTMLAttributes } from "react";
import { Loader2 } from "../../../_components/Loader2";
import { Button } from "@/app/_components/ui/button";

interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  loaderClassName?: string;
}

export function SubmitButton({
  loading = false,
  loaderClassName,
  disabled,
  children,
  className = "",
  type = "submit",
  ...props
}: SubmitButtonProps) {
  return (
    <Button
      type={type}
      variant="gradient"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={className}
      {...props}
    >
      {loading ? <Loader2 className={loaderClassName} /> : null}
      {children}
    </Button>
  );
}
