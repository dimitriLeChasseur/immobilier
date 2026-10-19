<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import { openBillingPortal, startCheckout, unlockWithCredit } from '../api/billing'
import AuthModal from '../components/AuthModal.vue'
import { useAccount } from '../composables/useAccount'
import { useAuth } from '../composables/useAuth'
import { readPendingAudit } from '../lib/pending'
import { DEMO_QUERY } from '../lib/demo'
import { FREE_OFFER, OFFERS, PRO_DAILY_ADDRESSES, UNIT_PRICE, type Offer } from '../lib/pricing'
import { writeTarget } from '../lib/url'

const { accessToken } = useAuth()
const { account, refresh } = useAccount()
const router = useRouter()

// Adresse mémorisée avant la création de compte : c'est elle que l'achat débloquera.
const pending = readPendingAudit()
// Offre en cours de traitement : ses boutons sont neutralisés jusqu'à la redirection.
const busy = ref<Offer['id'] | 'credit' | 'portal' | null>(null)
const error = ref<string | null>(null)
const authOpen = ref(false)
const cancelled = new URLSearchParams(window.location.search).get('paiement') === 'annule'
// Retour vers l'aperçu de l'adresse mémorisée, avec ses paramètres d'URL.
const backLink = {
  name: 'audit',
  query: pending ? Object.fromEntries(new URLSearchParams(writeTarget(pending, pending.label))) : {},
}

const PRO_OFFER = OFFERS.find((offer) => offer.id === 'pro')

const credits = computed(() => account.value?.credits ?? 0)
const subscribed = computed(() => account.value?.subscription_active ?? false)

/** Exécute une action de paiement ; sans session, ouvre d'abord la connexion. */
async function withSession(action: typeof busy.value, run: (token: string) => Promise<void>): Promise<void> {
  const token = accessToken.value
  if (!token) {
    authOpen.value = true
    return
  }
  busy.value = action
  error.value = null
  try {
    await run(token)
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : 'Le paiement n’a pas pu démarrer.'
    busy.value = null
  }
}

function checkout(offer: Offer): Promise<void> {
  // Le prix est fixé par le serveur : seul l'identifiant de l'offre est transmis.
  return withSession(offer.id, async (token) => {
    window.location.assign(await startCheckout(token, offer.id, pending))
  })
}

function useCredit(): Promise<void> {
  return withSession('credit', async (token) => {
    if (!pending) return
    await unlockWithCredit(token, pending)
    await refresh()
    await router.push(backLink)
  })
}

function manageSubscription(): Promise<void> {
  return withSession('portal', async (token) => {
    window.location.assign(await openBillingPortal(token))
  })
}
</script>

