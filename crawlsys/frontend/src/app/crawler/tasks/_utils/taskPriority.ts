import { t, type MessageKey } from "../../../i18n";
import type { TaskPriority } from "../../../../utils/crawler/crawler-types";

const labelKeys = {
  lowest: "tasks.priorityLowest",
  low: "tasks.priorityLow",
  normal: "tasks.priorityNormal",
  high: "tasks.priorityHigh",
  urgent: "tasks.priorityUrgent",
} satisfies Record<TaskPriority, MessageKey>;

const badgeClasses = {
  lowest: "border-border bg-background text-muted-foreground",
  low: "border-border bg-muted text-muted-foreground",
  normal: "border-border bg-secondary text-secondary-foreground",
  high: "border-primary/30 bg-primary/10 text-primary",
  urgent: "border-destructive/30 bg-destructive/10 text-destructive",
} satisfies Record<TaskPriority, string>;

export function taskPriorityLabel(priority: TaskPriority) {
  return t(labelKeys[priority]);
}

export function taskPriorityBadgeClass(priority: TaskPriority) {
  return badgeClasses[priority];
}
