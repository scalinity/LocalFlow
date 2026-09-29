import { call, onPush, type Reply } from '../bridge/bridge';

export type Route =
  | 'home'
  | 'history'
  | 'insights'
  | 'dictionary'
  | 'snippets'
  | 'styles'
  | 'transforms'
  | 'scratchpad'
  | 'models'
  | 'diagnostics';

export interface Shell {
  view: string;
  theme: 'system' | 'light' | 'dark';
  sidebar_collapsed: boolean;
  engine: { asr: string | null; cleanup: string | null };
  dictation_key: string | null;
  version: string | null;
  dismissed: string[];
  onboarding_seen: boolean;
  name: string | null;
}

interface AppState {
  connected: boolean;
  route: Route;
  settingsOpen: boolean;
  settingsSection: string;
  shell: Shell;
  views: Record<string, any>;
  seq: number;
}

export const app: AppState = $state({
  connected: false,
  route: 'home',
  settingsOpen: false,
  settingsSection: 'general',
  shell: {
    view: 'home',
    theme: 'system',
    sidebar_collapsed: false,
    engine: { asr: null, cleanup: null },
    dictation_key: null,
    version: null,
    dismissed: [],
    onboarding_seen: false,
    name: null,
  },
  views: {},
  seq: 0,
});

type EventHandler = (payload: any) => void;
const eventHandlers = new Map<string, Set<EventHandler>>();

/** Subscribe to a named Python event (e.g. a Paste Again pick ending). */
export function onEvent(name: string, fn: EventHandler): () => void {
  if (!eventHandlers.has(name)) eventHandlers.set(name, new Set());
  eventHandlers.get(name)!.add(fn);
  return () => eventHandlers.get(name)?.delete(fn);
}

onPush((msg) => {
  if (msg.type === 'snapshot') {
    if (typeof msg.seq === 'number' && msg.seq <= app.seq) return;
    app.seq = msg.seq ?? app.seq;
    if (msg.shell) app.shell = msg.shell;
    if (msg.view && 'data' in msg) app.views[msg.view] = msg.data;
    app.connected = true;
  } else if (msg.type === 'event') {
    for (const fn of eventHandlers.get(msg.name) ?? []) fn(msg.payload);
  }
});

const routeListeners = new Set<(r: Route) => void>();

/** Called after every route change (e.g. the canvas scrolls to the top). */
export function onRoute(fn: (r: Route) => void): () => void {
  routeListeners.add(fn);
  return () => routeListeners.delete(fn);
}

export async function navigate(route: Route) {
  const changed = app.route !== route;
  app.route = route;
  if (changed) for (const fn of routeListeners) fn(route);
  await call('nav.select', { view: route });
}

export async function openSettings(section = 'general') {
  app.settingsSection = section;
  app.settingsOpen = true;
  await call('nav.select', { view: 'settings' });
}

export async function closeSettings() {
  app.settingsOpen = false;
  await call('nav.select', { view: app.route });
}

export function view<T = any>(name: string): T | undefined {
  return app.views[name] as T | undefined;
}

export async function act(command: string, payload: object = {}): Promise<Reply> {
  return call(command, payload);
}

export async function hello() {
  const r = await call('shell.hello', {});
  if (r.status === 'success' && r.result) {
    app.shell = r.result.shell;
    const v = r.result.shell.view;
    if (v && v !== 'settings') app.route = v as Route;
  }
  return r;
}
