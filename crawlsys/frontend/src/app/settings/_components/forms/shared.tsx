import { cloneElement, type ReactElement } from "react";

import { NumberInput } from "../../../_components/NumberInput";
import { Input } from "../../../_components/ui/input";
import { Label } from "../../../_components/ui/label";

import { Switch } from "../../../_components/ui/switch";

export const inputClass = "h-9 w-full";

export function Field({ name, label, error, hint, children }: { name: string; label: string; error?: string; hint?: string; children: ReactElement<Record<string, unknown>> }) {
  const hintId = `${name}-hint`;
  const errorId = `${name}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={name} className="text-xs font-medium text-foreground">
        {label}
      </Label>
      {cloneElement(children, {
        "aria-describedby": describedBy,
        "aria-invalid": Boolean(error),
      })}
      {hint ? (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function TextField({ name, id = name, label, defaultValue, error, hint, secret = false, disabled = false }: { name: string; id?: string; label: string; defaultValue?: string; error?: string; hint?: string; secret?: boolean; disabled?: boolean }) {
  return (
    <Field name={id} label={label} error={error} hint={hint}>
      <Input
        id={id}
        name={name}
        type={secret ? "password" : "text"}
        defaultValue={defaultValue}
        disabled={disabled}
        className={inputClass}
      />
    </Field>
  );
}

export function NumericField({ name, id = name, label, defaultValue, error, hint, integer = false, disabled = false }: { name: string; id?: string; label: string; defaultValue: number; error?: string; hint?: string; integer?: boolean; disabled?: boolean }) {
  return <Field name={id} label={label} error={error} hint={hint}><NumberInput id={id} name={name} defaultValue={defaultValue} integer={integer} disabled={disabled} className="w-full" /></Field>;
}

export function CheckField({ name, label, defaultChecked }: { name: string; label: string; defaultChecked: boolean }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
      <Switch name={name} defaultChecked={defaultChecked} />
      {label}
    </label>
  );
}

export const numberValue = (data: FormData, name: string) => Number(data.get(name));
