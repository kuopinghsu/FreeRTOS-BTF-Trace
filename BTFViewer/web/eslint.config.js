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
      },
    },
    rules: {
      "no-unused-vars": ["warn", { "argsIgnorePattern": "^_" }],
      "no-undef": "warn",
      "no-console": "off",
      "vue/multi-word-component-names": "off",
    },
  },
];
