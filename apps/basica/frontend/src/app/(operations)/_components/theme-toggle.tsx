"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Alterna o tema resolvido e evita diferenças entre HTML estático e hidratação. */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );

  useEffect(() => {
    if (!mounted || !resolvedTheme) return;
    const color = resolvedTheme === "dark" ? "#09090b" : "#f3f2ef";
    document
      .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
      .forEach((meta) => meta.setAttribute("content", color));
  }, [mounted, resolvedTheme]);

  const dark = mounted && resolvedTheme === "dark";
  const nextTheme = dark ? "light" : "dark";
  const label = mounted ? `Usar modo ${dark ? "claro" : "escuro"}` : "Alternar tema";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={label}
          onClick={() => setTheme(nextTheme)}
          className="h-8 min-h-8 gap-2 px-3 font-mono text-[9px] uppercase tracking-[0.11em]"
        >
          {dark ? <Moon aria-hidden="true" /> : <Sun aria-hidden="true" />}
          <span className="hidden xl:inline">{dark ? "Modo escuro" : "Modo claro"}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
