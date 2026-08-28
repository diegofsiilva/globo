/** Configuração de build e exportação estática do dashboard. */
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  // Gera /rota/index.html, formato resolvido diretamente pelo website do S3.
  trailingSlash: true,
  experimental: {
    // O runner CLI do Next 16.3 encerra antes de capturar o JSON do
    // `tsc --showConfig` neste Node 20; a API usa o mesmo compilador e evita
    // essa falha de infraestrutura sem desabilitar a verificação de tipos.
    useTypeScriptCli: false,
  },
};

export default nextConfig;
