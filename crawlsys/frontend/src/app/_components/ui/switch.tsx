import * as React from "react";
import { cn } from "@/utils/cn";

export interface SwitchProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

const Switch = React.forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, checked, onCheckedChange, onChange, disabled, ...props }, ref) => {
    return (
      <input
        type="checkbox"
        ref={ref}
        checked={checked}
        disabled={disabled}
        onChange={(e) => {
          onChange?.(e);
          onCheckedChange?.(e.target.checked);
        }}
        className={cn(
          "size-4 shrink-0 cursor-pointer rounded border-input accent-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        {...props}
      />
    );
  }
);
Switch.displayName = "Switch";

export { Switch };
