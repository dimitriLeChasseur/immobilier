<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { communeLinks, fetchCommune } from '../api/communes'
import AddressSearch from '../components/AddressSearch.vue'
import { codeFromSlug, communePage, communeSlug, nearbyCommunes, relatedCommunes, type CommuneProfile } from '../lib/commune'
import { UNIT_PRICE } from '../lib/pricing'
import { DEFAULT_DESCRIPTION, setPageMeta, SITE_NAME } from '../lib/seo'
import { writeTarget } from '../lib/url'
import type { AddressSuggestion } from '../types/audit'

const route = useRoute()
const router = useRouter()
const profile = ref<CommuneProfile | null>(null)
const state = ref<'loading' | 'ready' | 'missing' | 'error'>('loading')

const page = computed(() => (profile.value ? communePage(profile.value) : null))
const nearby = computed(() => (profile.value ? nearbyCommunes(communeLinks(), profile.value) : []))
const related = computed(() => (profile.value ? relatedCommunes(communeLinks(), profile.value, nearby.value) : []))

// Le lecteur vient chercher une moyenne communale ; ce qui change d'une rue à l'autre se vérifie
// à l'adresse. Un rappel après les rubriques où l'écart est le plus parlant.
const ADDRESS_NOTES: Record<string, string> = {
  'Fiscalité locale':
    'Ce taux vaut pour toute la commune. Ce qui fait le prix d’un bien se joue à l’adresse : ventes réelles ' +
    'voisines, bruit, état de l’immeuble.',
  Sécurité:
    'Moyenne communale. Le bruit, les diagnostics énergie et les risques naturels changent d’une rue à ' +
    'l’autre : vérifiez votre numéro exact.',
  'Établissements scolaires':
    'Le collège de secteur dépend de l’adresse, pas de la commune : l’audit l’indique là où la carte ' +
    'scolaire est publiée.',
}

function addressNote(heading: string): string | undefined {
  return ADDRESS_NOTES[heading.replace(/ \(.*\)$/, '')]
}

async function focusSearch(): Promise<void> {
  const block = document.getElementById('commune-search')
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  block?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' })
  await nextTick()
  document.getElementById('address-input')?.focus({ preventScroll: true })
}

function onSelect(suggestion: AddressSuggestion): void {
  if (suggestion.commune) {
    void router.push({ name: 'commune', params: { slug: communeSlug(suggestion.commune.nom, suggestion.commune.code) } })
    return
  }
  const target = { lat: suggestion.lat, lon: suggestion.lon, banId: suggestion.id }
  void router.push({ name: 'audit', query: Object.fromEntries(new URLSearchParams(writeTarget(target, suggestion.label))) })
}

async function load(slug: string): Promise<void> {
  state.value = 'loading'
  profile.value = null
  const code = codeFromSlug(slug)
  if (!code) {
    state.value = 'missing'
    return
  }
  try {
    profile.value = await fetchCommune(code)
    state.value = profile.value ? 'ready' : 'missing'
  } catch {
    state.value = 'error'
  }
}

watch(() => String(route.params.slug ?? ''), load, { immediate: true })

function updateMeta(): void {
  if (page.value && profile.value) {
    setPageMeta({
      title: page.value.title,
      description: page.value.description,
      path: `/commune/${profile.value.slug}`,
    })
  } else if (state.value === 'missing') {
    setPageMeta({
      title: `Commune introuvable | ${SITE_NAME}`,
      description: DEFAULT_DESCRIPTION,
      path: route.path,
      noindex: true,
    })
  }
}

// Immédiat : un segment d'URL mal formé est jugé introuvable avant même le premier rendu.
watch([page, state], updateMeta, { immediate: true })
</script>

