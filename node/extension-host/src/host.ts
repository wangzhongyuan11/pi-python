/**
 * Managed Node extension host (P15.5-T02).
 *
 * Booted by pi-python with `--config <json>`. Loads upstream TypeScript
 * extensions (Jiti when installed, Node type stripping otherwise), activates
 * each default factory with the bridged ExtensionAPI, then serves the stdio
 * request loop until Python shuts it down.
 */

import { readFileSync } from "node:fs";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";
import { ExtensionApi, type HostState } from "./api.ts";
import {
  CAPABILITIES,
  PROTOCOL_VERSION,
  parseFrame,
  type Frame,
  type Hello,
  type HelloAck,
  type Request,
  type Response,
} from "./protocol.ts";

interface ExtensionDescriptor {
  path: string;
  name?: string;
  error?: string;
  unsupported?: string[];
}

interface HostConfig {
  extensions: string[];
  generation: number;
  state?: Partial<HostState>;
}

const DEFAULT_STATE: HostState = {
  flags: {},
  activeTools: [],
  allTools: [],
  commands: [],
  thinkingLevel: "off",
  hasUI: false,
};

function send(frame: Frame | (Response & { id: string })): void {
  process.stdout.write(JSON.stringify(frame) + "\n");
}

let pythonCallId = 0;
const pythonPending = new Map<
  string,
  { resolve: (value: unknown) => void; reject: (error: Error) => void }
>();

function callPython(command: string, payload: object = {}): Promise<unknown> {
  pythonCallId += 1;
  const id = `host-${pythonCallId}`;
  return new Promise((resolve, reject) => {
    pythonPending.set(id, { resolve, reject });
    send({ type: "request", id, command, payload } as Request);
  });
}

async function loadModule(extensionPath: string): Promise<unknown> {
  try {
    const jitiModule = (await import("jiti")) as {
      createJiti: (id: string, options: object) => { import: (path: string) => Promise<unknown> };
    };
    const jiti = jitiModule.createJiti(import.meta.url, { moduleCache: false });
    return await jiti.import(pathToFileURL(extensionPath).href);
  } catch (error) {
    if (error instanceof Error && error.message.includes("Cannot find package")) {
      // Jiti is optional; Node type stripping (>=22.18) loads erasable TS.
      return await import(pathToFileURL(extensionPath).href);
    }
    throw error;
  }
}

const apis: ExtensionApi[] = [];
const loaded: ExtensionDescriptor[] = [];
const inflight = new Set<Promise<void>>();

async function activateExtension(extensionPath: string, state?: Partial<HostState>): Promise<void> {
  const descriptor: ExtensionDescriptor = { path: extensionPath, unsupported: [] };
  try {
    const module = (await loadModule(extensionPath)) as {
      default?: unknown;
    } | null;
    const factory = module?.default;
    if (typeof factory !== "function") {
      descriptor.error = `Extension does not export a valid factory function: ${extensionPath}`;
      loaded.push(descriptor);
      return;
    }
    const api = new ExtensionApi(callPython, { ...DEFAULT_STATE, ...(state ?? {}) });
    apis.push(api);
    try {
      await factory(api.build());
    } catch (error) {
      if (error instanceof UnsupportedCapabilityError) {
        descriptor.unsupported = [error.capability];
      } else {
        descriptor.error = error instanceof Error ? error.message : String(error);
      }
    }
    descriptor.name = extensionPath.replace(/\\/g, "/").split("/").pop() ?? extensionPath;
    loaded.push(descriptor);
  } catch (error) {
    descriptor.error = error instanceof Error ? error.message : String(error);
    loaded.push(descriptor);
  }
}

function serializeToolResult(raw: unknown): unknown {
  if (typeof raw !== "object" || raw === null) {
    return { content: [], details: null, isError: false };
  }
  const record = raw as Record<string, unknown>;
  return {
    content: Array.isArray(record.content) ? record.content : [],
    details: record.details ?? null,
    isError: record.isError === true,
  };
}

