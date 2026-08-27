import * as React from "react";
import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-11 w-full min-w-0 touch-manipulation border border-input bg-background px-3 py-2 text-base text-foreground outline-none transition-[border-color,box-shadow,background-color] duration-[160ms] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-45 md:h-9 md:text-xs motion-reduce:transition-none",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
