<script setup lang="ts">
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { MARKER_STYLES, type MapMarker, type MarkerKind } from '../lib/markers'

const props = defineProps<{
  lat: number
  lon: number
  label: string
  /** Mode « rue » : [lon, lat] des numéros de la voie, tracés à la place du cercle. */
  street?: [number, number][]
  /** Ventes, écoles et permis à placer autour de l'adresse. */
  markers?: MapMarker[]
}>()

const DVF_RADIUS_M = 300
// Plan IGN servi par la Géoplateforme : service public ouvert, sans clé, utilisable par un
// produit commercial (les tuiles d'openstreetmap.org ne le sont pas à volume).
const IGN_TILES =
  'https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0' +
  '&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png' +
  '&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}'
const DEFAULT_ZOOM = 16

const container = ref<HTMLDivElement | null>(null)
let map: L.Map | undefined
let overlay: L.LayerGroup | undefined

function drawStreet(points: [number, number][], recentre: boolean): void {
  if (!map || !overlay) return
  const positions = points.map(([lon, lat]): L.LatLngTuple => [lat, lon])
  for (const position of positions) {
    L.circleMarker(position, { radius: 4, color: '#ffffff', weight: 1, fillColor: '#0f766e', fillOpacity: 0.9 }).addTo(overlay)
  }
  if (recentre) map.fitBounds(L.latLngBounds(positions), { padding: [24, 24], maxZoom: 18 })
}

/** Petits points colorés par nature ; le libellé apparaît au survol ou au toucher. */
function drawMarkers(): void {
  if (!overlay) return
  for (const marker of props.markers ?? []) {
    L.circleMarker([marker.lat, marker.lon], {
      // Un immeuble aux nombreuses ventes ressort un peu plus gros.
      radius: (marker.weight ?? 1) > 1 ? 7 : 5,
      color: '#ffffff',
      weight: 1,
      fillColor: MARKER_STYLES[marker.kind].color,
      fillOpacity: 0.85,
    })
      .bindTooltip(marker.label)
      .addTo(overlay)
  }
}

// Seules les natures présentes sur la carte figurent dans la légende.
const legend = computed(() => {
  const present = new Set((props.markers ?? []).map((marker) => marker.kind))
  return (Object.keys(MARKER_STYLES) as MarkerKind[])
    .filter((kind) => present.has(kind))
    .map((kind) => ({ kind, ...MARKER_STYLES[kind] }))
})

/**
 * Redessine la carte. `recentre` est faux quand seuls les points changent (sources arrivant
 * une à une) : le cadrage choisi par l'utilisateur est alors conservé.
 */
function draw(recentre = true): void {
  if (!map || !overlay) return
  const position: L.LatLngTuple = [props.lat, props.lon]
  overlay.clearLayers()
  if (props.street?.length) {
    drawStreet(props.street, recentre)
    drawMarkers()
    return
  }
  // Le cercle est non interactif : il ne doit pas masquer le survol des points qu'il contient.
  L.circle(position, {
    radius: DVF_RADIUS_M,
    color: '#0d9488',
    weight: 1.5,
    fillOpacity: 0.08,
    interactive: false,
  }).addTo(overlay)
  drawMarkers()
  // Marqueur vectoriel : évite les images d'icône de Leaflet, mal résolues par les bundlers.
  L.circleMarker(position, {
    radius: 8,
    color: '#ffffff',
    weight: 3,
    fillColor: '#0f766e',
    fillOpacity: 1,
  })
    .bindTooltip(props.label)
    .addTo(overlay)
  if (recentre) map.setView(position, DEFAULT_ZOOM)
}

onMounted(() => {
  if (!container.value) return
  map = L.map(container.value, { scrollWheelZoom: false })
  L.tileLayer(IGN_TILES, {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.ign.fr/">IGN</a>, Géoplateforme',
  }).addTo(map)
  overlay = L.layerGroup().addTo(map)
  draw()
})

watch(
  () => [props.lat, props.lon, props.street],
  () => draw(),
)
watch(
  () => props.markers,
  () => draw(false),
)
onBeforeUnmount(() => map?.remove())
</script>

<template>
  <figure class="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <div ref="container" class="h-72 w-full lg:h-full lg:min-h-80" role="application" :aria-label="`Carte centrée sur ${label}`"></div>
    <figcaption class="sr-only">
      {{
        street?.length
          ? 'Les points représentent les numéros de la rue analysée.'
          : 'Le cercle représente le rayon de 300 m utilisé pour les prix de vente.'
      }}
    </figcaption>
    <ul v-if="legend.length" class="flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-200 px-4 py-2 text-xs text-slate-600">
      <li v-for="item in legend" :key="item.kind" class="flex items-center gap-1.5">
        <span class="size-2.5 rounded-full" :style="{ backgroundColor: item.color }" aria-hidden="true"></span>
        {{ item.legend }}
      </li>
    </ul>
  </figure>
</template>
