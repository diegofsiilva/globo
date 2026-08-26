"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

function Table({ className, containerClassName, ...props }: React.ComponentProps<"table"> & { containerClassName?: string }) {
  return <div className={cn("relative w-full overflow-x-auto", containerClassName)}><table className={cn("w-full caption-bottom text-xs", className)} {...props} /></div>;
}
const TableHeader = ({ className, ...props }: React.ComponentProps<"thead">) => <thead className={cn("[&_tr]:border-b", className)} {...props} />;
const TableBody = ({ className, ...props }: React.ComponentProps<"tbody">) => <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
const TableRow = ({ className, ...props }: React.ComponentProps<"tr">) => <tr className={cn("border-b border-border transition-colors duration-[160ms] hover:bg-surface-raised/70 motion-reduce:transition-none", className)} {...props} />;
const TableHead = ({ className, ...props }: React.ComponentProps<"th">) => <th className={cn("h-10 px-3 text-left align-middle font-mono text-[9px] font-medium uppercase tracking-[0.09em] whitespace-nowrap text-muted-foreground", className)} {...props} />;
const TableCell = ({ className, ...props }: React.ComponentProps<"td">) => <td className={cn("px-3 py-3 align-middle whitespace-nowrap", className)} {...props} />;
const TableCaption = ({ className, ...props }: React.ComponentProps<"caption">) => <caption className={cn("mt-3 text-left text-xs text-muted-foreground", className)} {...props} />;

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption };
