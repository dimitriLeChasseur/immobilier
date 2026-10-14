<script setup lang="ts">
/**
 * Maquette éclatée du rapport, en tête de l'accueil : le visiteur voit le livrable avant de
 * saisir une adresse. Uniquement du HTML et du CSS, écrits dans la page dès la construction :
 * ni carte Leaflet ni graphique, qui retarderaient le premier affichage. Les couches dérivent à
 * des vitesses différentes au défilement (style.css, `.parallax-layer`).
 */
defineEmits<{ demo: [] }>()

// Échelle de l'étiquette énergie, longueurs croissantes comme sur un DPE.
const DPE = [
  ['A', 'bg-emerald-600', 'w-5/12'],
  ['B', 'bg-emerald-500', 'w-6/12'],
  ['C', 'bg-lime-500', 'w-7/12'],
  ['D', 'bg-yellow-400', 'w-8/12'],
  ['E', 'bg-amber-500', 'w-9/12'],
  ['F', 'bg-orange-600', 'w-10/12'],
  ['G', 'bg-rose-600', 'w-11/12'],
] as const
const PRICES = ['h-5', 'h-8', 'h-6', 'h-10', 'h-9', 'h-12', 'h-11'] as const
const FINDINGS = [
  ['Risques', 'bg-rose-600', 'border-rose-200 bg-rose-50', 'w-4/5'],
  ['Bruit', 'bg-rose-600', 'border-rose-200 bg-rose-50', 'w-3/5'],
  ['Vie de quartier', 'bg-emerald-600', 'border-emerald-200 bg-emerald-50', 'w-2/3'],
] as const
</script>

<template>
  <button
    type="button"
    class="group relative mx-auto block aspect-[5/4] w-full max-w-md [perspective:1400px] focus-visible:outline-offset-8 lg:max-w-none"
    aria-label="Voir un rapport d’exemple complet"
    @click="$emit('demo')"
  >
    <span class="absolute inset-0 block" aria-hidden="true">
      <!-- Plan du quartier : rues stylisées, cercle des ventes analysées, adresse au centre. -->
      <span
        class="parallax-layer absolute inset-x-6 top-0 bottom-10 block overflow-hidden rounded-3xl bg-white shadow-2xl ring-1 shadow-slate-900/10 ring-slate-900/5 transition-transform duration-700 ease-out [--depth:-18px] [transform:rotateX(6deg)_rotateY(-10deg)] group-hover:[transform:none] motion-reduce:transition-none"
      >
        <span class="flex items-center gap-2 border-b border-slate-100 px-4 py-3 text-left">
          <span class="size-2 rounded-full bg-brand-600"></span>
          <!-- Maquette illustrative : ni adresse ni chiffre réels, pour ne rien laisser croire. -->
          <span class="text-xs font-semibold text-slate-800">Votre adresse</span>
          <span class="ml-auto rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold text-brand-700">Illustration</span>
        </span>
        <svg viewBox="0 0 320 200" class="block h-full w-full" preserveAspectRatio="xMidYMid slice">
          <rect width="320" height="200" fill="#f5f1e8" />
          <g stroke="#ffffff" stroke-linecap="round">
            <path d="M-10 60 L330 40" stroke-width="10" />
            <path d="M-10 150 L330 130" stroke-width="7" />
            <path d="M90 -10 L120 210" stroke-width="8" />
            <path d="M220 -10 L200 210" stroke-width="6" />
            <path d="M-10 105 L330 95" stroke-width="4" />
          </g>
          <g fill="#e2dccd">
            <rect x="20" y="70" width="55" height="22" rx="3" />
            <rect x="135" y="55" width="50" height="30" rx="3" />
            <rect x="140" y="105" width="45" height="22" rx="3" />
            <rect x="230" y="60" width="70" height="25" rx="3" />
            <rect x="25" y="160" width="60" height="25" rx="3" />
            <rect x="225" y="140" width="60" height="30" rx="3" />
          </g>
          <circle cx="160" cy="100" r="62" fill="#14b8a6" fill-opacity="0.08" stroke="#0d9488" stroke-width="1.5" />
          <g fill="#f59e0b" stroke="#ffffff" stroke-width="1.5">
            <circle cx="130" cy="78" r="4.5" />
            <circle cx="190" cy="120" r="4.5" />
            <circle cx="175" cy="70" r="3.5" />
            <circle cx="120" cy="125" r="3.5" />
          </g>
          <circle cx="160" cy="100" r="7" fill="#0f766e" stroke="#ffffff" stroke-width="3" />
        </svg>
      </span>

      <!-- Synthèse : deux alertes, un point fort. -->
      <span
        class="parallax-layer absolute top-12 -left-1 block w-44 rounded-2xl bg-white p-3 text-left shadow-xl ring-1 shadow-slate-900/10 ring-slate-900/5 [--depth:22px] sm:-left-6 sm:w-60"
      >
        <span class="block text-xs font-semibold text-slate-900">L’essentiel : alertes et points forts</span>
        <span class="mt-2 block space-y-1.5">
          <span v-for="[theme, dot, tone, width] in FINDINGS" :key="theme" class="block rounded-lg border px-2 py-1.5" :class="tone">
            <span class="flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-slate-600 uppercase">
              <span class="size-1.5 rounded-full" :class="dot"></span>{{ theme }}
            </span>
            <span class="mt-1 block h-1.5 rounded bg-slate-900/15" :class="width"></span>
          </span>
        </span>
      </span>

      <!-- Étiquette énergie du voisinage. -->
      <span
        class="parallax-layer absolute -right-1 bottom-0 block w-40 rounded-2xl bg-white p-3 text-left shadow-xl ring-1 shadow-slate-900/10 ring-slate-900/5 [--depth:44px] sm:-right-4 sm:w-44"
      >
        <span class="block text-xs font-semibold text-slate-900">DPE du voisinage</span>
        <span class="mt-2 block space-y-0.5">
          <span v-for="[letter, color, width] in DPE" :key="letter" class="flex items-center gap-1.5">
            <span class="block h-2 rounded-r" :class="[color, width]"></span>
            <span class="text-[9px] font-bold" :class="letter === 'D' ? 'text-slate-900' : 'text-slate-400'">{{ letter }}</span>
          </span>
        </span>
      </span>

      <!-- Prix des ventes voisines. -->
      <span
        class="parallax-layer absolute bottom-4 left-6 hidden w-36 rounded-2xl bg-white p-3 text-left shadow-xl ring-1 shadow-slate-900/10 ring-slate-900/5 [--depth:32px] sm:left-10 sm:block"
      >
        <span class="block text-xs font-semibold text-slate-900">Ventes voisines</span>
        <span class="block text-[10px] text-slate-500">Prix au m², année par année</span>
        <span class="mt-2 flex h-12 items-end gap-1">
          <span v-for="(height, index) in PRICES" :key="index" class="block w-full rounded-t bg-brand-500/70" :class="height"></span>
        </span>
      </span>
    </span>
  </button>
</template>
