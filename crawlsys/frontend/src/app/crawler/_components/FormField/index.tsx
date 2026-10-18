import { cloneElement, isValidElement, type ReactElement } from "react";
import { Label } from "@/app/_components/ui/label";

interface FormFieldProps {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: ReactElement<Record<string, unknown>>;
}

export function FormField({
  id,
  label,
  error,
  hint,
  required,
  children,
}: FormFieldProps) {
  const existingDescription =
    typeof children.props["aria-describedby"] === "string"
      ? children.props["aria-describedby"]
      : undefined;
  const descriptionIds = [
    existingDescription,
    hint ? `${id}-hint` : undefined,
    error ? `${id}-error` : undefined,
  ].filter((value): value is string => Boolean(value));
  const describedBy = [...new Set(descriptionIds)].join(" ") || undefined;
  const controlProps: Record<string, unknown> = {
    id,
    "aria-describedby": describedBy,
  };
  if (required !== undefined) controlProps.required = required;
  if (error !== undefined) controlProps["aria-invalid"] = true;
  const control = isValidElement(children)
    ? cloneElement(children, controlProps)
    : children;

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-foreground">
        {label}
      </Label>
      {control}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error !== undefined ? (
        <p id={`${id}-error`} className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