<template>
  <section class="py-10 sm:py-14" aria-labelledby="pricing-title">
    <div class="mx-auto max-w-2xl text-center">
      <h1 id="pricing-title" class="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
        {{ UNIT_PRICE }} pour ne rien découvrir après la signature.
      </h1>
      <p class="mt-3 text-base text-slate-600">
        L’aperçu d’une adresse est gratuit. L’audit complet ajoute les prix réels des ventes voisines, le
        rendement, le bâtiment, le bruit, la synthèse et l’export PDF.
      </p>
      <p
        v-if="pending"
        class="mt-5 inline-flex max-w-full items-center gap-2 rounded-full bg-brand-50 px-4 py-2 text-sm text-brand-900"
      >
        <span class="shrink-0 font-medium">Adresse à débloquer :</span>
        <span class="truncate">{{ pending.label }}</span>
      </p>
    </div>

    <div
      v-if="cancelled || subscribed || credits > 0"
      class="mx-auto mt-8 flex max-w-2xl flex-col gap-3 text-sm"
    >
      <output v-if="cancelled" class="block rounded-xl bg-amber-50 px-4 py-3 text-amber-900">
        Paiement annulé : aucune somme n’a été débitée.
      </output>
      <p v-if="subscribed" class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-emerald-900">
        <span>Abonnement Pro actif : toutes les adresses sont débloquées.</span>
        <button type="button" class="font-medium underline disabled:opacity-50" :disabled="busy !== null" @click="manageSubscription">
          Gérer ou résilier
        </button>
      </p>
      <p v-else-if="credits > 0" class="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-emerald-900">
        <span>{{ credits }} {{ credits > 1 ? 'audits restants' : 'audit restant' }} sur votre pack.</span>
        <button
          v-if="pending"
          type="button"
          class="rounded-lg bg-emerald-700 px-3 py-1.5 font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          :disabled="busy !== null"
          @click="useCredit"
        >
          Débloquer cette adresse avec 1 crédit
        </button>
      </p>
    </div>

    <!-- Sur mobile, le pack recommandé passe en tête ; sur grand écran, il est au centre. -->
    <ul class="mx-auto mt-10 grid max-w-5xl grid-cols-1 items-stretch gap-6 md:grid-cols-3">
      <li
        v-for="offer in OFFERS"
        :key="offer.id"
        class="relative flex flex-col rounded-2xl bg-white p-6"
        :class="
          offer.highlighted
            ? 'order-first border-2 border-brand-600 shadow-xl shadow-brand-700/10 md:order-none'
            : 'border border-slate-200 shadow-sm'
        "
      >
        <p
          v-if="offer.highlighted"
          class="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-1 text-xs font-semibold whitespace-nowrap text-white"
        >
          Recommandé si vous visitez plusieurs biens
        </p>
        <h2 class="text-lg font-semibold text-slate-900">{{ offer.name }}</h2>
        <p class="mt-4 flex flex-wrap items-baseline gap-x-2">
          <span class="text-4xl font-semibold tracking-tight whitespace-nowrap text-slate-900 tabular-nums">{{ offer.price }}</span>
          <span class="text-sm text-slate-500">{{ offer.priceNote }}</span>
        </p>
        <p v-if="offer.anchor" class="mt-2 inline-flex w-fit rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800">
          {{ offer.anchor }}
        </p>
        <p class="mt-4 text-sm text-slate-600">{{ offer.description }}</p>

        <ul class="mt-5 flex-1 space-y-2 text-sm text-slate-700">
          <li v-for="feature in offer.features" :key="feature" class="flex gap-2">
            <svg viewBox="0 0 16 16" class="mt-0.5 size-4 shrink-0 text-brand-600" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M3 8.5 6.5 12 13 4.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            {{ feature }}
          </li>
        </ul>

        <button
          type="button"
          class="mt-6 w-full rounded-lg px-4 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          :class="
            offer.highlighted
              ? 'bg-brand-700 text-white hover:bg-brand-900'
              : 'border border-slate-300 text-slate-800 hover:bg-slate-50'
          "
          :disabled="busy !== null || (offer.id === 'pro' && subscribed)"
          @click="checkout(offer)"
        >
          {{ busy === offer.id ? 'Redirection…' : offer.id === 'pro' && subscribed ? 'Abonnement actif' : offer.cta }}
        </button>
      </li>
    </ul>

    <!-- Le gratuit n'est pas une offre de plus : une porte d'entrée, sous la grille. -->
    <section
      aria-labelledby="free-offer"
      class="mx-auto mt-6 flex max-w-5xl flex-col gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-5 sm:flex-row sm:items-center"
    >
      <div class="min-w-0 flex-1">
        <h2 id="free-offer" class="font-semibold text-slate-900">
          {{ FREE_OFFER.name }} · {{ FREE_OFFER.price }}, {{ FREE_OFFER.priceNote }}
        </h2>
        <p class="mt-1 text-sm text-slate-600">{{ FREE_OFFER.features.join(' · ') }}.</p>
      </div>
      <RouterLink
        :to="backLink"
        class="shrink-0 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-center text-sm font-medium text-slate-800 hover:bg-slate-50"
      >
        {{ pending ? 'Revenir à l’aperçu' : FREE_OFFER.cta }}
      </RouterLink>
    </section>

    <section aria-labelledby="pro-offer" class="mx-auto mt-10 max-w-5xl rounded-2xl bg-slate-900 p-6 text-slate-100 sm:p-8">
      <p class="text-xs font-semibold tracking-wide text-brand-100 uppercase">Offre Pro</p>
      <h2 id="pro-offer" class="mt-2 text-2xl font-semibold tracking-tight text-white">
        Arrivez en rendez-vous avec un dossier à votre nom.
      </h2>
      <p class="mt-3 max-w-2xl text-sm text-slate-300">
        Agents et chasseurs immobiliers : le PDF de chaque bien porte votre logo, pas le nôtre. Vos clients
        reçoivent les ventes voisines, les risques et la synthèse dans un document que vous signez.
      </p>
      <ul class="mt-5 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        <li class="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">Audits sans décompte, jusqu’à {{ PRO_DAILY_ADDRESSES }} nouvelles adresses par jour</li>
        <li class="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">Logo PNG ou JPEG ajouté une fois pour toutes depuis votre compte</li>
        <li v-if="PRO_OFFER" class="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
          {{ PRO_OFFER.price }} {{ PRO_OFFER.priceNote }}, résiliable à tout moment
        </li>
      </ul>
    </section>

    <p v-if="error" class="mx-auto mt-8 max-w-xl rounded-xl bg-rose-50 px-4 py-3 text-center text-sm text-rose-800" role="alert">
      {{ error }}
    </p>
    <p class="mt-8 text-center text-sm text-slate-600">
      Pas sûr de ce que contient l’audit complet ?
      <RouterLink :to="{ name: 'audit', query: DEMO_QUERY }" class="font-medium text-brand-700 underline hover:text-brand-900">
        Voir un rapport d’exemple
      </RouterLink>
    </p>
    <p class="mt-4 text-center text-xs text-slate-500">
      Paiement sécurisé par Stripe. Vos coordonnées bancaires ne transitent pas par nos serveurs.
    </p>
    <p class="mx-auto mt-2 max-w-2xl text-center text-xs text-slate-500">
      La page de paiement vous demande de cocher votre accord aux
      <RouterLink :to="{ name: 'terms' }" class="underline">conditions générales de vente</RouterLink> : l’accès
      immédiat à l’audit vaut renonciation au droit de rétractation pour les audits débloqués.
    </p>

    <p class="mt-8 text-center text-sm text-slate-600">
      <RouterLink
        :to="backLink"
        class="font-medium text-brand-700 underline hover:text-brand-900"
      >
        {{ pending ? 'Revenir à l’aperçu de cette adresse' : 'Analyser une adresse' }}
      </RouterLink>
    </p>
    <AuthModal v-model:open="authOpen" initial-mode="signin" :unlocking="pending !== null" @authenticated="authOpen = false" />
  </section>
</template>
