"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import * as TogglePrimitive from "@radix-ui/react-toggle";
import { cn } from "@/lib/utils";

const toggleVariants = cva(
  "inline-flex touch-manipulation items-center justify-center border border-transparent font-mono text-[12px] font-medium text-muted-foreground outline-none transition-[background-color,color,border-color] duration-[160ms] hover:bg-surface-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-45 data-[state=on]:bg-foreground data-[state=on]:text-background motion-reduce:transition-none md:text-[11px]",
  {
    variants: {
      variant: {
        default: "bg-transparent",
        outline: "border-border-strong bg-transparent",
      },
      size: {
        default: "h-10 min-w-11 px-3",
        sm: "h-11 min-w-11 px-2.5 md:h-8 md:min-w-9",
        lg: "h-11 min-w-12 px-4",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Toggle({ className, variant, size, ...props }: React.ComponentProps<typeof TogglePrimitive.Root> & VariantProps<typeof toggleVariants>) {
  return <TogglePrimitive.Root data-slot="toggle" className={cn(toggleVariants({ variant, size }), className)} {...props} />;
}

export { Toggle, toggleVariants };
