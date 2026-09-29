import { useTransport, deliver, BRIDGE_VERSION } from '../bridge/bridge';

export function connectPreview() {
  useTransport({
    async send(envelope: any) {
      return JSON.stringify({ request_id: envelope.request_id, status: 'success', result: { pong: true, preview: true } });
    },
  });
  setTimeout(() => deliver({ bridge_version: BRIDGE_VERSION, type: 'snapshot', view: 'shell', data: { preview: true } }), 0);
}
