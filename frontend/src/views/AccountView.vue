<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { deleteBranding, fetchAudits, fetchBranding, saveBranding, type UnlockedAudit } from '../api/account'
import { openBillingPortal } from '../api/billing'
import AuthModal from '../components/AuthModal.vue'
import { useAccount } from '../composables/useAccount'
import { useAuth } from '../composables/useAuth'
import { formatDate } from '../lib/format'
import { logoProblem, MAX_LOGO_BYTES, readAsDataUrl } from '../lib/logo'

const ORIGINS: Record<UnlockedAudit['origin'], string> = {
  unit: 'Achat à l’unité',
  pack: 'Pack Investisseur',
  subscription: 'Abonnement',
  admin: 'Offert',
}

const { user, accessToken, ready, available } = useAuth()
const { account, refresh } = useAccount()

const audits = ref<UnlockedAudit[]>([])
const loading = ref(false)
const loadFailed = ref(false)
const authOpen = ref(false)

const DEFAULT_COLOR = '#0f766e'
const CONTACT_FIELDS = [
  { key: 'phone', label: 'Téléphone', type: 'tel', maxlength: 30, placeholder: '02 41 00 00 00' },
  { key: 'email', label: 'E-mail', type: 'email', maxlength: 120, placeholder: 'contact@cabinet.fr' },
  { key: 'website', label: 'Site web', type: 'url', maxlength: 120, placeholder: 'https://cabinet.fr' },
  { key: 'address', label: 'Adresse', type: 'text', maxlength: 160, placeholder: '12 rue de la Paix, 49100 Angers' },
] as const
type ContactKey = (typeof CONTACT_FIELDS)[number]['key']

const company = ref('')
const color = ref(DEFAULT_COLOR)
const contact = ref<Record<ContactKey, string>>({ phone: '', email: '', website: '', address: '' })
const logo = ref<string | null>(null)
const saved = ref(false)
const busy = ref(false)
const brandingError = ref<string | null>(null)
const brandingNotice = ref<string | null>(null)

const credits = computed(() => account.value?.credits ?? 0)
const subscribed = computed(() => account.value?.subscription_active ?? false)

function auditLink(audit: UnlockedAudit) {
  const query: Record<string, string> = { lat: String(audit.lat), lon: String(audit.lon) }
  if (audit.ban_id) query.ban_id = audit.ban_id
  if (audit.label) query.q = audit.label
  return { name: 'audit', query }
}

async function load(token: string): Promise<void> {
  loading.value = true
  loadFailed.value = false
  try {
    await refresh()
    const [list, branding] = await Promise.all([fetchAudits(token), fetchBranding(token)])
    audits.value = list
    company.value = branding?.company ?? ''
    color.value = branding?.color ?? DEFAULT_COLOR
    for (const { key } of CONTACT_FIELDS) contact.value[key] = branding?.[key] ?? ''
    logo.value = branding?.logo ?? null
    saved.value = branding !== null
  } catch {
    loadFailed.value = true
  } finally {
    loading.value = false
  }
}

watch(
  accessToken,
  (token) => {
    if (token) void load(token)
    else audits.value = []
  },
  { immediate: true },
)

async function onLogoChosen(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  brandingNotice.value = null
  brandingError.value = logoProblem(file)
  if (!brandingError.value) logo.value = await readAsDataUrl(file).catch(() => null)
  // Permet de rechoisir le même fichier après une erreur.
  input.value = ''
}

async function withBranding(action: (token: string) => Promise<void>, done: string): Promise<void> {
  if (!accessToken.value) return
  busy.value = true
  brandingError.value = null
  brandingNotice.value = null
  try {
    await action(accessToken.value)
    brandingNotice.value = done
  } catch (failure) {
    brandingError.value = failure instanceof Error ? failure.message : 'L’enregistrement a échoué.'
  } finally {
    busy.value = false
  }
}

function save(): Promise<void> {
  return withBranding(async (token) => {
    await saveBranding(token, {
      company: company.value.trim(),
      logo: logo.value,
      // La couleur par défaut n'est pas enregistrée : elle suivra nos évolutions.
      color: color.value === DEFAULT_COLOR ? null : color.value,
      ...contact.value,
    })
    saved.value = true
  }, 'Marque enregistrée : elle figurera sur vos prochains exports PDF.')
}

function remove(): Promise<void> {
  return withBranding(async (token) => {
    await deleteBranding(token)
    company.value = ''
    color.value = DEFAULT_COLOR
    contact.value = { phone: '', email: '', website: '', address: '' }
    logo.value = null
    saved.value = false
  }, 'Marque supprimée.')
}

async function manageSubscription(): Promise<void> {
  if (!accessToken.value) return
  try {
    window.location.assign(await openBillingPortal(accessToken.value))
  } catch {
    loadFailed.value = true
  }
}
</script>

