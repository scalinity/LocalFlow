import { mount } from 'svelte';
import App from './app/App.svelte';
import './styles/tokens.css';
import './styles/base.css';
import { connectNative, nativeAvailable } from './bridge/bridge';

async function boot() {
  if (nativeAvailable()) {
    connectNative();
  } else if (import.meta.env.DEV) {
    // Browser preview only: synthetic fixtures, never part of the
    // production bundle (this branch is removed from `vite build`).
    const { connectPreview } = await import('./fixtures/preview');
    connectPreview();
  }
  mount(App, { target: document.getElementById('app')! });
}

boot();
