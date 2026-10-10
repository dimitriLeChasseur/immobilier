<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <section class="mx-auto max-w-xl py-16 text-center">
    <p class="text-sm font-medium text-brand-700">Erreur 404</p>
    <h1 class="mt-2 text-2xl font-semibold text-slate-900">Page introuvable</h1>
    <p class="mt-3 text-sm text-slate-600">
      Cette adresse ne correspond à aucune page du site. Le lien est peut-être incomplet, ou la page a été déplacée.
    </p>
    <div class="mt-6 flex flex-wrap justify-center gap-3 text-sm">
      <RouterLink
        :to="{ name: 'audit' }"
        class="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700"
      >
        Auditer une adresse
      </RouterLink>
      <RouterLink
        :to="{ name: 'communes' }"
        class="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50"
      >
        Chiffres clés par commune
      </RouterLink>
    </div>
  </section>
</template>
