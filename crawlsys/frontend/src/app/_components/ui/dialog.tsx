"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/utils/cn";

export interface DialogProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

const DialogContext = React.createContext<{
  open: boolean;
  onOpenChange?: (open: boolean) => void;
}>({ open: false });

export function Dialog({ open, onOpenChange, children }: DialogProps) {
  if (!open) return null;

  return (
    <DialogContext.Provider value={{ open, onOpenChange }}>
      {children}
    </DialogContext.Provider>
  );
}

export interface DialogContentProps
  extends React.DialogHTMLAttributes<HTMLDialogElement> {
  onClose?: () => void;
  showCloseButton?: boolean;
}

export const DialogContent = React.forwardRef<
  HTMLDialogElement,
  DialogContentProps
>(
  (
    {
      className,
      children,
      onClose,
      onCancel,
      showCloseButton = true,
      ...props
    },
    ref
  ) => {
    const { open, onOpenChange } = React.useContext(DialogContext);
    const internalRef = React.useRef<HTMLDialogElement | null>(null);
    const handleClose = onClose || (() => onOpenChange?.(false));

    React.useEffect(() => {
      const dialog = internalRef.current;
      if (!dialog) return;
      if (open) {
        if (typeof dialog.showModal === "function" && !dialog.open) {
          try {
            dialog.showModal();
          } catch {
            dialog.setAttribute("open", "");
          }
        } else {
          dialog.setAttribute("open", "");
        }
      }
    }, [open]);

    return (
      <dialog
        ref={(node) => {
          internalRef.current = node;
          if (typeof ref === "function") ref(node);
          else if (ref) ref.current = node;
        }}
        onCancel={(event) => {
          if (onCancel) {
            onCancel(event);
          } else {
            event.preventDefault();
            handleClose();
          }
        }}
        onClose={() => {
          handleClose();
        }}
        className={cn(
          "fixed inset-0 m-auto w-[min(28rem,calc(100%-2rem))] rounded-lg border border-border bg-card p-6 text-card-foreground shadow-lg backdrop:bg-foreground/30",
          className
        )}
        {...props}
      >
        {showCloseButton ? (
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close"
            className="absolute right-4 top-4 rounded-sm opacity-70 transition-opacity hover:opacity-100 focus:outline-none cursor-pointer"
          >
            <X className="size-4" />
          </button>
        ) : null}
        {children}
      </dialog>
    );
  }
);
DialogContent.displayName = "DialogContent";

export function DialogHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col space-y-1.5 text-left", className)}
      {...props}
    />
  );
}

export function DialogTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        "text-lg font-semibold leading-none tracking-tight",
        className
      )}
      {...props}
    />
  );
}

export function DialogDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-sm text-muted-foreground", className)} {...props} />
  );
}

export function DialogFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mt-6 flex justify-end gap-2", className)}
      {...props}
    />
  );
}
