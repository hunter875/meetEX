import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],build:{rollupOptions:{input:{dashboard:'dashboard.html',sidepanel:'sidepanel.html',background:'src/background/index.ts'},output:{entryFileNames:chunk=>chunk.name==='background'?'background.js':'assets/[name]-[hash].js'}}},test:{environment:'jsdom',include:['tests/**/*.test.ts']}});
