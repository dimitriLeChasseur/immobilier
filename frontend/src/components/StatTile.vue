<script setup lang="ts">
defineProps<{
  label: string
  value: string
  hint?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}>()

const TONES = {
  default: 'text-slate-900',
  good: 'text-emerald-700',
  warn: 'text-amber-700',
  bad: 'text-rose-700',
} as const
</script>

<template>
  <div>
    <p class="text-xs text-slate-500">{{ label }}</p>
    <p class="text-2xl font-semibold tracking-tight tabular-nums" :class="TONES[tone ?? 'default']">
      {{ value }}
    </p>
    <p v-if="hint" class="mt-0.5 text-xs text-slate-500">{{ hint }}</p>
  </div>
</template>
