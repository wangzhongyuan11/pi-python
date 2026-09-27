/**
 * The ExtensionAPI implementation handed to upstream extension factories.
 *
 * Synchronous reads (flags, tools, session name, thinking level) are answered
 * from the state snapshot Python pushed with the handshake — the upstream API
 * is synchronous and must stay synchronous. Mutations forward to Python as
 * ordered requests; async upstream operations (exec, setModel, dialogs) await
 * the correlated response. Surfaces that cannot cross the process boundary
 * (ADR 0009) throw a structured unsupported error.
 */

import type { Request } from "./protocol.ts";

export type PythonCaller = (command: string, payload?: object) => Promise<unknown>;

export type EventHandler = (event: unknown, context: unknown) => unknown;

export interface HostState {
  flags: Record<string, boolean | string>;
  sessionName?: string;
  activeTools: string[];
  allTools: Array<Record<string, unknown>>;
  commands: Array<Record<string, unknown>>;
  thinkingLevel: string;
  hasUI: boolean;
}

export function fireAndForget(promise: Promise<unknown>): void {
  promise.catch(() => undefined);
}

const UNSUPPORTED = new Set([
  "registerProvider",
  "unregisterProvider",
  "registerMarkdownTransformer",
  "events",
]);

interface ToolRecord {
  name: string;
  execute: (toolCallId: string, params: unknown, signal: unknown, onUpdate: unknown, ctx: unknown) => Promise<unknown>;
}

interface CommandRecord {
  name: string;
  handler: (args: string, context: unknown) => Promise<unknown> | unknown;
}

interface ShortcutRecord {
  shortcut: string;
  handler: (context: unknown) => Promise<void> | void;
}

export class ExtensionApi {
  readonly handlers = new Map<string, EventHandler[]>();
  readonly tools = new Map<string, ToolRecord>();
  readonly commands = new Map<string, CommandRecord>();
  readonly shortcuts = new Map<string, ShortcutRecord>();
  state: HostState;
  hasUI: boolean;
  private readonly callPython: PythonCaller;

  constructor(callPython: PythonCaller, state: HostState) {
    this.callPython = callPython;
    this.state = state;
    this.hasUI = state.hasUI ?? false;
  }

  /** Build the object handed to extension factories. */
  build(): Record<string, unknown> {
    const api: Record<string, unknown> = {
      hasUI: this.hasUI,
      on: (event: string, handler: EventHandler) => {
        if (typeof event !== "string" || typeof handler !== "function") {
          throw new TypeError("on(event, handler) requires strings and functions");
        }
        const list = this.handlers.get(event) ?? [];
        list.push(handler);
        this.handlers.set(event, list);
      },
      registerTool: (tool: ToolRecord & Record<string, unknown>) => {
        if (typeof tool?.execute !== "function") {
          throw new TypeError("registerTool requires an execute function");
        }
        this.tools.set(tool.name, tool);
        // Forward the definition without functions; JSON.stringify drops them.
        return this.callPython("register_tool", { definition: JSON.parse(JSON.stringify(tool)) });
      },
      registerCommand: (name: string, options: { handler?: unknown; description?: string }) => {
        if (typeof options?.handler !== "function") {
          throw new TypeError("registerCommand requires a handler function");
        }
        this.commands.set(name, { name, handler: options.handler });
        return this.callPython("register_command", {
          name,
          options: { description: options.description },
        });
      },
      registerFlag: (name: string, options: { type?: string; default?: boolean | string }) =>
        this.callPython("register_flag", { name, options }),
      registerShortcut: (
        shortcut: string,
        options: { handler?: unknown; description?: string },
      ) => {
        if (typeof options?.handler !== "function") {
          throw new TypeError("registerShortcut requires a handler function");
        }
        this.shortcuts.set(shortcut, { shortcut, handler: options.handler });
        return this.callPython("register_shortcut", {
          shortcut,
          options: { description: options.description },
        });
      },
      registerMessageRenderer: (customType: string, renderer: unknown) => {
        if (typeof renderer !== "function") {
          throw new TypeError("registerMessageRenderer requires a renderer function");
        }
        return this.callPython("register_message_renderer", { customType, serialized: true });
      },
      registerEntryRenderer: (customType: string, renderer: unknown) => {
        if (typeof renderer !== "function") {
          throw new TypeError("registerEntryRenderer requires a renderer function");
        }
        return this.callPython("register_entry_renderer", { customType, serialized: true });
      },
      getFlag: (name: string) => this.state.flags[name],
      // Actions and session metadata: ordered fire-and-forget (void upstream).
      sendMessage: (message: unknown, options?: unknown) => {
        fireAndForget(this.callPython("send_message", { message, options }));
      },
      sendUserMessage: (content: unknown, options?: unknown) => {
        fireAndForget(this.callPython("send_user_message", { content, options }));
      },
      appendEntry: (customType: string, data?: unknown) => {
        fireAndForget(this.callPython("append_entry", { customType, data }));
      },
      setSessionName: (name: string) => {
        this.state.sessionName = name;
        fireAndForget(this.callPython("set_session_name", { name }));
      },
      getSessionName: () => this.state.sessionName,
      setLabel: (entryId: string, label?: string) => {
        fireAndForget(this.callPython("set_label", { entryId, label }));
      },
      // Async upstream operations await the correlated response.
      exec: (command: string, args: string[], options?: unknown) =>
        this.callPython("exec", { command, args, options }),
      getActiveTools: () => [...this.state.activeTools],
      getAllTools: () => this.state.allTools.map((tool) => ({ ...tool })),
      setActiveTools: (toolNames: string[]) => {
        this.state.activeTools = [...toolNames];
        fireAndForget(this.callPython("set_active_tools", { toolNames }));
      },
      getCommands: () => this.state.commands.map((command) => ({ ...command })),
      setModel: (model: unknown) => this.callPython("set_model", { model }),
      getThinkingLevel: () => this.state.thinkingLevel,
      setThinkingLevel: (level: string) => {
        this.state.thinkingLevel = level;
        fireAndForget(this.callPython("set_thinking_level", { level }));
      },
      // Serializable UI subset (T05).
      ui: {
        input: (title: string, placeholder?: string) =>
          this.callPython("ui_input", { title, placeholder }),
        confirm: (title: string, message: string) =>
          this.callPython("ui_confirm", { title, message }),
        select: (title: string, options: string[]) =>
          this.callPython("ui_select", { title, options }),
        notify: (message: string, level?: string) => {
          fireAndForget(this.callPython("ui_notify", { message, level }));
        },
        setStatus: (message?: string) => {
          fireAndForget(this.callPython("ui_status", { message }));
        },
      },
    };
    for (const name of UNSUPPORTED) {
      api[name] = () => {
        throw new Error(
          `unsupported_capability: ${name} cannot cross the process boundary (ADR 0009)`,
        );
      };
    }
    return api;
  }

  async dispatch(event: string, payload: unknown, context: unknown): Promise<unknown> {
    const handlers = this.handlers.get(event) ?? [];
    let last: unknown;
    for (const handler of handlers) {
      last = await handler(payload, context);
    }
    return last;
  }

  hasHandlersFor(events: readonly string[]): boolean {
    return events.some((event) => (this.handlers.get(event) ?? []).length > 0);
  }

  requestFrame(command: string, payload: Record<string, unknown>): Request {
    return { type: "request", id: "", command, payload };
  }
}
