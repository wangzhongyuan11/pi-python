// Registers the resolution hooks before the host boots (P15.5-T02).
import { register } from "node:module";

register("./hooks.mjs", import.meta.url);
