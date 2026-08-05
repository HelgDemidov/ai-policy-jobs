import js from "@eslint/js";
import globals from "globals";

// Scoped to web/public/*.js — the vanilla browser JS planned in
// docs/tech_specs/vercel-web-gui/spec.md. No files match yet (application
// code not built); this just has the tool ready for when it lands.
export default [
  // Global ignores — this repo is mostly Python; without this ESLint walks
  // .venv/'s bundled vendor JS (transitive deps ship some) too.
  { ignores: [".venv/**", "node_modules/**", "data/**", "**/__pycache__/**"] },
  js.configs.recommended,
  {
    files: ["web/public/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: globals.browser,
    },
  },
];
