<script setup lang="ts">
/**
 * Tient la place du tableau de bord le temps que son code arrive (quelques centaines de
 * millisecondes au premier rapport) : sans elle, la checklist de visite s'affiche en haut,
 * puis saute d'un écran vers le bas.
 */
const SECTIONS = 4
const CARDS = 3
</script>

<template>
  <output class="block space-y-10" aria-label="Chargement du rapport">
    <span v-for="section in SECTIONS" :key="section" class="block">
      <span class="skeleton mb-4 block h-6 w-48"></span>
      <span class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <span v-for="card in CARDS" :key="card" class="skeleton block h-64 rounded-2xl"></span>
      </span>
    </span>
  </output>
</template>
