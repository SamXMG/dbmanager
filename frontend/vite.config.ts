import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// dbmanager 前端迁移: 产物为纯静态 dist/, 由后端 python http.server serve
// base='./' 相对路径 -> 部署在子路径(/v2)也能跑; assetsDir='assets' 对齐后端白名单
export default defineConfig({
  base: './',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    chunkSizeWarningLimit: 3000, // CodeMirror 体积小, 不刷警告
  },
  server: {
    port: 5173,
    proxy: {
      // 开发模式: /api 转发到现有 python 后端(8770)
      '/api': {
        target: 'http://127.0.0.1:8770',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
  },
})
