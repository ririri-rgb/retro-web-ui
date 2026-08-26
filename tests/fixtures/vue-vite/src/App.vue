<script setup>import { ref } from 'vue'; const name = ref(''); function save() { name.value = name.value.trim(); }</script>
<template><form @submit.prevent="save"><input v-model="name" required><button type="submit">保存</button></form></template>
