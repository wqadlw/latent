<template>
  <div class="step-header">
    <div class="step-header-no">{{ no }}</div>
    <div class="step-header-text">
      <div class="step-header-title">{{ title }}</div>
      <div class="step-header-desc">{{ desc }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  no: { type: [Number, String], default: '' },
  title: { type: String, default: '' },
  desc: { type: String, default: '' },
})
</script>
