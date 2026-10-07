<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

import AuthModal from './components/AuthModal.vue'
import { useAuth } from './composables/useAuth'
import { DATA_SOURCES } from './lib/sources'

const { user, available, signOut } = useAuth()
const authOpen = ref(false)
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center gap-3 px-4 py-4 sm:px-6">
        <RouterLink :to="{ name: 'audit' }" class="flex items-center gap-3">
          <img src="/favicon.svg" alt="" class="size-8" />
          <span class="text-base font-semibold text-slate-900">Audit Immobilier</span>
        </RouterLink>

        <nav class="ml-auto flex items-center gap-2 text-sm" aria-label="Navigation principale">
          <RouterLink
            :to="{ name: 'pricing' }"
            class="rounded-lg px-3 py-2 font-medium text-slate-700 hover:bg-slate-100"
          >
            Tarifs
          </RouterLink>
          <template v-if="user">
            <RouterLink
              :to="{ name: 'account' }"
              class="max-w-48 truncate rounded-lg px-3 py-2 font-medium text-slate-700 hover:bg-slate-100"
              :title="user.email ?? undefined"
            >
              Mon compte
            </RouterLink>
            <button
              type="button"
              class="rounded-lg border border-slate-300 px-3 py-2 font-medium text-slate-700 hover:bg-slate-50"
              @click="signOut"
            >
              Se déconnecter
            </button>
          </template>
          <button
            v-else-if="available"
            type="button"
            class="rounded-lg border border-slate-300 px-3 py-2 font-medium text-slate-700 hover:bg-slate-50"
            @click="authOpen = true"
          >
            Se connecter
          </button>
        </nav>
      </div>
    </header>

    <main class="mx-auto w-full max-w-6xl flex-1 px-4 pb-16 sm:px-6">
      <RouterView />
    </main>

    <footer class="border-t border-slate-200 bg-white">
      <p class="mx-auto max-w-6xl px-4 py-5 text-xs text-slate-500 sm:px-6">
        Données publiques : {{ DATA_SOURCES }}. Informations indicatives, sans valeur contractuelle.
        <RouterLink :to="{ name: 'communes' }" class="ml-1 font-medium text-slate-700 underline">
          Chiffres clés par commune
        </RouterLink>
      </p>
    </footer>

    <AuthModal v-model:open="authOpen" initial-mode="signin" @authenticated="authOpen = false" />
  </div>
</template>
