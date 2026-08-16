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
    // P2-13: 生产构建优化(产物体积/源码泄露/构建速度)
    target: 'es2019', // 对齐目标浏览器语法, 避免过新特性导致旧端白屏
    minify: 'terser', // 比默认 esbuild 更激进的压缩(去 console/debugger)
    sourcemap: false, // 生产不产出 sourcemap, 避免源码泄露
    cssCodeSplit: true, // 样式按 chunk 拆分, 提升缓存命中
    reportCompressedSize: false, // 关闭压缩体积上报, 加速构建
    assetsInlineLimit: 4096, // 小于 4KB 的资源内联为 base64, 减少请求数
    terserOptions: {
      compress: {
        drop_console: true, // 生产构建剔除 console.* (性能+避免信息泄露)
        drop_debugger: true,
      },
    },
    // 复核 P1-9: 警告阈值回归 1000(原 3000 掩盖包体肥胖); 配合 manualChunks 分包
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        // P1-9 分包: 框架核心 vendor + SQL 编辑器 editor 独立 chunk(仅工作台页加载)
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return
          if (id.includes('codemirror') || id.includes('@codemirror')) return 'editor'
          if (id.includes('/vue') || id.includes('vue-router') || id.includes('pinia')) return 'vendor'
        },
      },
    },
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
