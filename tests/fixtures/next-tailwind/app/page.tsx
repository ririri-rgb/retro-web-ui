import { SettingsClient } from './settings-client';

export const dynamic = 'force-dynamic';

export default function Page() {
  return (
    <main className="retro-app fixture-workspace">
      <section className="retro-window fixture-window" aria-labelledby="next-title">
        <header className="retro-title-bar"><span id="next-title">システム設定</span></header>
        <nav className="retro-commandbar" aria-label="設定コマンド"><button type="button">ホーム</button><button type="button">更新履歴</button></nav>
        <SettingsClient />
        <footer className="retro-statusbar"><span>準備完了</span><span>Next App Router / Radix</span></footer>
      </section>
    </main>
  );
}
