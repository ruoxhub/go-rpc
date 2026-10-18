"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/utils/cn";

export interface SheetProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

const SheetContext = React.createContext<{
  open: boolean;
  onOpenChange?: (open: boolean) => void;
}>({ open: false });

export function Sheet({ open, onOpenChange, children }: SheetProps) {
  if (!open) return null;

  return (
    <SheetContext.Provider value={{ open, onOpenChange }}>
      {children}
    </SheetContext.Provider>
  );
}

const sheetVariants = cva(
  "fixed m-0 max-h-full max-w-full bg-card p-6 text-foreground shadow-lg transition ease-in-out border-border backdrop:bg-foreground/30",
  {
    variants: {
      side: {
        top: "inset-x-0 top-0 border-b",
        bottom: "inset-x-0 bottom-0 border-t",
        left: "inset-y-0 left-0 right-auto h-full w-3/4 border-r sm:max-w-md",
        right: "inset-y-0 left-auto right-0 h-full w-[min(40rem,100%)] border-l",
      },
    },
    defaultVariants: {
      side: "right",
    },
  }
);

export interface SheetContentProps
  extends React.DialogHTMLAttributes<HTMLDialogElement>,
    VariantProps<typeof sheetVariants> {
  onClose?: () => void;
  showCloseButton?: boolean;
}

export const SheetContent = React.forwardRef<
  HTMLDialogElement,
  SheetContentProps
>(
  (
    {
      side = "right",
      className,
      children,
      onClose,
      onCancel,
      showCloseButton = false,
      ...props
    },
    ref
  ) => {
    const { open, onOpenChange } = React.useContext(SheetContext);
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
        className={cn(sheetVariants({ side }), className)}
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
SheetContent.displayName = "SheetContent";

export function SheetHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex flex-col space-y-2 text-left", className)}
      {...props}
    />
  );
}

export function SheetTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("text-lg font-semibold text-foreground", className)}
      {...props}
    />
  );
}

export function SheetDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-sm text-muted-foreground", className)} {...props} />
  );
}

export function SheetFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 mt-6",
        className
      )}
      {...props}
    />
  );
}
