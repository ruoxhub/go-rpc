"use client";

import { Switch } from "@/app/_components/ui/switch";
import { t } from "../../../../i18n";

// 数据模型启用状态开关：可控 checkbox 语义与键盘可访问。
interface DatatypeStatusSwitchProps {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}

export function DatatypeStatusSwitch({
  label,
  checked,
  onChange,
}: DatatypeStatusSwitchProps) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <Switch
        role="switch"
        aria-label={label}
        checked={checked}
        onCheckedChange={onChange}
      />
      <span className={checked ? "text-foreground" : "text-muted-foreground"}>
        {checked ? t("common.enabled") : t("common.disabled")}
      </span>
    </label>
  );
}
