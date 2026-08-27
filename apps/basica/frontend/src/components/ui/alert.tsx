import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative grid w-full grid-cols-[0_1fr] items-start gap-y-1 rounded-panel border px-4 py-3 text-sm has-[>svg]:grid-cols-[16px_1fr] has-[>svg]:gap-x-3 [&>svg]:size-4 [&>svg]:translate-y-0.5", {
  variants: {
    variant: {
      default: "border-border-strong bg-surface text-foreground",
      destructive: "border-destructive/50 bg-destructive/8 text-destructive",
      warning: "border-warning/50 bg-warning/8 text-warning",
    },
  },
  defaultVariants: { variant: "default" },
});

function Alert({ className, variant, ...props }: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}
const AlertTitle = ({ className, ...props }: React.ComponentProps<"div">) => <div className={cn("col-start-2 font-semibold", className)} {...props} />;
const AlertDescription = ({ className, ...props }: React.ComponentProps<"div">) => <div className={cn("col-start-2 leading-relaxed text-muted-foreground", className)} {...props} />;

export { Alert, AlertTitle, AlertDescription };
