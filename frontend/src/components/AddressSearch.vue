<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { useAddressSearch } from '../composables/useAddressSearch'
import type { AddressSuggestion } from '../types/audit'

const props = defineProps<{ initialLabel?: string }>()
const emit = defineEmits<{ select: [suggestion: AddressSuggestion] }>()

const LISTBOX_ID = 'address-suggestions'

const query = ref(props.initialLabel ?? '')
const open = ref(false)
const activeIndex = ref(-1)
// Libellé inséré par le dernier choix : il ne doit pas relancer une recherche ni rouvrir la liste.
let selectedLabel: string | null = null

const { suggestions, loading, failed, clear } = useAddressSearch(query)

const expanded = computed(() => open.value && suggestions.value.length > 0)
const activeId = computed(() => (activeIndex.value >= 0 ? `${LISTBOX_ID}-${activeIndex.value}` : undefined))
const noResult = computed(
  () => open.value && !loading.value && !failed.value && query.value.trim().length >= 3 && !suggestions.value.length,
)

watch(suggestions, (items) => {
  activeIndex.value = -1
  if (items.length && query.value !== selectedLabel) open.value = true
})

function choose(suggestion: AddressSuggestion): void {
  selectedLabel = suggestion.label
  query.value = suggestion.label
  open.value = false
  // Après la mise à jour : annule la recherche que ce changement de texte vient de programmer.
  void nextTick(clear)
  emit('select', suggestion)
}

function move(step: number): void {
  if (!suggestions.value.length) return
  open.value = true
  const count = suggestions.value.length
  activeIndex.value = (activeIndex.value + step + count) % count
}

function submit(): void {
  const suggestion = suggestions.value[Math.max(activeIndex.value, 0)]
  if (suggestion) choose(suggestion)
}
</script>

<template>
  <form class="relative" role="search" @submit.prevent="submit">
    <label for="address-input" class="sr-only">Adresse du bien</label>
    <div class="relative">
      <svg
        class="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-slate-400"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M9 3.5a5.5 5.5 0 1 0 3.4 9.8l3.6 3.7a.75.75 0 1 0 1-1l-3.6-3.7A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z"
          clip-rule="evenodd"
        />
      </svg>
      <input
        id="address-input"
        v-model="query"
        type="text"
        role="combobox"
        autocomplete="off"
        spellcheck="false"
        maxlength="200"
        placeholder="Saisissez une adresse, ex. 12 rue de la Paix, Angers"
        class="w-full rounded-2xl border border-slate-300 bg-white py-4 pr-12 pl-12 text-base text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100"
        aria-autocomplete="list"
        :aria-expanded="expanded"
        :aria-controls="LISTBOX_ID"
        :aria-activedescendant="activeId"
        @focus="open = query !== selectedLabel"
        @input="open = true"
        @keydown.down.prevent="move(1)"
        @keydown.up.prevent="move(-1)"
        @keydown.esc="open = false"
      />
      <span
        v-if="loading"
        class="absolute top-1/2 right-4 size-5 -translate-y-1/2 animate-spin rounded-full border-2 border-slate-200 border-t-brand-600"
        aria-hidden="true"
      ></span>
    </div>

    <ul
      v-show="expanded"
      :id="LISTBOX_ID"
      role="listbox"
      aria-label="Adresses proposées"
      class="absolute z-[1100] mt-2 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white py-1 shadow-lg"
    >
      <li
        v-for="(suggestion, index) in suggestions"
        :id="`${LISTBOX_ID}-${index}`"
        :key="suggestion.id"
        role="option"
        :aria-selected="index === activeIndex"
        class="cursor-pointer px-4 py-2.5"
        :class="index === activeIndex ? 'bg-brand-50' : 'hover:bg-slate-50'"
        @mousedown.prevent="choose(suggestion)"
        @mousemove="activeIndex = index"
      >
        <p class="text-sm font-medium text-slate-900">{{ suggestion.label }}</p>
        <p class="text-xs text-slate-500">{{ suggestion.context }}</p>
      </li>
    </ul>

    <p v-if="failed" class="mt-2 text-sm text-rose-700" role="alert">
      Le service d’adresses ne répond pas. Réessayez dans un instant.
    </p>
    <output v-else-if="noResult" class="mt-2 block text-sm text-slate-500">
      Aucune adresse trouvée pour cette saisie.
    </output>
  </form>
</template>
