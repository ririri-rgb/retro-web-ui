import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Tab,
  Tabs,
  TextField,
  ThemeProvider,
  createTheme,
} from '@mui/material';

const theme = createTheme({
  typography: { fontFamily: '"MS Sans Serif", Tahoma, system-ui, sans-serif', fontSize: 11 },
  shape: { borderRadius: 0 },
  palette: { primary: { main: '#000080' }, background: { paper: '#c0c0c0' }, text: { primary: '#000' } },
  components: {
    MuiButton: { styleOverrides: { root: { minHeight: 23, minWidth: 72, borderRadius: 0, borderColor: '#000', color: '#000', padding: '2px 11px', textTransform: 'none', boxShadow: 'inset -1px -1px #000, inset 1px 1px #fff, inset -2px -2px #808080, inset 2px 2px #dfdfdf' } } },
    MuiCheckbox: { styleOverrides: { root: { color: '#000', padding: 2 } } },
    MuiDialog: { styleOverrides: { paper: { border: '2px solid #c0c0c0', borderRadius: 0, background: '#c0c0c0', boxShadow: 'inset 1px 1px #fff, inset -1px -1px #000, inset 2px 2px #dfdfdf, inset -2px -2px #808080' } } },
    MuiDialogTitle: { styleOverrides: { root: { margin: 2, minHeight: 22, padding: '3px 5px', background: 'linear-gradient(90deg, #000080, #1084d0)', color: '#fff', fontSize: 11, fontWeight: 700 } } },
    MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 0, background: '#fff', fontSize: 11 }, input: { padding: '4px 6px' }, notchedOutline: { borderColor: '#000' } } },
    MuiTab: { styleOverrides: { root: { minHeight: 24, minWidth: 70, border: '1px solid #000', color: '#000', padding: '3px 9px', textTransform: 'none' } } },
    MuiTabs: { styleOverrides: { root: { minHeight: 24 }, indicator: { height: 2, background: '#000080' } } },
  },
});

export function App() {
  const [tab, setTab] = useState(0);
  const [enabled, setEnabled] = useState(false);
  const [name, setName] = useState('既定の接続');
  const [status, setStatus] = useState('準備完了');
  const [dialogOpen, setDialogOpen] = useState(false);
  const triggerRef = useRef(null);

  function save(event) {
    event.preventDefault();
    setName(name.trim());
    setStatus(`${name.trim()}を保存しました`);
  }

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.get('dialog') === '1') setDialogOpen(true);
    if (query.get('selftest') !== '1') return;
    window.setTimeout(async () => {
      const input = document.querySelector('[data-fixture-name]');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(input, '  社内LAN  ');
      input?.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('[data-fixture-form]')?.requestSubmit();
      await new Promise((resolve) => window.setTimeout(resolve, 80));
      document.querySelector('[data-fixture-tab="advanced"]')?.click();
      await new Promise((resolve) => window.setTimeout(resolve, 80));
      document.querySelector('[data-fixture-check]')?.click();
      await new Promise((resolve) => window.setTimeout(resolve, 80));
      triggerRef.current?.focus();
      triggerRef.current?.click();
      window.setTimeout(() => {
        const dialog = document.querySelector('[data-fixture-dialog]');
        const style = dialog ? getComputedStyle(dialog) : null;
        const dialogRadius = style?.borderRadius || 'missing';
        const portalThemed = dialog?.closest('[data-retro-theme="windows-98"]') !== null;
        dialog?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }));
        window.setTimeout(() => {
          const checks = {
            tab: document.querySelector('[data-fixture-tab="advanced"]')?.getAttribute('aria-selected') === 'true',
            checked: document.querySelector('[data-fixture-check]')?.checked === true,
            input: input?.value === '社内LAN',
            status: document.querySelector('[data-fixture-status]')?.textContent?.includes('保存しました') === true,
            portalThemed,
            radius: Number.parseFloat(dialogRadius) <= 1,
            radiusValue: dialogRadius,
            closed: document.querySelector('[data-fixture-dialog]') === null,
            focusReturned: document.activeElement === triggerRef.current,
          };
          const passed = Object.entries(checks).filter(([key]) => key !== 'radiusValue').every(([, value]) => Boolean(value));
          document.documentElement.dataset.selftestDetails = JSON.stringify(checks);
          document.documentElement.dataset.selftest = passed ? 'passed' : 'failed';
        }, 400);
      }, 150);
    }, 100);
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <main className="retro-app fixture-workspace">
        <section className="retro-window fixture-window" aria-labelledby="mui-title">
          <header className="retro-title-bar"><span id="mui-title">通信設定</span></header>
          <Tabs value={tab} onChange={(_, value) => setTab(value)} aria-label="設定ページ">
            <Tab label="基本" data-fixture-tab="basic" />
            <Tab label="詳細" data-fixture-tab="advanced" />
          </Tabs>
          <form className="retro-window-body retro-stack" data-fixture-form onSubmit={save}>
            {tab === 0 ? (
              <fieldset><legend>接続先</legend><div className="retro-form-grid"><label htmlFor="mui-name">接続名</label><TextField id="mui-name" slotProps={{ htmlInput: { 'data-fixture-name': true } }} value={name} onChange={(event) => setName(event.target.value)} required size="small" /></div></fieldset>
            ) : (
              <fieldset><legend>詳細オプション</legend><FormControlLabel control={<Checkbox slotProps={{ input: { 'data-fixture-check': true } }} checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />} label="起動時に自動接続" /></fieldset>
            )}
            <div className="retro-dialog__commands"><Button type="submit" variant="outlined">適用</Button><Button ref={triggerRef} type="button" variant="outlined" onClick={() => setDialogOpen(true)}>確認...</Button></div>
          </form>
          <footer className="retro-statusbar" aria-live="polite"><span data-fixture-status>{status}</span><span>React / MUI / Emotion</span></footer>
        </section>
      </main>
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} aria-labelledby="mui-dialog-title" slotProps={{ paper: { 'data-fixture-dialog': true } }}>
        <DialogTitle id="mui-dialog-title">設定の確認</DialogTitle>
        <DialogContent>CSS-in-JS providerとportal behaviorを維持します。</DialogContent>
        <DialogActions><Button onClick={() => setDialogOpen(false)}>閉じる</Button></DialogActions>
      </Dialog>
    </ThemeProvider>
  );
}
