/**
 * Module customization hooks (P15.5-T02).
 *
 * Registered via node:module.register before the host boots. Resolution of
 * upstream "@earendil-works/*" specifiers is redirected to in-host stubs so
 * extensions that import TUI values fail with a structured unsupported
 * capability instead of a module-not-found crash.
 */

import { register } from "node:module";
import { pathToFileURL } from "node:url";

register("./hooks.mjs", import.meta.url);

export const VIRTUAL_PREFIX = "pi-python-virtual:";
const UPSTREAM_PREFIX = "@earendil-works/";

export async function resolve(specifier: string, context: { parentURL?: string | null }, next: (specifier: string, context: object) => Promise<object>) {
  if (specifier.startsWith(UPSTREAM_PREFIX)) {
    return { url: `${VIRTUAL_PREFIX}${specifier}`, shortCircuit: true };
  }
  return next(specifier, context);
}

export async function load(url: string, context: object, next: (url: string, context: object) => Promise<object>) {
  if (url.startsWith(VIRTUAL_PREFIX)) {
    const specifier = url.slice(VIRTUAL_PREFIX.length);
    return {
      format: "module",
      source: `const unsupported = new Proxy({}, { get(_t, property) { throw new Error("unsupported_capability: ${"upstream_tui_values"}: ${specifier}." + String(property)); } }); export default unsupported;`,
      shortCircuit: true,
    };
  }
  return next(url, context);
}

export { pathToFileURL };