async function handleRequest(request: Request): Promise<unknown> {
  switch (request.command) {
    case "dispatch": {
      const event = String(request.payload.event ?? "");
      const payload = request.payload.payload;
      const context = request.payload.context ?? {};
      let result: unknown;
      for (const api of apis) {
        result = await api.dispatch(event, payload, context);
      }
      return { result };
    }
    case "ping":
      return { pong: true };
    case "execute_tool": {
      const name = String(request.payload.name ?? "");
      const toolCallId = String(request.payload.tool_call_id ?? "");
      const args = request.payload.args ?? {};
      for (const api of apis) {
        const tool = api.tools.get(name);
        if (tool) {
          const raw = await tool.execute(toolCallId, args, undefined, undefined, {
            hasUI: api.hasUI,
          });
          return serializeToolResult(raw);
        }
      }
      throw Object.assign(new Error(`unknown tool ${name}`), { code: "unknown_tool" });
    }
    case "run_command": {
      const commandName = String(request.payload.name ?? "");
      const args = String(request.payload.args ?? "");
      for (const api of apis) {
        const command = api.commands.get(commandName);
        if (command) {
          const result = await command.handler(args, request.payload.context ?? {});
          return { result: result ?? null };
        }
      }
      throw Object.assign(new Error(`unknown command ${commandName}`), {
        code: "unknown_command",
      });
    }
    case "run_shortcut": {
      const shortcut = String(request.payload.shortcut ?? "");
      for (const api of apis) {
        const record = api.shortcuts.get(shortcut);
        if (record) {
          await record.handler(request.payload.context ?? {});
          return { ok: true };
        }
      }
      throw Object.assign(new Error(`unknown shortcut ${shortcut}`), {
        code: "unknown_shortcut",
      });
    }
    case "update_state": {
      const patch = (request.payload.state ?? {}) as Partial<HostState>;
      for (const api of apis) {
        if (patch.flags) api.state.flags = { ...api.state.flags, ...patch.flags };
        if (patch.sessionName !== undefined) api.state.sessionName = patch.sessionName;
        if (patch.activeTools) api.state.activeTools = [...patch.activeTools];
        if (patch.allTools) api.state.allTools = [...patch.allTools];
        if (patch.commands) api.state.commands = [...patch.commands];
        if (patch.thinkingLevel) api.state.thinkingLevel = patch.thinkingLevel;
        if (patch.hasUI !== undefined) api.hasUI = patch.hasUI;
      }
      return { ok: true };
    }
    default:
      throw Object.assign(new Error(`unknown command ${request.command}`), {
        code: "unknown_command",
      });
  }
}

function respond(id: string, reply: Response): void {
  send(reply);
}

async function main(): Promise<void> {
  const configIndex = process.argv.indexOf("--config");
  if (configIndex === -1) {
    process.stderr.write("host requires --config <json>\n");
    process.exit(2);
  }
  const config = JSON.parse(readFileSync(process.argv[configIndex + 1], "utf8")) as HostConfig;
  const readline = createInterface({ input: process.stdin, terminal: false });
  let handshakeComplete = false;

  const queue: string[] = [];
  let waiting: ((line: string) => void) | null = null;
  readline.on("line", (line) => {
    if (waiting) {
      const resolve = waiting;
      waiting = null;
      resolve(line);
    } else {
      queue.push(line);
    }
  });
  const nextLine = (): Promise<string> =>
    new Promise((resolve) => {
      if (queue.length > 0) {
        resolve(queue.shift() as string);
      } else {
        waiting = resolve;
      }
    });

  const closed = new Promise<void>((resolve) => {
    readline.on("close", () => resolve());
  });

  while (true) {
    const line = await Promise.race([nextLine(), closed.then(() => null)]);
    if (line === null) {
      process.exit(0);
    }
    if (line.trim() === "") continue;
    let frame: Frame;
    try {
      frame = parseFrame(line);
    } catch (error) {
      if (error instanceof ProtocolError && !handshakeComplete) {
        process.stderr.write(`${error.code}: ${error.message}\n`);
        process.exit(2);
      }
      continue;
    }
    if (!handshakeComplete) {
      if (frame.type !== "hello") {
        process.stderr.write(`expected hello, got ${frame.type}\n`);
        process.exit(2);
      }
      const hello = frame as Hello;
      if (hello.protocol !== PROTOCOL_VERSION) {
        send({
          type: "response",
          id: "handshake",
          ok: false,
          errorCode: "version_mismatch",
          error: `python speaks protocol ${hello.protocol}, host speaks ${PROTOCOL_VERSION}`,
        } as Response & { id: string });
        process.exit(2);
      }
      for (const extensionPath of config.extensions) {
        await activateExtension(extensionPath, config.state);
      }
      const ack: HelloAck = {
        type: "hello_ack",
        protocol: PROTOCOL_VERSION,
        host: "node",
        generation: hello.generation ?? 0,
        capabilities: [...CAPABILITIES],
        extensions: loaded as unknown as Array<Record<string, unknown>>,
      };
      send(ack);
      handshakeComplete = true;
      continue;
    }
    if (frame.type === "request") {
      const request = frame as Request;
      // Handle concurrently: a handler may itself await a Python round trip
      // (sendMessage, exec, ui), which must not block the read loop.
      const task = (async () => {
        try {
          if (request.command === "shutdown") {
            respond(request.id, { type: "response", id: request.id, ok: true, result: null });
            process.exit(0);
          }
          const result = await handleRequest(request);
          respond(request.id, { type: "response", id: request.id, ok: true, result });
        } catch (error) {
          const code = (error as { code?: string }).code ?? "handler_error";
          respond(request.id, {
            type: "response",
            id: request.id,
            ok: false,
            errorCode: code === "unknown_command" ? "unknown_command" : "handler_error",
            error: error instanceof Error ? error.message : String(error),
          });
        }
      })();
      inflight.add(task);
      void task.finally(() => inflight.delete(task));
      continue;
    }
    if (frame.type === "response") {
      const response = frame as Response;
      const pending = pythonPending.get(response.id);
      if (pending) {
        pythonPending.delete(response.id);
        if (response.ok) {
          pending.resolve(response.result);
        } else {
          pending.reject(new Error(response.error ?? response.errorCode ?? "python call failed"));
        }
      }
    }
  }
}

main().catch((error: unknown) => {
  process.stderr.write(error instanceof Error ? error.stack ?? error.message : String(error));
  process.exit(1);
});
