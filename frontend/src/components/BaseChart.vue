<script setup lang="ts">
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  RadarController,
  RadialLinearScale,
  Tooltip,
  type ChartConfiguration,
} from 'chart.js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  RadarController,
  RadialLinearScale,
  Tooltip,
)

const props = defineProps<{
  config: ChartConfiguration
  /** Description lue par les lecteurs d'écran, et titre du graphique dans le PDF. */
  label: string
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | undefined

function render(): void {
  chart?.destroy()
  if (!canvas.value) return
  chart = new Chart(canvas.value, {
    ...props.config,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // Rendu immédiat : l'export PDF peut capturer le graphique sans attendre une animation.
      animation: false,
      ...props.config.options,
    },
  })
}

onMounted(render)
watch(() => props.config, render)
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div class="relative h-48">
    <!-- Le texte de repli décrit le graphique aux lecteurs d'écran. -->
    <canvas ref="canvas" :data-pdf-chart="label">{{ label }}</canvas>
  </div>
</template>
