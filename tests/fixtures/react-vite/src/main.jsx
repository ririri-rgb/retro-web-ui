import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import '../../../../skills/retro-web-ui/assets/theme-kit/retro-base.css';
import '../../../../skills/retro-web-ui/assets/theme-kit/japanese-freeware-2000s.css';
import './fixture.css';

createRoot(document.querySelector('#root')).render(<StrictMode><App /></StrictMode>);

if (new URLSearchParams(window.location.search).has('selftest')) {
  const observer = new MutationObserver(() => {
    const status = document.querySelector('[data-fixture-status]');
    if (status?.textContent === '稼働中') {
      document.documentElement.dataset.selftest = 'passed';
      observer.disconnect();
    }
  });
  observer.observe(document.querySelector('#root'), { subtree: true, childList: true, characterData: true });
  window.setTimeout(() => document.querySelector('[aria-pressed="false"]')?.click(), 50);
}
