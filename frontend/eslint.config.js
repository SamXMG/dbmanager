// ESLint 9 flat config(路线图 P1-3)
// 门禁: eslint . --max-warnings 0; 存量问题在 M2 收敛
import pluginVue from 'eslint-plugin-vue'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import prettier from 'eslint-config-prettier'

export default [
  // 忽略构建产物与依赖
  { ignores: ['dist/**', 'node_modules/**'] },
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaVersion: 2022, sourceType: 'module' },
    },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      // 组件名单文件在工具类场景常见, 放宽
      'vue/multi-word-component-names': 'off',
      // 存量 any 较多, 先 warn 后逐步收敛为 error
      '@typescript-eslint/no-explicit-any': 'warn',
      // 模板内联样式(条件类名)允许
      'vue/no-v-html': 'off',
    },
  },
  prettier,
]
