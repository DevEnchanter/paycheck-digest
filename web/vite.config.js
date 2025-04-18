
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins:[react()],
  css:{postcss:'./postcss.config.js'},
  server:{proxy:{'/digest':'http://localhost:8080','/history':'http://localhost:8080','/health':'http://localhost:8080','/analytics':'http://localhost:8080'}}
})
