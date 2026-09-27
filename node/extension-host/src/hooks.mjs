/**
 * Module customization hooks (P15.5-T02).
 *
 * Resolution of upstream "@earendil-works/*" specifiers is redirected to a
 * stub whose property access throws a structured unsupported-capability
 * error. Type-only imports are erased by type stripping before resolution, so
 * only value imports (TUI components, host internals) ever hit this path.
 */

const VIRTUAL_PREFIX = "pi-python-virtual:";
const UPSTREAM_PREFIX = "@earendil-works/";

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(UPSTREAM_PREFIX)) {
    return { url: `${VIRTUAL_PREFIX}${specifier}`, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (url.startsWith(VIRTUAL_PREFIX)) {
    const specifier = JSON.stringify(url.slice(VIRTUAL_PREFIX.length));
    const source =
      "const unsupported = new Proxy({}, { get() {" +
      " throw new Error('unsupported_capability: upstream_tui_values: ' + " +
      specifier +
      " + ' cannot cross the process boundary (ADR 0009)'); } });" +
      " export default unsupported;";
    return { format: "module", source, shortCircuit: true };
  }
  return nextLoad(url, context);
}
