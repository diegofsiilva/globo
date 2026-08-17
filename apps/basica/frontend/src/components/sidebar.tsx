"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SIDEBAR_ITEMS = [
  { id: "agora", label: "Agora", href: "/agora" },
  { id: "explorar", label: "Explorar", href: "/explorar" },
  { id: "comparar", label: "Comparar", href: "/comparar" },
  { id: "hipoteses", label: "Hipóteses", href: "/hipoteses" },
  { id: "timeline", label: "Timeline", href: "/timeline" },
  { id: "recorte", label: "Recorte", href: "/recorte" },
] as const;

type SidebarItemId = (typeof SIDEBAR_ITEMS)[number]["id"];
type NotificationCounts = Partial<Record<SidebarItemId, number>>;

type SidebarProps = {
  /** Quantidade exibida no marcador de cada aba. Valores menores que 1 são ocultados. */
  notificationCounts?: NotificationCounts;
};

const DEFAULT_NOTIFICATION_COUNTS: NotificationCounts = {
  agora: 3,
  hipoteses: 4,
};

/** Navegação principal entre as seis áreas de análise da plataforma. */
export function Sidebar({
  notificationCounts = DEFAULT_NOTIFICATION_COUNTS,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <nav>
        <ol className="sidebar-list">
          {SIDEBAR_ITEMS.map((item, index) => {
            const notificationCount = notificationCounts[item.id] ?? 0;
            const isActive =
              pathname === item.href ||
              pathname.startsWith(`${item.href}/`) ||
              (item.id === "agora" && pathname === "/");

            return (
              <li className="sidebar-item" key={item.id}>
                <Link
                  className={`sidebar-link${isActive ? " is-active" : ""}`}
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                >
                  <span className="sidebar-index" aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="sidebar-label">{item.label}</span>
                  {notificationCount > 0 && (
                    <span
                      className="sidebar-notification"
                      aria-label={`${notificationCount} ${notificationCount === 1 ? "notificação" : "notificações"}`}
                    >
                      {notificationCount}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>
    </aside>
  );
}
