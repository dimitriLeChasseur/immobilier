<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { MIN_PASSWORD_LENGTH, useAuth, type AuthOutcome } from '../composables/useAuth'

const props = defineProps<{ initialMode?: 'signup' | 'signin' }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ authenticated: [] }>()

const { available, signUp, signIn, signInWithGoogle } = useAuth()

const dialog = ref<HTMLDialogElement | null>(null)
const mode = ref<'signup' | 'signin'>(props.initialMode ?? 'signup')
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

const isSignup = computed(() => mode.value === 'signup')
const title = computed(() => (isSignup.value ? 'Créer votre compte' : 'Se connecter'))

// <dialog> natif : piège le focus, se ferme avec Échap et rend le reste de la page inerte.
watch(
  [open, dialog],
  ([isOpen, element]) => {
    if (!element) return
    if (isOpen && !element.open) {
      error.value = null
      notice.value = null
      mode.value = props.initialMode ?? 'signup'
      element.showModal()
    } else if (!isOpen && element.open) {
      element.close()
    }
  },
  { immediate: true, flush: 'post' },
)

function handle(outcome: AuthOutcome): void {
  if (!outcome.ok) {
    error.value = outcome.message
    return
  }
  if (outcome.needsConfirmation) {
    notice.value = 'Compte créé. Confirmez votre adresse via l’e-mail que nous venons d’envoyer, puis connectez-vous.'
    mode.value = 'signin'
    return
  }
  password.value = ''
  emit('authenticated')
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  notice.value = null
  const action = isSignup.value ? signUp : signIn
  handle(await action(email.value.trim(), password.value))
  busy.value = false
}

async function withGoogle(): Promise<void> {
  busy.value = true
  error.value = null
  // Au retour de Google, l'utilisateur arrive directement sur le paiement de son adresse.
  const outcome = await signInWithGoogle(`${window.location.origin}/tarifs`)
  if (!outcome.ok) error.value = outcome.message
  busy.value = false
}
</script>

<template>
  <dialog
    ref="dialog"
    class="m-auto w-full max-w-md rounded-2xl border border-slate-200 bg-white p-0 shadow-2xl backdrop:bg-slate-900/50"
    aria-labelledby="auth-title"
    @close="open = false"
    @click.self="open = false"
  >
    <div class="p-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 id="auth-title" class="text-lg font-semibold text-slate-900">{{ title }}</h2>
          <p class="mt-1 text-sm text-slate-600">
            Votre adresse est conservée : vous la retrouverez juste après.
          </p>
        </div>
        <button
          type="button"
          class="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"
          aria-label="Fermer"
          @click="open = false"
        >
          <svg viewBox="0 0 20 20" class="size-5" fill="currentColor" aria-hidden="true">
            <path d="M5.3 5.3a1 1 0 0 1 1.4 0L10 8.6l3.3-3.3a1 1 0 1 1 1.4 1.4L11.4 10l3.3 3.3a1 1 0 0 1-1.4 1.4L10 11.4l-3.3 3.3a1 1 0 0 1-1.4-1.4L8.6 10 5.3 6.7a1 1 0 0 1 0-1.4Z" />
          </svg>
        </button>
      </div>

      <p v-if="!available" class="mt-5 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800" role="alert">
        La création de compte n’est pas configurée sur cet environnement.
      </p>

      <template v-else>
        <button
          type="button"
          class="mt-5 flex w-full items-center justify-center gap-3 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          :disabled="busy"
          @click="withGoogle"
        >
          <svg viewBox="0 0 18 18" class="size-4.5" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33A9 9 0 0 0 9 18Z" />
            <path fill="#FBBC05" d="M3.96 10.71a5.41 5.41 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3-2.33Z" />
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96l3 2.33C4.67 5.16 6.66 3.58 9 3.58Z" />
          </svg>
          Continuer avec Google
        </button>

        <p class="my-4 flex items-center gap-3 text-xs text-slate-400">
          <span class="h-px flex-1 bg-slate-200"></span>ou<span class="h-px flex-1 bg-slate-200"></span>
        </p>

        <form class="space-y-4" @submit.prevent="submit">
          <label class="block text-sm font-medium text-slate-700">
            Adresse e-mail
            <input
              v-model="email"
              type="email"
              required
              autocomplete="email"
              class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100"
            />
          </label>
          <label class="block text-sm font-medium text-slate-700">
            Mot de passe
            <input
              v-model="password"
              type="password"
              required
              :minlength="isSignup ? MIN_PASSWORD_LENGTH : undefined"
              :autocomplete="isSignup ? 'new-password' : 'current-password'"
              class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100"
            />
            <span v-if="isSignup" class="mt-1 block text-xs font-normal text-slate-500">
              {{ MIN_PASSWORD_LENGTH }} caractères au minimum.
            </span>
          </label>

          <p v-if="error" class="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800" role="alert">{{ error }}</p>
          <output v-if="notice" class="block rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{{ notice }}</output>

          <button
            type="submit"
            class="w-full rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-900 disabled:opacity-50"
            :disabled="busy"
          >
            {{ isSignup ? 'Créer mon compte' : 'Me connecter' }}
          </button>
        </form>

        <p class="mt-4 text-center text-sm text-slate-600">
          {{ isSignup ? 'Déjà un compte ?' : 'Pas encore de compte ?' }}
          <button
            type="button"
            class="font-medium text-brand-700 underline hover:text-brand-900"
            @click="mode = isSignup ? 'signin' : 'signup'"
          >
            {{ isSignup ? 'Se connecter' : 'Créer un compte' }}
          </button>
        </p>
      </template>
    </div>
  </dialog>
</template>
