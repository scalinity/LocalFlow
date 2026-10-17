import { defineConfig } from "vite";
export default defineConfig({ clearScreen: false, optimizeDeps: { include: ["@tauri-apps/api/core"] }, server: { host: "localhost", port: 1431, strictPort: true, watch: { ignored: ["**/src-tauri/**", "**/verification/**"] } } });
