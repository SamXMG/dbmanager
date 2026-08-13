<script setup lang="ts">
// P1-10: 统一 SVG 功能图标(Lucide 风格手写 path, 16/20/24px, currentColor)
// 替代散落的 emoji 功能图标(📋👁️ƒ🔔🗄️📁🌓等); 配色一律走 var(--text*), 严禁紫→粉渐变
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 16 })

const PATHS: Record<string, string[]> = {
  table: [
    '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    '<path d="M3 9h18"/>',
    '<path d="M9 21V9"/>',
  ],
  view: [
    '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/>',
    '<circle cx="12" cy="12" r="3"/>',
  ],
  database: [
    '<ellipse cx="12" cy="5" rx="9" ry="3"/>',
    '<path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>',
    '<path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
  ],
  folder: [
    '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.6 3.9A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>',
  ],
  code: [
    '<polyline points="16 18 22 12 16 6"/>',
    '<polyline points="8 6 2 12 8 18"/>',
  ],
  bell: [
    '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>',
    '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  ],
  sun: [
    '<circle cx="12" cy="12" r="4"/>',
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  ],
  refresh: [
    '<path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/>',
    '<path d="M21 3v5h-5"/>',
    '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/>',
    '<path d="M3 21v-5h5"/>',
  ],
  x: ['<path d="M18 6 6 18M6 6l12 12"/>'],
  check: ['<polyline points="20 6 9 17 4 12"/>'],
  key: [
    '<circle cx="7.5" cy="15.5" r="4.5"/>',
    '<path d="m10.7 12.3 9-9M16 7l3 3M13 10l2.5 2.5"/>',
  ],
  user: [
    '<circle cx="12" cy="8" r="4"/>',
    '<path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/>',
  ],
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
       aria-hidden="true" focusable="false" v-html="PATHS[name]?.join('') || ''"></svg>
</template>
