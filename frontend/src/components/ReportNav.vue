<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/** Sommaire du rapport, fixé en haut de l'écran : chaque entrée mène à une section de la page. */
const props = defineProps<{
  /** Sections présentes dans la page, dans l'ordre : identifiant du titre et libellé. */
  sections: readonly { id: string; label: string }[]
}>()

const active = ref<string | null>(null)
let observer: IntersectionObserver | undefined

function goTo(id: string): void {
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  document.getElementById(id)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  active.value = id
}

onMounted(() => {
  if (typeof IntersectionObserver === 'undefined') return
  // La section « courante » est celle dont le titre a franchi le haut de l'écran en dernier.
  observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).map((entry) => entry.target.id)
      const first = props.sections.find((section) => visible.includes(section.id))
      if (first) active.value = first.id
    },
    { rootMargin: '-15% 0px -70% 0px' },
  )
  for (const section of props.sections) {
    const title = document.getElementById(section.id)
    if (title) observer.observe(title)
  }
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <nav
    class="sticky top-0 z-20 -mx-4 mb-6 border-b border-slate-200 bg-slate-50/95 px-4 backdrop-blur sm:-mx-6 sm:px-6"
    aria-label="Sommaire du rapport"
  >
    <ul class="flex gap-1 overflow-x-auto py-2 text-sm whitespace-nowrap">
      <li v-for="section in sections" :key="section.id">
        <button
          type="button"
          class="rounded-full px-3 py-1.5 font-medium"
          :class="
            active === section.id ? 'bg-brand-700 text-white' : 'text-slate-600 hover:bg-slate-200 hover:text-slate-900'
          "
          :aria-current="active === section.id ? 'true' : undefined"
          @click="goTo(section.id)"
        >
          {{ section.label }}
        </button>
      </li>
    </ul>
  </nav>
</template>
