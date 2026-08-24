/** Configuração de build e exportação estática do dashboard. */
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  // Gera /rota/index.html, formato resolvido diretamente pelo website do S3.
  trailingSlash: true,
};

export default nextConfig;
