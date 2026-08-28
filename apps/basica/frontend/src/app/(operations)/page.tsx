import { redirect } from "next/navigation";

/** Encaminha a rota raiz para a primeira etapa da investigação operacional. */
export default function HomePage() {
  redirect("/agora");
}
