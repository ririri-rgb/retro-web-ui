const themes = new Set(['modern', 'windows-98', 'windows-xp', 'windows-7', 'japanese-freeware-2000s']);
const params = new URLSearchParams(location.search);
const requested = themes.has(params.get('theme')) ? params.get('theme') : 'windows-98';
const base = document.querySelector('#base-theme');
const selected = document.querySelector('#selected-theme');
const modern = document.querySelector('#modern-theme');
const picker = document.querySelector('#theme-picker');
const status = document.querySelector('#status');

function applyTheme(theme) {
  picker.value = theme;
  if (theme === 'modern') {
    document.body.removeAttribute('data-retro-theme');
    base.disabled = true;
    selected.removeAttribute('href');
    modern.disabled = false;
  } else {
    document.body.dataset.retroTheme = theme;
    base.disabled = false;
    selected.href = `../theme-kit/${theme}.css`;
    modern.disabled = true;
  }
}

applyTheme(requested);
picker.addEventListener('change', () => { location.search = `?theme=${picker.value}`; });

const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab) {
  tabs.forEach((item) => {
    const selectedState = item === tab;
    item.setAttribute('aria-selected', String(selectedState));
    document.querySelector(`#${item.getAttribute('aria-controls')}`).hidden = !selectedState;
  });
  tab.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const direction = ['ArrowDown', 'ArrowRight'].includes(event.key) ? 1 : -1;
    selectTab(tabs[(index + direction + tabs.length) % tabs.length]);
  });
});

document.querySelector('#run-now').addEventListener('click', () => { status.textContent = '同期を開始しました'; });
document.querySelector('#panel-settings').addEventListener('submit', (event) => {
  event.preventDefault();
  status.textContent = '設定を保存しました';
});

if (params.get('selftest') === '1') {
  document.querySelector('#run-now').click();
  document.querySelector('#tab-jobs').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }));
  document.querySelector('#panel-settings').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  const passed = status.textContent === '設定を保存しました'
    && document.querySelector('#tab-settings').getAttribute('aria-selected') === 'true'
    && document.activeElement === document.querySelector('#tab-settings')
    && !document.querySelector('#panel-settings').hidden;
  document.documentElement.dataset.selftest = passed ? 'passed' : 'failed';
}
