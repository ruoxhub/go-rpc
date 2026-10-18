import type { InputHTMLAttributes } from "react";
import { Input } from "../ui/input";
import { cn } from "@/utils/cn";

interface NumberInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "inputMode"> {
  integer?: boolean;
}

export function NumberInput({
  integer = false,
  className = "",
  ...props
}: NumberInputProps) {
  return (
    <Input
      type="text"
      inputMode={integer ? "numeric" : "decimal"}
      className={cn("font-numeric bg-background", className)}
      {...props}
    />
  );
}
