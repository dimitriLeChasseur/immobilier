<script setup lang="ts">
import { computed } from 'vue'

import { CHECKLIST_ITEMS, CHECKLIST_TITLE } from '../lib/checklist'

/** Identifiants des points cochés ; l'export PDF reprend cet état. */
const checked = defineModel<string[]>({ required: true })

const remaining = computed(() => CHECKLIST_ITEMS.length - checked.value.length)
</script>

<template>
  <section aria-labelledby="section-checklist" class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <h2 id="section-checklist" class="scroll-mt-20 text-lg font-semibold text-slate-900">{{ CHECKLIST_TITLE }}</h2>
    <p class="mt-1 text-sm text-slate-600">
      Trois points que les données publiques ne permettent pas de vérifier à votre place.
    </p>

    <ul class="mt-4 space-y-3">
      <li v-for="item in CHECKLIST_ITEMS" :key="item.id">
        <label class="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 px-4 py-3 hover:bg-slate-50 has-checked:border-brand-500 has-checked:bg-brand-50">
          <input
            v-model="checked"
            type="checkbox"
            :value="item.id"
            class="mt-0.5 size-5 shrink-0 rounded border-slate-400 accent-brand-600"
          />
          <span class="text-sm text-slate-800">{{ item.label }}</span>
        </label>
      </li>
    </ul>

    <output class="mt-3 block text-xs text-slate-500">
      {{ remaining === 0 ? 'Tous les points sont vérifiés.' : `${remaining} point(s) restant à vérifier.` }}
      L’état des cases est repris dans l’export PDF.
    </output>
  </section>
</template>
