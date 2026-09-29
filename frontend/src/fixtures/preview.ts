// Browser preview (`npm run dev`) over synthetic fixtures captured by
// scripts/v2/companion_screens.py --dump-fixtures. Read-only: navigation
// and selection replay a captured read model, typing stays in the page,
// and every other command is refused. main.ts imports this module only
// in dev, so neither it nor the fixtures reach the production bundle.

import { useTransport, deliver, BRIDGE_VERSION, type Reply } from '../bridge/bridge';
import fixtures from './synthetic.json';

const views: Record<string, any> = fixtures.views;
const shell: any = { ...fixtures.shell };
let trainingTab = 'evidence';

function push(view: string, key = view) {
  shell.view = view;
  deliver({ bridge_version: BRIDGE_VERSION, type: 'snapshot', view, data: views[key], shell: { ...shell } });
}

function reply(command: string, p: any): Omit<Reply, 'request_id'> {
  switch (command) {
    case 'shell.hello':
      return { status: 'success', result: { shell: { ...shell } } };
    case 'nav.select':
      push(p.view);
      return { status: 'success' };
    case 'insights.subview':
      push('insights', p.subview === 'voice' ? 'insights_voice' : 'insights');
      return { status: 'success' };
    case 'models.subview':
      push('models', p.subview === 'training' ? `models_${trainingTab}` : 'models');
      return { status: 'success' };
    case 'training.tab':
      trainingTab = p.tab;
      push('models', `models_${p.tab}`);
      return { status: 'success' };
    case 'scratchpad.sync':
      return { status: 'success', result: fixtures.scratchpad_content };
    case 'scratchpad.edit':
      return { status: 'success', result: { version: p.base + 1, content: null } };
    case 'history.select':
    case 'training.select':
    case 'scratchpad.open':
    case 'scratchpad.cursor':
    case 'system.csp_violation':
      return { status: 'success' };
    default:
      return { status: 'refusal', reason_code: 'preview' };
  }
}

export function connectPreview() {
  useTransport({
    async send(envelope: any) {
      return JSON.stringify({ request_id: envelope.request_id, ...reply(envelope.command, envelope.payload) });
    },
  });
  setTimeout(() => push(shell.view ?? 'home'), 0);
}
