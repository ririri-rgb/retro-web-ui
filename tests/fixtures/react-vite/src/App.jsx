import { useState } from 'react';
export function App() {
  const [enabled, setEnabled] = useState(false);
  return (
    <main className="retro-app fixture-workspace" data-retro-theme="japanese-freeware-2000s">
      <section className="retro-window fixture-window" aria-labelledby="fixture-title">
        <header className="retro-title-bar">
          <span id="fixture-title">動作確認ユーティリティ</span>
        </header>
        <nav className="retro-menubar" aria-label="メニュー">
          <span>ファイル(F)</span>
          <span>ヘルプ(H)</span>
        </nav>
        <div className="retro-window-body retro-stack">
          <fieldset>
            <legend>テスト設定</legend>
            <p>既存の状態とクリックハンドラを保ったまま、desktop utility構造へ再構成したfixtureです。</p>
            <button
              type="button"
              aria-pressed={enabled}
              onClick={() => setEnabled(!enabled)}
            >
              {enabled ? '停止' : '開始'}
            </button>
          </fieldset>
        </div>
        <footer className="retro-statusbar" aria-live="polite">
          <span data-fixture-status>{enabled ? '稼働中' : '待機中'}</span>
          <span>React 19 / Vite 8</span>
        </footer>
      </section>
    </main>
  );
}
