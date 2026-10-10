<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { CAPTCHA_SITE_KEY, loadCaptcha, type TurnstileApi } from '../lib/captcha'

/** Jeton à usage unique, null tant que le défi n'est pas passé ou après son expiration. */
const token = defineModel<string | null>({ required: true })

const container = ref<HTMLElement | null>(null)
const failed = ref(false)
let api: TurnstileApi | null = null
let widgetId: string | null = null

onMounted(async () => {
  if (!CAPTCHA_SITE_KEY || !container.value) return
  try {
    api = await loadCaptcha()
  } catch {
    failed.value = true
    return
  }
  if (!container.value) return
  widgetId = api.render(container.value, {
    sitekey: CAPTCHA_SITE_KEY,
    language: 'fr',
    callback: (value) => (token.value = value),
    'expired-callback': () => (token.value = null),
    'error-callback': () => {
      token.value = null
      failed.value = true
    },
  })
})

onBeforeUnmount(() => {
  if (api && widgetId !== null) api.remove(widgetId)
})

/** Un jeton ne sert qu'une fois : à rappeler après chaque envoi du formulaire. */
function reset(): void {
  token.value = null
  if (api && widgetId !== null) api.reset(widgetId)
}

defineExpose({ reset })
</script>

<template>
  <div v-if="CAPTCHA_SITE_KEY">
    <div ref="container"></div>
    <p v-if="failed" class="mt-1 text-xs text-rose-700" role="alert">
      La vérification anti-robot n’a pas pu se charger. Désactivez un éventuel bloqueur puis rechargez la page.
    </p>
  </div>
</template>
