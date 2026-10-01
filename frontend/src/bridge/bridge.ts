// The one channel between the view and LocalFlow's Python process.
//
// JS → Python: an allowlisted command with a JSON payload, answered once
// with a typed status. Python → JS: pushed messages (view snapshots and
// events) delivered to window.__lfBridge.receive. The view never names a
// Python method, a path or a query — only a command from the allowlist
// Python validates.

export const BRIDGE_VERSION = 1;

export type Status =
  | 'success'
  | 'refusal'
  | 'outcome_unknown'
  | 'cancelled'
  | 'stale'
  | 'unavailable'
  | 'error';

export interface Reply<T = any> {
  request_id: string;
  status: Status;
  result?: T;
  reason_code?: string;
}

export interface Pushed {
  bridge_version: number;
  type: 'snapshot' | 'event';
  [key: string]: any;
}

type Listener = (msg: Pushed) => void;

interface Transport {
  send(envelope: object): Promise<string>;
}

declare global {
  interface Window {
    webkit?: { messageHandlers?: { lf?: { postMessage(m: string): Promise<string> } } };
    __lfBridge?: { receive(json: string): void };
  }
}

const listeners = new Set<Listener>();
let transport: Transport | null = null;
let seq = 0;

export function nativeAvailable(): boolean {
  return !!window.webkit?.messageHandlers?.lf;
}

export function onPush(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function deliver(msg: Pushed) {
  for (const fn of listeners) {
    try {
      fn(msg);
    } catch (e) {
      console.error('[bridge] listener failed', e);
    }
  }
}

window.__lfBridge = {
  receive(json: string) {
    let msg: Pushed;
    try {
      msg = JSON.parse(json);
    } catch {
      return;
    }
    if (msg?.bridge_version !== BRIDGE_VERSION) return;
    deliver(msg);
  },
};

export function useTransport(t: Transport) {
  transport = t;
}

export async function call<T = any>(command: string, payload: object = {}): Promise<Reply<T>> {
  const request_id = `r${++seq}`;
  if (!transport) {
    return { request_id, status: 'unavailable', reason_code: 'no_transport' };
  }
  try {
    const raw = await transport.send({ bridge_version: BRIDGE_VERSION, request_id, command, payload });
    return JSON.parse(raw) as Reply<T>;
  } catch (e) {
    return { request_id, status: 'error', reason_code: 'bridge_failed' };
  }
}

export function connectNative() {
  const handler = window.webkit!.messageHandlers!.lf!;
  // The envelope crosses as one JSON string: Python parses exactly what
  // was sent, with no Objective-C value conversion in between.
  useTransport({ send: (envelope) => handler.postMessage(JSON.stringify(envelope)) });
}
