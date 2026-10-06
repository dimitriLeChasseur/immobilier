<script setup lang="ts">
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  lat: number
  lon: number
  label: string
  /** Mode « rue » : [lon, lat] des numéros de la voie, tracés à la place du cercle. */
  street?: [number, number][]
}>()

const DVF_RADIUS_M = 300
const DEFAULT_ZOOM = 16

const container = ref<HTMLDivElement | null>(null)
let map: L.Map | undefined
let overlay: L.LayerGroup | undefined

function drawStreet(points: [number, number][]): void {
  if (!map || !overlay) return
  const positions = points.map(([lon, lat]): L.LatLngTuple => [lat, lon])
  for (const position of positions) {
    L.circleMarker(position, { radius: 4, color: '#ffffff', weight: 1, fillColor: '#0f766e', fillOpacity: 0.9 }).addTo(overlay)
  }
  map.fitBounds(L.latLngBounds(positions), { padding: [24, 24], maxZoom: 18 })
}

function draw(): void {
  if (!map || !overlay) return
  const position: L.LatLngTuple = [props.lat, props.lon]
  overlay.clearLayers()
  if (props.street?.length) {
    drawStreet(props.street)
    return
  }
  L.circle(position, {
    radius: DVF_RADIUS_M,
    color: '#0d9488',
    weight: 1.5,
    fillOpacity: 0.08,
  }).addTo(overlay)
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
  map.setView(position, DEFAULT_ZOOM)
}

onMounted(() => {
  if (!container.value) return
  map = L.map(container.value, { scrollWheelZoom: false })
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; contributeurs <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map)
  overlay = L.layerGroup().addTo(map)
  draw()
})

watch(() => [props.lat, props.lon, props.street], draw)
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
  </figure>
</template>
