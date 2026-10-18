"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { Loader2 } from "../Loader2";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel: string;
  busy?: boolean;
  destructive?: boolean;
  loaderClassName?: string;
  onCancel: () => void;
  onConfirm: () => void;
  children?: ReactNode;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  busy = false,
  destructive = false,
  loaderClassName,
  onCancel,
  onConfirm,
  children,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement as HTMLElement | null;
      (destructive ? cancelRef.current : confirmRef.current)?.focus();
      return () => restoreFocusRef.current?.focus();
    }
    restoreFocusRef.current?.focus();
  }, [destructive, open]);

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && !busy && onCancel()}>
      <DialogContent
        ref={dialogRef}
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        onCancel={(event) => {
          event.preventDefault();
          if (!busy) onCancel();
        }}
        showCloseButton={false}
        className="p-6"
      >
        <DialogHeader>
          <DialogTitle id={titleId} className="text-lg font-semibold">
            {title}
          </DialogTitle>
          {description ? (
            <DialogDescription id={descriptionId} className="mt-2 text-sm text-muted-foreground">
              {description}
            </DialogDescription>
          ) : null}
        </DialogHeader>
        {children ? <div className="mt-4">{children}</div> : null}
        <DialogFooter className="mt-6 flex justify-end gap-2">
          <Button
            ref={cancelRef}
            type="button"
            variant="outline"
            disabled={busy}
            onClick={onCancel}
          >
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            type="button"
            variant={destructive ? "destructive" : "gradient"}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? (
              <Loader2 className={`mr-2 inline ${loaderClassName ?? ""}`} />
            ) : null}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
