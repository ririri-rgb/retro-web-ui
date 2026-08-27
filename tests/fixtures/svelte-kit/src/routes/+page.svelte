<script>
  import { onMount } from 'svelte';

  let checked = false;
  let folder = 'C:\\Backup';
  let status = '待機中';

  function save(event) {
    event.preventDefault();
    folder = folder.trim();
    status = checked ? `${folder}へ自動保存します` : `${folder}を手動保存します`;
  }

  onMount(() => {
    if (new URLSearchParams(window.location.search).get('selftest') !== '1') return;
    window.setTimeout(() => {
      const checkbox = document.querySelector('[data-fixture-check]');
      const input = document.querySelector('[data-fixture-folder]');
      checkbox.click();
      input.value = '  D:\\Archive  ';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('[data-fixture-form]').requestSubmit();
      window.setTimeout(() => {
        const passed = checkbox.checked
          && input.value === 'D:\\Archive'
          && document.querySelector('[data-fixture-status]').textContent.includes('自動保存します');
        document.documentElement.dataset.selftest = passed ? 'passed' : 'failed';
      }, 30);
    }, 50);
  });
</script>

<main class="retro-app fixture-workspace" data-retro-theme="japanese-freeware-2000s">
  <section class="retro-window fixture-window" aria-labelledby="svelte-title">
    <header class="retro-title-bar"><span id="svelte-title">簡易バックアップ設定 Ver.2.4</span></header>
    <nav class="retro-menubar" aria-label="メニュー"><button type="button">設定(S)</button><button type="button">ヘルプ(H)</button></nav>
    <form class="retro-window-body retro-stack" data-fixture-form onsubmit={save}>
      <fieldset>
        <legend>保存先</legend>
        <div class="retro-form-grid">
          <label for="backup-folder">フォルダー</label>
          <input id="backup-folder" data-fixture-folder bind:value={folder} required>
          <span>自動処理</span>
          <label><input data-fixture-check type="checkbox" bind:checked={checked}>終了時に自動保存</label>
        </div>
      </fieldset>
      <div class="retro-dialog__commands"><button type="submit">適用</button><button type="reset">元に戻す</button></div>
    </form>
    <footer class="retro-statusbar" aria-live="polite"><span data-fixture-status>{status}</span><span>SvelteKit prerender + hydration</span></footer>
  </section>
</main>
