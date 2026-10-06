<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { fetchCommune } from '../api/communes'
import { codeFromSlug, communePage, type CommuneProfile } from '../lib/commune'
import { DEFAULT_DESCRIPTION, setPageMeta, SITE_NAME } from '../lib/seo'

const route = useRoute()
const profile = ref<CommuneProfile | null>(null)
const state = ref<'loading' | 'ready' | 'missing' | 'error'>('loading')

const page = computed(() => (profile.value ? communePage(profile.value) : null))
// Audit lancé depuis le centre de la commune : l'utilisateur précise ensuite son adresse.
const auditLink = computed(() => {
  const centre = profile.value?.centre
  if (!centre || !profile.value) return { name: 'audit' }
  return { name: 'audit', query: { lat: String(centre[1]), lon: String(centre[0]), q: profile.value.nom } }
})

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

      <section
        v-for="section in page.sections"
        :key="section.heading"
        class="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2 class="text-lg font-semibold text-slate-900">{{ section.heading }}</h2>
        <dl class="mt-4 space-y-4">
          <div v-for="fact in section.facts" :key="fact.label">
            <dt class="text-sm text-slate-500">{{ fact.label }}</dt>
            <dd class="mt-0.5 text-base font-medium text-slate-900">{{ fact.value }}</dd>
            <dd v-if="fact.note" class="text-sm text-slate-500">{{ fact.note }}</dd>
          </div>
        </dl>
      </section>

      <div class="mt-8 rounded-2xl border border-brand-100 bg-brand-50 p-6">
        <h2 class="text-lg font-semibold text-brand-900">Et pour une adresse précise ?</h2>
        <p class="mt-2 text-sm text-brand-900">
          Ces chiffres sont les mêmes pour toute la commune. L’audit d’une adresse ajoute les ventes voisines, le
          bâtiment et sa copropriété, les risques au point exact, le bruit, l’urbanisme et les commerces à pied.
        </p>
        <RouterLink
          :to="auditLink"
          class="mt-4 inline-block rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900"
        >
          Auditer une adresse à {{ profile?.nom }}
        </RouterLink>
      </div>
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
