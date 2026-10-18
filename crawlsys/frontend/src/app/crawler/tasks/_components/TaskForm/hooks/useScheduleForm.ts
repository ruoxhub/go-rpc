import { useState } from "react";
import type { Task } from "@/utils/crawler/crawler-types";
import type { ScheduleFormValue } from "../types/schedule";
import { initialSchedule } from "../utils/taskForm";

export function useScheduleForm(task?: Task) {
  const [value, setValue] = useState<ScheduleFormValue>(() => initialSchedule(task));
  return { value, setValue };
}
