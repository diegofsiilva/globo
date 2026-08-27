"use client";

import * as React from "react";
import { X } from "lucide-react";
import * as SheetPrimitive from "@radix-ui/react-dialog";
import { cn } from "@/lib/utils";

const Sheet = SheetPrimitive.Root;
const SheetTrigger = SheetPrimitive.Trigger;
const SheetClose = SheetPrimitive.Close;

function SheetOverlay({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Overlay>) {
  return (
    <SheetPrimitive.Overlay
      className={cn("fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px] data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 motion-reduce:animate-none", className)}
      {...props}
    />
  );
}

function SheetContent({ className, children, side = "left", showCloseButton = true, ...props }: React.ComponentProps<typeof SheetPrimitive.Content> & { side?: "left" | "right"; showCloseButton?: boolean }) {
  return (
    <SheetPrimitive.Portal>
      <SheetOverlay />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          "fixed inset-y-0 z-50 flex h-dvh w-[min(86vw,340px)] flex-col overflow-y-auto overscroll-contain border-border-strong bg-background shadow-[0_0_60px_rgb(0_0_0/0.34)] outline-none transition-transform duration-[240ms] ease-out data-[state=closed]:animate-out data-[state=open]:animate-in motion-reduce:transition-none motion-reduce:data-[state=closed]:animate-none motion-reduce:data-[state=open]:animate-none",
          side === "left" && "left-0 border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left",
          side === "right" && "right-0 border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close className="absolute right-3 top-3 grid size-11 place-items-center border border-transparent text-muted-foreground outline-none transition-[background-color,color,border-color] hover:bg-surface-raised hover:text-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none">
            <X aria-hidden="true" className="size-5" />
            <span className="sr-only">Fechar menu</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-2 border-b border-border p-5 pr-16", className)} {...props} />;
}

function SheetTitle({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Title>) {
  return <SheetPrimitive.Title className={cn("text-sm font-semibold uppercase tracking-[0.08em] text-foreground", className)} {...props} />;
}

function SheetDescription({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Description>) {
  return <SheetPrimitive.Description className={cn("text-xs leading-relaxed text-muted-foreground", className)} {...props} />;
}

export { Sheet, SheetTrigger, SheetClose, SheetContent, SheetHeader, SheetTitle, SheetDescription };
