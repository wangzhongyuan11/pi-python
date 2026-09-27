/**
 * An upstream-style Pi extension, loaded unmodified by the pi-python Node
 * host. Uses the documented ExtensionAPI surface only: a TypeBox tool, a
 * slash command, a CLI flag, lifecycle hooks, session actions, and a UI
 * dialog. Anything that cannot cross the process boundary is reported
 * through the structured unsupported path instead of failing the extension.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.registerFlag("--official", { type: "boolean", default: false });

  pi.registerTool({
    name: "official_weather",
    label: "Official weather",
    description:
      "Returns a deterministic weather report for a city, proving the TypeScript tool executed inside the Node host.",
    parameters: {
      type: "object",
      properties: { city: { type: "string", description: "City name" } },
      required: ["city"],
    },
    execute: async (_id, params) => ({
      content: [
        {
          type: "text",
          text: `Weather for ${params.city}: 21C, clear skies (reported by the official TypeScript extension).`,
        },
      ],
      details: { city: params.city, runtime: "node" },
    }),
  });

  pi.registerCommand("official-report", {
    description: "Reports the negotiated bridge status",
    handler: async (args) => {
      const flag = pi.getFlag("--official");
      const tools = pi.getActiveTools();
      await pi.sendMessage({
        customType: "official-status",
        content: `flag:${String(flag)} tools:${tools.length}`,
      });
      return args
        ? `official:${args} flag:${String(flag)}`
        : `official:ready flag:${String(flag)}`;
    },
  });

  pi.on("agent_start", () => {
    pi.appendEntry("official-lifecycle", { phase: "agent_start" });
  });

  pi.on("tool_call", (event) => {
    if (event.toolName === "official_weather") {
      // Prove control hooks can rewrite arguments crossing the bridge.
      const input = event.input as { city?: string };
      if (input.city === "capital") {
        input.city = "Berlin";
        return { input: event.input };
      }
    }
    return undefined;
  });

  pi.registerCommand("official-ask", {
    description: "Asks through the product UI",
    handler: async () => {
      const answer = await pi.ui.input("Official extension", "say anything");
      return `ui:${answer ?? "declined"}`;
    },
  });
}
