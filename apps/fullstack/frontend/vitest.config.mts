import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  define: {
    "process.env.NEXT_PUBLIC_API_URL": JSON.stringify("http://api.test"),
    "process.env.NEXT_PUBLIC_HYPOTHESES_SOURCE": JSON.stringify("api"),
  },
  test: {
    environment: "jsdom",
    include: ["tests/contracts/**/*.test.{ts,tsx}", "tests/ui/**/*.test.{ts,tsx}"],
    setupFiles: ["./tests/setup.ts"],
    clearMocks: true,
    restoreMocks: true,
  },
});
