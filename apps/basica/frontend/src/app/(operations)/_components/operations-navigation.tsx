"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { navigationStyles as styles } from "./operations-navigation.styles";

type NavigationItem = {
  badge?: string;
  href: string;
  index: string;
  label: string;
};

const navigationItems: readonly NavigationItem[] = [
  { href: "/agora", index: "01", label: "Agora", badge: "3" },
  { href: "/explorar", index: "02", label: "Explorar" },
  { href: "/comparar", index: "03", label: "Comparar" },
  { href: "/hipoteses", index: "04", label: "Hipóteses", badge: "4" },
  { href: "/timeline", index: "05", label: "Timeline" },
  { href: "/recorte", index: "06", label: "Recorte" },
];

/** Navegação primária reutilizável das páginas operacionais. */
export function OperationsNavigation() {
  const pathname = usePathname();

  return (
    <nav className={styles.navigation} aria-label="Navegação de monitoração">
      <ol className={styles.list}>
        {navigationItems.map((item) => {
          const active = pathname === item.href;

          return (
            <li key={item.href}>
              <Link
                className={clsx(styles.link, active && styles.active)}
                href={item.href}
                aria-current={active ? "page" : undefined}
              >
                <span className={styles.index}>{item.index}</span>
                <span className={styles.label}>{item.label}</span>
                {item.badge && (
                  <span className={styles.badge} aria-label={`${item.badge} pendências`}>
                    {item.badge}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
