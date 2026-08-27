import { createApp } from 'vue';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import App from './App.vue';
import './fixture.css';
document.body.dataset.retroTheme = 'windows-xp';
createApp(App).mount('#app');