<template>
  <article class="mx-auto max-w-3xl py-10 sm:py-14">
    <template v-if="page">
      <p class="text-xs font-medium tracking-wide text-brand-700 uppercase">
        <RouterLink :to="{ name: 'communes' }" class="hover:underline">Communes</RouterLink>
      </p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">{{ page.heading }}</h1>
      <p class="mt-3 text-base text-slate-600">{{ page.intro }}</p>

      <section v-if="page.summary.length" class="mt-8" aria-labelledby="commune-summary">
        <h2 id="commune-summary" class="text-lg font-semibold text-slate-900">En bref</h2>
        <ul class="mt-3 list-disc space-y-1.5 pl-5 text-base text-slate-700">
          <li v-for="sentence in page.summary" :key="sentence">{{ sentence }}</li>
        </ul>
      </section>

      <section
        id="commune-search"
        class="mt-8 scroll-mt-24 rounded-2xl border border-brand-100 bg-brand-50 p-6"
        aria-labelledby="commune-audit"
      >
        <h2 id="commune-audit" class="text-lg font-semibold text-brand-900">
          Ces chiffres valent pour toute la commune. Et à votre adresse ?
        </h2>
        <p class="mt-2 text-sm text-brand-900">
          Ventes réelles autour du bien, bruit, diagnostic énergie de l’immeuble, risque d’argile au point exact :
          tout change d’une rue à l’autre. Aperçu gratuit, audit complet à {{ UNIT_PRICE }}.
        </p>
        <AddressSearch
          v-if="profile"
          class="mt-4"
          :citycode="profile.code"
          :placeholder="`Numéro et rue à ${profile.nom}`"
          @select="onSelect"
        />
      </section>

      <template v-for="section in page.sections" :key="section.heading">
        <section class="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 class="text-lg font-semibold text-slate-900">{{ section.heading }}</h2>
          <dl class="mt-4 space-y-4">
            <div v-for="fact in section.facts" :key="fact.label">
              <dt class="text-sm text-slate-500">{{ fact.label }}</dt>
              <dd class="mt-0.5 text-base font-medium text-slate-900">{{ fact.value }}</dd>
              <dd v-if="fact.note" class="text-sm text-slate-500">{{ fact.note }}</dd>
            </div>
          </dl>
        </section>
        <aside
          v-if="addressNote(section.heading)"
          class="mt-4 flex flex-col gap-3 rounded-2xl border border-dashed border-brand-600/40 bg-white px-5 py-4 sm:flex-row sm:items-center"
        >
          <p class="min-w-0 flex-1 text-sm text-slate-700">{{ addressNote(section.heading) }}</p>
          <button
            type="button"
            class="shrink-0 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900"
            @click="focusSearch"
          >
            Tester mon adresse
          </button>
        </aside>
      </template>

      <nav v-if="nearby.length" class="mt-8" aria-labelledby="commune-nearby">
        <h2 id="commune-nearby" class="text-lg font-semibold text-slate-900">Communes proches</h2>
        <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <li v-for="commune in nearby" :key="commune.slug">
            <RouterLink :to="{ name: 'commune', params: { slug: commune.slug } }" class="text-brand-700 hover:underline">
              {{ commune.nom }}
            </RouterLink>
          </li>
        </ul>
      </nav>
      <nav v-if="related.length" class="mt-8" aria-labelledby="commune-related">
        <h2 id="commune-related" class="text-lg font-semibold text-slate-900">
          Autres communes du département {{ profile?.departement_nom || profile?.departement_code }}
        </h2>
        <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <li v-for="commune in related" :key="commune.slug">
            <RouterLink :to="{ name: 'commune', params: { slug: commune.slug } }" class="text-brand-700 hover:underline">
              {{ commune.nom }}
            </RouterLink>
          </li>
        </ul>
      </nav>
      <p class="mt-6 text-xs text-slate-500">
        Sources : carte des loyers (ANIL, ministère chargé du logement), DGFiP, SSMSI, Éducation nationale, INSEE,
        ARCEP. Données publiques, sans valeur contractuelle.
      </p>
    </template>

    <output v-else-if="state === 'loading'" class="block space-y-4" aria-label="Chargement de la fiche">
      <span class="skeleton block h-10 w-2/3"></span>
      <span class="skeleton block h-40 w-full"></span>
    </output>

    <div v-else class="rounded-2xl border border-slate-200 bg-white p-6">
      <h1 class="text-xl font-semibold text-slate-900">
        {{ state === 'missing' ? 'Commune introuvable' : 'Fiche momentanément indisponible' }}
      </h1>
      <p class="mt-2 text-sm text-slate-600">
        {{ state === 'missing' ? 'Cette adresse ne correspond à aucune commune.' : 'Réessayez dans un instant.' }}
      </p>
      <RouterLink :to="{ name: 'audit' }" class="mt-4 inline-block text-sm font-medium text-brand-700 underline">
        Analyser une adresse
      </RouterLink>
    </div>
  </article>
</template>
