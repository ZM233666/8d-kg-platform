import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  // 让前端可读取仓库根目录 .env（例如 VITE_NEO4J_*）
  envDir: '..',
  plugins: [react()],
  server: {
    port: 5172,
    strictPort: true, // 5172 被占用时不自动跳到 5173（避免与其它项目冲突）
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
