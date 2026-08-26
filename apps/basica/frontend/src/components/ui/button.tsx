import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import * as Slot from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 touch-manipulation items-center justify-center gap-2 whitespace-nowrap border text-[11px] font-semibold transition-[background-color,color,border-color,opacity,transform] duration-[160ms] outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-45 active:translate-y-px motion-reduce:transition-none motion-reduce:active:translate-y-0 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground hover:border-primary-hover hover:bg-primary-hover",
        destructive:
          "border-destructive bg-destructive text-white hover:bg-destructive/90",
        outline:
          "border-border-strong bg-transparent text-foreground hover:border-foreground/50 hover:bg-surface-raised",
        secondary:
          "border-border bg-secondary text-secondary-foreground hover:bg-surface-raised",
        ghost:
          "border-transparent bg-transparent text-muted-foreground hover:bg-surface-raised hover:text-foreground",
        link:
          "h-auto border-transparent bg-transparent p-0 text-primary underline-offset-4 hover:text-primary-hover hover:underline",
      },
      size: {
        default: "min-h-10 px-4 py-2",
        sm: "min-h-8 px-3 py-1.5 text-[10px]",
        lg: "min-h-11 px-5 py-2.5 text-xs",
        icon: "size-11 p-0",
        "icon-sm": "size-9 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
