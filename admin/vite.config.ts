import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // 产物由后端挂在 /admin 子路径下，用相对路径最稳
  base: "./",
  build: {
    // 直接构建进后端的静态目录：少一步手工拷贝，也不会堆历史产物
    // （emptyOutDir 会先清空，等价于自动做了"清理旧包"）
    outDir: "../app/static_admin",
    emptyOutDir: true,
  },
  server: {
    port: 5174,
  },
});
