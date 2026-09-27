/**
 * Node extension host wire protocol (P15.5-T01).
 *
 * Mirrors src/pi_coding_agent/node_host/models.py: one protocol version, a
 * hello/hello_ack handshake, and correlated request/response frames in both
 * directions. Unknown commands and unknown capabilities fail with typed error
 * codes instead of being ignored.
 */

export const PROTOCOL_VERSION = 1;

export const CAPABILITIES: readonly string[] = [
  "register_tool",
  "register_command",
  "register_flag",
  "register_shortcut",
  "register_message_renderer",
  "register_entry_renderer",
  "events",
  "actions",
  "ui",
  "exec",
];

export type ErrorCode =
  | "version_mismatch"
  | "unknown_command"
  | "unknown_capability"
  | "handler_error"
  | "invalid_frame";

export interface Hello {
  type: "hello";
  protocol: number;
  generation: number;
  cwd: string;
}

export interface HelloAck {
  type: "hello_ack";
  protocol: number;
  host: string;
  generation: number;
  capabilities: string[];
  extensions: Array<Record<string, unknown>>;
}

export interface Request {
  type: "request";
  id: string;
  command: string;
  payload: Record<string, unknown>;
}

export interface Response {
  type: "response";
  id: string;
  ok: boolean;
  result?: unknown;
  errorCode?: string;
  error?: string;
}

export type Frame = Hello | HelloAck | Request | Response;

export class ProtocolError extends Error {
  readonly code: ErrorCode;

  constructor(code: ErrorCode, message: string) {
    super(`${code}: ${message}`);
    this.code = code;
  }
}

export function negotiate(hello: Hello): HelloAck {
  if (hello.protocol !== PROTOCOL_VERSION) {
    throw new ProtocolError(
      "version_mismatch",
      `python speaks protocol ${hello.protocol}, host speaks ${PROTOCOL_VERSION}`,
    );
  }
  return {
    type: "hello_ack",
    protocol: PROTOCOL_VERSION,
    host: "node",
    generation: hello.generation ?? 0,
    capabilities: [...CAPABILITIES],
    extensions: [],
  };
}

export function parseFrame(line: string): Frame {
  let payload: unknown;
  try {
    payload = JSON.parse(line);
  } catch (error) {
    throw new ProtocolError("invalid_frame", `not JSON: ${String(error)}`);
  }
  if (typeof payload !== "object" || payload === null) {
    throw new ProtocolError("invalid_frame", "frame is not an object");
  }
  const kind = (payload as { type?: unknown }).type;
  if (kind === "hello") return payload as Hello;
  if (kind === "hello_ack") return payload as HelloAck;
  if (kind === "request") {
    const request = payload as Request;
    if (typeof request.id !== "string" || typeof request.command !== "string") {
      throw new ProtocolError("invalid_frame", "request requires id and command");
    }
    return request;
  }
  if (kind === "response") {
    const response = payload as Response;
    if (typeof response.id !== "string") {
      throw new ProtocolError("invalid_frame", "response requires id");
    }
    return response;
  }
  throw new ProtocolError("invalid_frame", `unknown frame type ${String(kind)}`);
}
