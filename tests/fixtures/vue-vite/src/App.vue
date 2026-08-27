<script setup>
import { nextTick, onMounted, ref } from 'vue';

const name = ref('');
const notifications = ref(true);
const status = ref('未保存');

function save() {
  name.value = name.value.trim();
  status.value = `${name.value || '名称未設定'}を保存しました`;
}

onMounted(() => {
  if (new URLSearchParams(window.location.search).get('selftest') !== '1') return;
  window.setTimeout(async () => {
    const input = document.querySelector('[data-fixture-name]');
    input.value = '  接続プロファイル  ';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    document.querySelector('[data-fixture-form]').requestSubmit();
    await nextTick();
    const modal = document.querySelector('#confirm-dialog');
    const shown = new Promise((resolve) => modal?.addEventListener('shown.bs.modal', resolve, { once: true }));
    document.querySelector('[data-bs-toggle="modal"]').click();
    await Promise.race([shown, new Promise((resolve) => window.setTimeout(resolve, 1000))]);
    const content = modal?.querySelector('.modal-content');
    const modalOpened = modal?.classList.contains('show') && content?.getAttribute('role') === 'document';
    const submitStyle = getComputedStyle(document.querySelector('[type="submit"]'));
    const bootstrapAdapted = Number.parseFloat(submitStyle.borderRadius) < 10
      && submitStyle.color !== 'rgb(255, 255, 255)';
    const hidden = new Promise((resolve) => modal?.addEventListener('hidden.bs.modal', resolve, { once: true }));
    modal?.querySelector('[data-bs-dismiss="modal"]')?.click();
    await Promise.race([hidden, new Promise((resolve) => window.setTimeout(resolve, 1000))]);
    const passed = name.value === '接続プロファイル'
      && status.value.includes('保存しました')
      && modalOpened
      && bootstrapAdapted
      && !modal?.classList.contains('show');
    document.documentElement.dataset.selftest = passed ? 'passed' : 'failed';
  }, 50);
});
</script>

<template>
  <main class="retro-app fixture-workspace">
    <section class="retro-window fixture-window" aria-labelledby="vue-title">
      <header class="retro-title-bar"><span id="vue-title">ネットワーク接続のプロパティ</span></header>
      <nav class="retro-menubar" aria-label="アプリケーションメニュー">
        <button type="button">ファイル(F)</button><button type="button">ヘルプ(H)</button>
      </nav>
      <form class="retro-window-body retro-stack" data-fixture-form @submit.prevent="save">
        <fieldset>
          <legend>接続設定</legend>
          <div class="retro-form-grid">
            <label for="profile-name">プロファイル名</label>
            <input id="profile-name" v-model="name" class="form-control form-control-sm" data-fixture-name required>
            <span>通知</span>
            <label><input v-model="notifications" class="form-check-input" type="checkbox">接続時に通知する</label>
          </div>
        </fieldset>
        <div class="retro-dialog__commands">
          <button class="btn btn-primary rounded-pill px-4" type="submit">保存</button>
          <button class="btn btn-secondary rounded-pill px-4" type="button" data-bs-toggle="modal" data-bs-target="#confirm-dialog">詳細...</button>
        </div>
      </form>
      <footer class="retro-statusbar" aria-live="polite"><span data-fixture-status>{{ status }}</span><span>Vue 3 / Bootstrap 5</span></footer>
    </section>
    <div id="confirm-dialog" class="modal fade" tabindex="-1" aria-labelledby="confirm-title" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content retro-window retro-dialog" role="document">
          <header class="retro-title-bar"><span id="confirm-title">接続の詳細</span></header>
          <div class="retro-dialog-body">
            <p>この画面はBootstrapのmodal runtimeとfocus managementを維持しています。</p>
            <div class="retro-dialog__commands"><button type="button" data-bs-dismiss="modal">閉じる</button></div>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>
