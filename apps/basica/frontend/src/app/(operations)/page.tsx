import { redirect } from "next/navigation";

/** Encaminha a rota raiz para o monitor de eventos. */
export default function HomePage() {
  redirect("/monitor");
}
