<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { LEGAL_INCOMPLETE, TODO } from '../lib/legal'
import { LEGAL_DOCUMENTS, type LegalKey } from '../lib/legalContent'

const props = defineProps<{ document: LegalKey }>()

const content = computed(() => LEGAL_DOCUMENTS[props.document])
const LINKS: [LegalKey, string, string][] = [
  ['mentions', 'legal-notice', 'Mentions légales'],
  ['cgv', 'terms', 'CGV'],
  ['confidentialite', 'privacy', 'Confidentialité'],
]

/** Découpe un paragraphe autour des informations manquantes, pour les signaler à l'écran. */
function parts(text: string): { text: string; missing: boolean }[] {
  return text
    .split(TODO)
    .flatMap((piece, index) => (index === 0 ? [{ text: piece, missing: false }] : [{ text: TODO, missing: true }, { text: piece, missing: false }]))
    .filter((piece) => piece.text !== '')
}

// Les entrées « - … » consécutives forment une liste ; les autres, des paragraphes.
function blocks(paragraphs: string[]): { list: boolean; items: string[] }[] {
  const result: { list: boolean; items: string[] }[] = []
  for (const paragraph of paragraphs.filter(Boolean)) {
    const list = paragraph.startsWith('- ')
    const text = list ? paragraph.slice(2) : paragraph
    const last = result.at(-1)
    if (list && last?.list) last.items.push(text)
    else result.push({ list, items: [text] })
  }
  return result
}
</script>

<template>
  <article class="mx-auto max-w-3xl py-10 sm:py-14">
    <nav class="flex flex-wrap gap-x-4 gap-y-1 text-sm" aria-label="Pages légales">
      <RouterLink
        v-for="[key, name, label] in LINKS"
        :key="key"
        :to="{ name }"
        class="font-medium"
        :class="key === document ? 'text-slate-900' : 'text-brand-700 hover:underline'"
        :aria-current="key === document ? 'page' : undefined"
      >
        {{ label }}
      </RouterLink>
    </nav>
    <h1 class="mt-4 text-3xl font-semibold tracking-tight text-slate-900">{{ content.title }}</h1>
    <p class="mt-2 text-sm text-slate-500">Dernière mise à jour : {{ content.updated }}</p>
    <p v-if="LEGAL_INCOMPLETE" class="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900" role="note">
      Page en cours de finalisation : certaines informations sur l’éditeur restent à compléter.
    </p>

    <section v-for="section in content.sections" :key="section.heading" class="mt-8">
      <h2 class="text-lg font-semibold text-slate-900">{{ section.heading }}</h2>
      <template v-for="(block, index) in blocks(section.paragraphs)" :key="index">
        <ul v-if="block.list" class="mt-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-slate-700">
          <li v-for="item in block.items" :key="item">
            <template v-for="(piece, position) in parts(item)" :key="position">
              <mark v-if="piece.missing" class="rounded bg-amber-100 px-1 text-amber-900">{{ piece.text }}</mark>
              <template v-else>{{ piece.text }}</template>
            </template>
          </li>
        </ul>
        <p v-else class="mt-3 text-sm leading-relaxed text-slate-700">
          <template v-for="(piece, position) in parts(block.items[0] ?? '')" :key="position">
            <mark v-if="piece.missing" class="rounded bg-amber-100 px-1 text-amber-900">{{ piece.text }}</mark>
            <template v-else>{{ piece.text }}</template>
          </template>
        </p>
      </template>
    </section>
  </article>
</template>