<template>
  <section class="mx-auto max-w-3xl py-10 sm:py-14" aria-labelledby="account-title">
    <h1 id="account-title" class="text-3xl font-semibold tracking-tight text-slate-900">Mon compte</h1>

    <div v-if="ready && !user" class="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
      <p class="text-sm text-slate-600">Connectez-vous pour retrouver vos audits et gérer votre offre.</p>
      <button
        v-if="available"
        type="button"
        class="mt-4 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900"
        @click="authOpen = true"
      >
        Se connecter
      </button>
    </div>

    <template v-else-if="user">
      <p class="mt-2 text-sm text-slate-600">{{ user.email }}</p>
      <p v-if="loadFailed" class="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">
        Votre compte n’a pas pu être chargé. Réessayez dans un instant.
      </p>

      <div class="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">Mon offre</h2>
        <p v-if="subscribed" class="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-700">
          <span>Abonnement Pro actif : toutes les adresses sont débloquées.</span>
          <button type="button" class="font-medium text-brand-700 underline" @click="manageSubscription">
            Gérer ou résilier
          </button>
        </p>
        <p v-else class="mt-3 text-sm text-slate-700">
          {{ credits }} {{ credits > 1 ? 'audits restants' : 'audit restant' }} sur votre pack.
          <RouterLink :to="{ name: 'pricing' }" class="ml-1 font-medium text-brand-700 underline">Voir les offres</RouterLink>
        </p>
      </div>

      <div class="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">Mes audits débloqués</h2>
        <output v-if="loading" class="skeleton mt-4 block h-16 w-full" aria-label="Chargement"></output>
        <ul v-else-if="audits.length" class="mt-3 divide-y divide-slate-100">
          <li v-for="audit in audits" :key="`${audit.lat}-${audit.lon}`" class="flex items-center justify-between gap-4 py-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-slate-900">{{ audit.label ?? 'Adresse sans libellé' }}</p>
              <p class="text-xs text-slate-500">{{ ORIGINS[audit.origin] }} · {{ formatDate(audit.granted_at) }}</p>
            </div>
            <RouterLink
              :to="auditLink(audit)"
              class="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Ouvrir
            </RouterLink>
          </li>
        </ul>
        <p v-else class="mt-3 text-sm text-slate-600">
          {{ subscribed ? 'Votre abonnement ouvre toutes les adresses : il n’y a rien à débloquer une par une.' : 'Aucune adresse débloquée pour l’instant.' }}
          <RouterLink :to="{ name: 'audit' }" class="ml-1 font-medium text-brand-700 underline">Analyser une adresse</RouterLink>
        </p>
      </div>

      <div class="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 class="text-lg font-semibold text-slate-900">Marque blanche des rapports PDF</h2>
        <p v-if="!subscribed" class="mt-3 text-sm text-slate-600">
          Avec l’offre Pro, vos exports PDF portent votre nom et votre logo.
          <RouterLink :to="{ name: 'pricing' }" class="ml-1 font-medium text-brand-700 underline">Découvrir l’offre Pro</RouterLink>
        </p>
        <form v-else class="mt-4 space-y-4" @submit.prevent="save">
          <div>
            <label for="company" class="block text-sm font-medium text-slate-700">Nom affiché sur les rapports</label>
            <input
              id="company"
              v-model="company"
              type="text"
              required
              maxlength="80"
              class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-brand-600 focus:ring-4 focus:ring-brand-100 focus:outline-none"
            />
          </div>
          <div>
            <label for="logo" class="block text-sm font-medium text-slate-700">Logo (PNG ou JPEG, {{ MAX_LOGO_BYTES / 1024 }} Ko au plus)</label>
            <div class="mt-1 flex flex-wrap items-center gap-4">
              <img v-if="logo" :src="logo" alt="Aperçu du logo" class="h-12 max-w-40 rounded border border-slate-200 bg-white object-contain p-1" />
              <input id="logo" type="file" accept="image/png,image/jpeg" class="text-sm text-slate-600" @change="onLogoChosen" />
              <button v-if="logo" type="button" class="text-sm font-medium text-slate-600 underline" @click="logo = null">
                Retirer le logo
              </button>
            </div>
          </div>
          <div>
            <label for="brand-color" class="block text-sm font-medium text-slate-700">Couleur du bandeau et des titres</label>
            <div class="mt-1 flex flex-wrap items-center gap-3">
              <input id="brand-color" v-model="color" type="color" class="h-10 w-16 cursor-pointer rounded border border-slate-300 bg-white p-1" />
              <span class="font-mono text-sm text-slate-600">{{ color }}</span>
              <button
                v-if="color !== DEFAULT_COLOR"
                type="button"
                class="text-sm font-medium text-slate-600 underline"
                @click="color = DEFAULT_COLOR"
              >
                Couleur par défaut
              </button>
            </div>
          </div>
          <fieldset>
            <legend class="text-sm font-medium text-slate-700">Coordonnées imprimées sous l’en-tête (facultatives)</legend>
            <div class="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div v-for="field in CONTACT_FIELDS" :key="field.key" :class="field.key === 'address' ? 'sm:col-span-2' : ''">
                <label :for="`brand-${field.key}`" class="block text-xs text-slate-500">{{ field.label }}</label>
                <input
                  :id="`brand-${field.key}`"
                  v-model="contact[field.key]"
                  :type="field.type"
                  :maxlength="field.maxlength"
                  :placeholder="field.placeholder"
                  class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-brand-600 focus:ring-4 focus:ring-brand-100 focus:outline-none"
                />
              </div>
            </div>
          </fieldset>
          <p v-if="brandingError" class="text-sm text-rose-700" role="alert">{{ brandingError }}</p>
          <output v-if="brandingNotice" class="block text-sm text-emerald-700">{{ brandingNotice }}</output>
          <div class="flex flex-wrap gap-3">
            <button
              type="submit"
              class="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900 disabled:opacity-50"
              :disabled="busy || !company.trim()"
            >
              Enregistrer
            </button>
            <button
              v-if="saved"
              type="button"
              class="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              :disabled="busy"
              @click="remove"
            >
              Supprimer la marque
            </button>
          </div>
          <p class="text-xs text-slate-500">
            Les sources des données restent citées en pied de page : leurs licences l’exigent.
          </p>
        </form>
      </div>
    </template>

    <AuthModal v-model:open="authOpen" initial-mode="signin" @authenticated="authOpen = false" />
  </section>
</template>
