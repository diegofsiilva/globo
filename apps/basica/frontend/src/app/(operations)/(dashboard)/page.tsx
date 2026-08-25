import { redirect } from "next/navigation";

/** Encaminha a entrada do dashboard para a tela operacional Agora. */
export default function HomePage() {
  redirect("/agora");
}
