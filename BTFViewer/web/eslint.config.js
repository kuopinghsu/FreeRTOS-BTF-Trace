import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";

export default [
  js.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        __APP_VERSION__: "readonly",
        __BUILD_DATE__: "readonly",
        Buffer: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { "argsIgnorePattern": "^_" }],
      "no-undef": "warn",
      "no-console": "off",
      "vue/multi-word-component-names": "off",
      // Rich report/chat fragments are sanitized before they reach templates.
      "vue/no-v-html": "off",
      "semi": ["error", "never"],
      "quotes": ["error", "single", { "avoidEscape": true }],
      "vue/html-quotes": ["error", "double"],
    },
  },
];
