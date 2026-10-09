<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'

import { MIN_PASSWORD_LENGTH, useAuth } from '../composables/useAuth'

// Le lien reçu par e-mail ouvre une session : c'est elle qui autorise le changement.
const { user, ready, updatePassword } = useAuth()

const password = ref('')
const busy = ref(false)
const done = ref(false)
const error = ref<string | null>(null)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  const outcome = await updatePassword(password.value)
  if (outcome.ok) {
    done.value = true
    password.value = ''
  } else {
    error.value = outcome.message
  }
  busy.value = false
}
</script>

<template>
  <section class="mx-auto max-w-md py-12 sm:py-16" aria-labelledby="password-title">
    <h1 id="password-title" class="text-2xl font-semibold tracking-tight text-slate-900">Nouveau mot de passe</h1>

    <div v-if="done" class="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-6">
      <p class="text-sm text-emerald-900">Votre mot de passe est changé. Vous êtes connecté.</p>
      <RouterLink :to="{ name: 'account' }" class="mt-3 inline-block text-sm font-medium text-brand-700 underline">
        Aller à mon compte
      </RouterLink>
    </div>

    <form v-else-if="user" class="mt-6 space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" @submit.prevent="submit">
      <p class="text-sm text-slate-600">Choisissez un nouveau mot de passe pour {{ user.email }}.</p>
      <label class="block text-sm font-medium text-slate-700">
        Nouveau mot de passe
        <input
          v-model="password"
          type="password"
          required
          :minlength="MIN_PASSWORD_LENGTH"
          autocomplete="new-password"
          class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-brand-600 focus:ring-4 focus:ring-brand-100 focus:outline-none"
        />
        <span class="mt-1 block text-xs font-normal text-slate-500">{{ MIN_PASSWORD_LENGTH }} caractères au minimum.</span>
      </label>
      <p v-if="error" class="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800" role="alert">{{ error }}</p>
      <button
        type="submit"
        class="w-full rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-900 disabled:opacity-50"
        :disabled="busy"
      >
        Enregistrer le mot de passe
      </button>
    </form>

    <div v-else-if="ready" class="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
      <p class="text-sm text-slate-600">
        Ce lien n’est plus valable : il ne sert qu’une fois et expire au bout d’une heure. Redemandez-en un
        depuis « Se connecter », puis « Mot de passe oublié ? ».
      </p>
      <RouterLink :to="{ name: 'audit' }" class="mt-3 inline-block text-sm font-medium text-brand-700 underline">
        Retour à l’accueil
      </RouterLink>
    </div>
  </section>
</template>
