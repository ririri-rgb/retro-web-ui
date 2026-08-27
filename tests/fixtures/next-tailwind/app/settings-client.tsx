'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { FormEvent, useEffect, useRef, useState } from 'react';

export function SettingsClient() {
  const [enabled, setEnabled] = useState(false);
  const [name, setName] = useState('標準プロファイル');
  const [status, setStatus] = useState('変更はありません');
  const [dialogOpen, setDialogOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setName(name.trim());
    setStatus(`${name.trim()}を保存しました`);
  }

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    if (query.get('dialog') === '1') setDialogOpen(true);
    if (query.get('selftest') !== '1') return;
    window.setTimeout(() => {
      const checkbox = document.querySelector<HTMLInputElement>('[data-fixture-check]');
      const input = document.querySelector<HTMLInputElement>('[data-fixture-name]');
      checkbox?.click();
      if (input) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
        setter?.call(input, '  管理者プロファイル  ');
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      document.querySelector<HTMLFormElement>('[data-fixture-form]')?.requestSubmit();
      triggerRef.current?.click();
      window.setTimeout(() => {
        const dialog = document.querySelector<HTMLElement>('[data-fixture-dialog]');
        const portalThemed = dialog?.closest('[data-retro-theme="windows-7"]') !== null;
        const radius = dialog ? getComputedStyle(dialog).borderRadius : '';
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        window.setTimeout(() => {
          const passed = checkbox?.checked === true
            && input?.value === '管理者プロファイル'
            && document.querySelector('[data-fixture-status]')?.textContent?.includes('保存しました')
            && portalThemed
            && radius !== '24px'
            && document.querySelector('[data-fixture-dialog]') === null
            && document.activeElement === triggerRef.current;
          document.documentElement.dataset.selftest = passed ? 'passed' : 'failed';
        }, 100);
      }, 100);
    }, 100);
  }, []);

  return (
    <form className="retro-window-body retro-stack fixture-modern-card rounded-3xl p-10 shadow-2xl" data-fixture-form onSubmit={save}>
      <fieldset>
        <legend>ユーザー設定</legend>
        <div className="retro-form-grid">
          <label htmlFor="profile">プロファイル名</label>
          <input id="profile" data-fixture-name value={name} onChange={(event) => setName(event.target.value)} required />
          <span>自動更新</span>
          <label><input data-fixture-check type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />有効にする</label>
        </div>
      </fieldset>
      <div className="retro-dialog__commands">
        <button className="rounded-full px-8" type="submit">適用</button>
        <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
          <Dialog.Trigger asChild><button ref={triggerRef} className="rounded-full px-8" type="button">詳細...</button></Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixture-dialog-overlay" />
            <Dialog.Content className="retro-window retro-dialog fixture-dialog-content rounded-3xl shadow-2xl" data-fixture-dialog>
              <header className="retro-title-bar"><Dialog.Title>詳細設定</Dialog.Title></header>
              <div className="retro-dialog-body">
                <Dialog.Description>Radix portalのfocus trapとEscape closeを維持します。</Dialog.Description>
                <div className="retro-dialog__commands"><Dialog.Close asChild><button type="button">閉じる</button></Dialog.Close></div>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
      <p className="fixture-status" aria-live="polite" data-fixture-status>{status}</p>
    </form>
  );
}
