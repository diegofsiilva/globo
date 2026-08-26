"use client";

import clsx from "clsx";
import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { navigationItems } from "./navigation-items";
import { useOperationsUi } from "./operations-ui-context";
import { navigationStyles as styles } from "./operations-navigation.styles";

/** Navegação primária reutilizável das páginas operacionais. */
export function OperationsNavigation() {
  const pathname = usePathname();

  return (
    <nav className={styles.navigation} aria-label="Navegação de monitoração">
      <NavigationLinks pathname={pathname} />
    </nav>
  );
}

/** Navegação em drawer para viewports onde a sidebar não cabe. */
export function MobileOperationsNavigation() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          className={styles.menuButton}
          variant="ghost"
          size="icon"
          aria-label="Abrir menu de navegação"
        >
          <Menu aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className={styles.drawer}>
        <SheetHeader>
          <SheetTitle>Monitoração Agêntica</SheetTitle>
          <SheetDescription>Escolha uma etapa da investigação operacional.</SheetDescription>
        </SheetHeader>
        <nav aria-label="Navegação móvel de monitoração" className={styles.drawerNavigation}>
          <NavigationLinks pathname={pathname} onNavigate={() => setOpen(false)} />
        </nav>
      </SheetContent>
    </Sheet>
  );
}

function NavigationLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const { hrefWithDemoState } = useOperationsUi();
  return (
    <ol className={styles.list}>
      {navigationItems.map((item) => {
        const active = pathname === item.href;
        return (
          <li key={item.href}>
            <Link
              className={clsx(styles.link, active && styles.active)}
              href={hrefWithDemoState(item.href)}
              aria-current={active ? "page" : undefined}
              onClick={onNavigate}
            >
              <span className={styles.index}>{item.index}</span>
              <span className={styles.label}>{item.label}</span>
              {item.badge && (
                <Badge className={styles.badge} aria-label={`${item.badge} pendências`}>
                  {item.badge}
                </Badge>
              )}
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
