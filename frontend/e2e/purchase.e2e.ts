/**
 * Parcours d'achat joué de bout en bout dans un vrai navigateur :
 * recherche, aperçu gratuit, création de compte, paiement, déblocage du rapport complet.
 *
 *   docker compose up -d --wait db auth backend caddy     # depuis la racine du dépôt
 *   npm run e2e                                           # depuis frontend/
 *
 * Tout est réel (site construit, API, base, service d'authentification) sauf la Base Adresse
 * Nationale, remplacée par des réponses fixes, et Stripe : un faux serveur reçoit la demande de
 * session, puis le test joue le rôle de Stripe en envoyant à l'API
 * l'évènement de paiement, signé avec le secret du test. Le backend testé est lancé ici, à
 * partir du code du dépôt, pour être branché sur ce faux Stripe ; il partage la base et le
 * service d'authentification de la pile Docker (réglages lus dans le .env de la racine).
 * Le compte créé est supprimé en sortant.
 */

import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { createHmac, randomBytes } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium, type Page } from 'playwright'

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ROOT = resolve(FRONTEND, '..')
const SITE_PORT = 4173
const API_PORT = 8011
const SITE = `http://127.0.0.1:${SITE_PORT}`
const API = `http://127.0.0.1:${API_PORT}`
const WEBHOOK_SECRET = `whsec_e2e_${randomBytes(12).toString('hex')}`
const PASSWORD = `E2e-${randomBytes(12).toString('hex')}`
const EMAIL = `e2e-${Date.now()}@test-integration.invalid`
const ADDRESS = {
  id: '49007_7050_00010',
  label: '10 Rue Saint-Aubin 49100 Angers',
  lon: -0.553891,
  lat: 47.46976,
}
const STEP_TIMEOUT_MS = 90_000

/** Réglages du .env de la racine ; les valeurs ne sont jamais affichées. */
function rootEnv(): Record<string, string> {
  const values: Record<string, string> = {}
  for (const line of readFileSync(resolve(ROOT, '.env'), 'utf8').split('\n')) {
    const match = /^([A-Z0-9_]+)=(.*)$/.exec(line)
    if (match?.[1]) values[match[1]] = (match[2] ?? '').replace(/^"(.*)"$/, '$1')
  }
  return values
}

const env = rootEnv()
const AUTH_URL = `http://localhost:${env.HTTP_PORT || '80'}`

interface FakeStripe {
  server: Server
  url: string
  /** Paramètres de la dernière session de paiement demandée par l'API. */
  sessions: URLSearchParams[]
}

/** Faux Stripe : accepte la création d'une session et sert une page de paiement factice. */
async function startFakeStripe(): Promise<FakeStripe> {
  const sessions: URLSearchParams[] = []
  const server = createServer((request, response) => {
    if (request.method === 'POST' && request.url === '/v1/checkout/sessions') {
      let body = ''
      request.on('data', (chunk: Buffer) => (body += chunk.toString()))
      request.on('end', () => {
        sessions.push(new URLSearchParams(body))
        const { port } = server.address() as AddressInfo
        response.writeHead(200, { 'Content-Type': 'application/json' })
        response.end(JSON.stringify({ id: 'cs_test_e2e', url: `http://127.0.0.1:${port}/pay/cs_test_e2e` }))
      })
      return
    }
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
    response.end('<!doctype html><title>Paiement factice</title><h1>Paiement factice</h1>')
  })
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  const { port } = server.address() as AddressInfo
  return { server, url: `http://127.0.0.1:${port}`, sessions }
}

/**
 * Fausse Base Adresse Nationale, côté serveur : géocodage inverse et fiche du numéro. Le
 * parcours ne dépend ainsi d'aucun service extérieur et peut conditionner la mise en ligne.
 */
async function startFakeBan(): Promise<{ server: Server; url: string }> {
  const reverse = {
    features: [
      {
        properties: {
          id: ADDRESS.id,
          label: ADDRESS.label,
          type: 'housenumber',
          housenumber: '10',
          street: 'Rue Saint-Aubin',
          citycode: '49007',
          postcode: '49100',
          city: 'Angers',
          context: '49, Maine-et-Loire, Pays de la Loire',
        },
      },
    ],
  }
  const lookup = {
    type: 'numero',
    numero: 10,
    position: { coordinates: [ADDRESS.lon, ADDRESS.lat] },
    voie: { nomVoie: 'Rue Saint-Aubin' },
    commune: { nom: 'Angers' },
    codePostal: '49100',
  }
  const server = createServer((request, response) => {
    const known = request.url?.startsWith('/reverse/') || request.url === `/lookup/${ADDRESS.id}`
    response.writeHead(known ? 200 : 404, { 'Content-Type': 'application/json' })
    response.end(JSON.stringify(request.url?.startsWith('/reverse/') ? reverse : known ? lookup : {}))
  })
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done))
  const { port } = server.address() as AddressInfo
  return { server, url: `http://127.0.0.1:${port}` }
}

function run(command: string, args: string[], cwd: string, extra: Record<string, string>): ChildProcess {
  // Groupe de processus propre : l'arrêt atteint aussi les processus que la commande a lancés.
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...extra },
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  })
  const output: string[] = []
  const keep = (chunk: Buffer): void => {
    output.push(chunk.toString())
    if (output.length > 200) output.shift()
  }
  child.stdout?.on('data', keep)
  child.stderr?.on('data', keep)
  child.on('exit', (code) => {
    if (code) console.error(`${command} ${args[0] ?? ''} s'est arrêté (code ${code}) :\n${output.join('').slice(-3000)}`)
  })
  return child
}

function stop(child: ChildProcess): void {
  if (child.pid === undefined) return
  try {
    process.kill(-child.pid, 'SIGTERM')
  } catch {
    // Déjà arrêté.
  }
}

function build(extra: Record<string, string>): Promise<void> {
  return new Promise((done, fail) => {
    const child = run('npx', ['vite', 'build', '--outDir', 'dist-e2e', '--logLevel', 'error'], FRONTEND, extra)
    child.on('exit', (code) => (code === 0 ? done() : fail(new Error('construction du site impossible'))))
  })
}

async function waitFor(url: string, what: string): Promise<void> {
  const deadline = Date.now() + STEP_TIMEOUT_MS
  while (Date.now() < deadline) {
    try {
      if ((await fetch(url)).ok) return
    } catch {
      // Pas encore démarré.
    }
    await new Promise((done) => setTimeout(done, 500))
  }
  throw new Error(`${what} ne répond pas (${url})`)
}

/** Évènement « paiement réussi », signé comme le ferait Stripe. */
async function sendPaidEvent(session: URLSearchParams): Promise<void> {
  const metadata: Record<string, string> = {}
  for (const [key, value] of session) {
    const match = /^metadata\[(\w+)\]$/.exec(key)
    if (match?.[1]) metadata[match[1]] = value
  }
  const payload = JSON.stringify({
    id: `evt_e2e_${randomBytes(8).toString('hex')}`,
    type: 'checkout.session.completed',
    created: Math.floor(Date.now() / 1000),
    data: {
      object: {
        id: 'cs_test_e2e',
        mode: 'payment',
        payment_status: 'paid',
        client_reference_id: session.get('client_reference_id'),
        metadata,
      },
    },
  })
  const timestamp = Math.floor(Date.now() / 1000)
  const signature = createHmac('sha256', WEBHOOK_SECRET).update(`${timestamp}.${payload}`).digest('hex')
  const response = await fetch(`${API}/api/v1/stripe/webhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Stripe-Signature': `t=${timestamp},v1=${signature}` },
    body: payload,
  })
  assert.equal(response.status, 200, `l'API a refusé l'évènement de paiement : ${await response.text()}`)
}

async function deleteAccount(userId: string): Promise<void> {
  const response = await fetch(`${AUTH_URL}/auth/v1/admin/users/${userId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${env.SERVICE_ROLE_KEY}`, apikey: env.SERVICE_ROLE_KEY ?? '' },
  })
  if (!response.ok) console.error(`Compte de test ${EMAIL} non supprimé (${response.status}).`)
}

/** Remplace l'autocomplétion de la Base Adresse Nationale par une réponse fixe. */
async function stubAddressSearch(page: Page): Promise<void> {
  await page.route('https://api-adresse.data.gouv.fr/search/**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        features: [
          {
            geometry: { coordinates: [ADDRESS.lon, ADDRESS.lat] },
            properties: { id: ADDRESS.id, label: ADDRESS.label, context: '49, Maine-et-Loire', type: 'housenumber' },
          },
        ],
      }),
    }),
  )
}

async function journey(page: Page, stripe: FakeStripe): Promise<string> {
  page.setDefaultTimeout(STEP_TIMEOUT_MS)
  await stubAddressSearch(page)

  // 1. Recherche : le prix et l'aperçu gratuit sont annoncés dès l'accueil.
  await page.goto(SITE)
  await page.getByText('Aperçu gratuit et sans compte').waitFor()
  await page.getByLabel('Adresse du bien').fill('10 rue saint-aubin angers')
  await page.getByRole('option', { name: /10 Rue Saint-Aubin/ }).click()

  // 2. Aperçu gratuit : le rapport est restreint et le bouton annonce le prix.
  await page.getByText('Aperçu gratuit.').waitFor()
  const unlock = page.getByRole('button', { name: 'Débloquer l’audit complet pour 4,99 €' }).first()
  await unlock.waitFor()
  assert.equal(await page.getByRole('button', { name: 'Exporter en PDF' }).count(), 0)
  await unlock.click()

  // 3. Création de compte, qui mène à la page des tarifs avec l'adresse mémorisée.
  const dialog = page.locator('dialog[open]')
  await dialog.getByLabel('Adresse e-mail').fill(EMAIL)
  await dialog.getByLabel('Mot de passe').fill(PASSWORD)
  await dialog.getByRole('button', { name: 'Créer mon compte' }).click()
  await page.waitForURL(`${SITE}/tarifs`)
  await page.getByText(ADDRESS.label).waitFor()

  // 4. Paiement : l'API demande une session à Stripe, au prix fixé par le serveur.
  await page.getByRole('button', { name: 'Payer 4,99 €' }).click()
  await page.waitForURL(`${stripe.url}/pay/**`)
  const session = stripe.sessions.at(-1)
  assert.ok(session, 'aucune session de paiement demandée')
  assert.equal(session.get('line_items[0][price_data][unit_amount]'), '499')
  assert.equal(session.get('line_items[0][price_data][currency]'), 'eur')
  assert.equal(session.get('metadata[offer]'), 'unit')
  assert.equal(session.get('customer_email'), EMAIL)
  assert.equal(session.get('metadata[ban_id]'), ADDRESS.id, 'adresse résolue par le serveur')
  const userId = session.get('client_reference_id')
  assert.ok(userId)

  const successUrl = session.get('success_url') ?? ''
  assert.ok(successUrl.startsWith(`${SITE}/?`), 'retour vers le site configuré côté serveur')

  // 5. Stripe confirme le paiement à l'API, puis renvoie l'acheteur sur le site.
  await sendPaidEvent(session)
  await page.goto(successUrl)

  // 6. Rapport complet : export PDF proposé, plus aucun cadenas ni bandeau d'aperçu.
  await page.getByRole('button', { name: 'Exporter en PDF' }).waitFor()
  await page.getByText(/Rapport (généré à l’instant|récent repris du cache)/).waitFor()
  assert.equal(await page.getByText('Aperçu gratuit.').count(), 0)
  assert.equal(await page.locator('.locked-blur').count(), 0)

  // L'achat figure dans l'espace client.
  await page.goto(`${SITE}/compte`)
  await page.getByText(ADDRESS.label).first().waitFor()
  return userId
}

async function main(): Promise<void> {
  for (const name of ['IMMO_APP_DB_PASSWORD', 'JWT_SECRET', 'ANON_KEY', 'SERVICE_ROLE_KEY']) {
    assert.ok(env[name], `${name} manque dans le .env de la racine`)
  }
  const stripe = await startFakeStripe()
  const ban = await startFakeBan()
  const processes: ChildProcess[] = []
  const browser = await chromium.launch()
  let userId: string | undefined
  try {
    // Clé du défi anti-robot vidée : le service d'authentification local ne l'exige pas.
    await build({ VITE_TURNSTILE_SITE_KEY: '', VITE_API_URL: API, VITE_SUPABASE_URL: AUTH_URL, VITE_SUPABASE_ANON_KEY: env.ANON_KEY ?? '' })
    processes.push(
      run('uv', ['run', 'uvicorn', 'app.main:app', '--port', String(API_PORT)], resolve(ROOT, 'backend'), {
        APP_ENV: 'test',
        DATABASE_URL: `postgresql://immo_app:${env.IMMO_APP_DB_PASSWORD}@127.0.0.1:${env.DB_HOST_PORT || '5433'}/${env.POSTGRES_DB || 'postgres'}`,
        SUPABASE_JWT_SECRET: env.JWT_SECRET ?? '',
        CORS_ALLOWED_ORIGINS: SITE,
        SITE_URL: SITE,
        STRIPE_SECRET_KEY: 'sk_test_e2e',
        STRIPE_WEBHOOK_SECRET: WEBHOOK_SECRET,
        STRIPE_API_URL: stripe.url,
        BAN_REVERSE_URL: `${ban.url}/reverse/`,
        BAN_LOOKUP_URL: `${ban.url}/lookup`,
        STRIPE_PRO_TAX_RATE_ID: '',
        DEMO_ADDRESS_ID: '',
        SMTP_HOST: '',
      }),
      run('npx', ['vite', 'preview', '--outDir', 'dist-e2e', '--host', '127.0.0.1', '--port', String(SITE_PORT), '--strictPort'], FRONTEND, {}),
    )
    await waitFor(`${API}/health`, 'Le backend de test')
    await waitFor(SITE, 'Le site de test')
    await waitFor(`${AUTH_URL}/auth/v1/health`, 'Le service d’authentification')

    const page = await browser.newPage()
    try {
      userId = await journey(page, stripe)
    } catch (error) {
      await page.screenshot({ path: resolve(FRONTEND, 'e2e-echec.png'), fullPage: true }).catch(() => undefined)
      console.error(`Échec sur ${page.url()} (capture : frontend/e2e-echec.png)`)
      userId = stripe.sessions.at(-1)?.get('client_reference_id') ?? undefined
      throw error
    }
    console.log('Parcours d’achat : recherche, aperçu, inscription, paiement, déblocage — réussi.')
  } finally {
    await browser.close()
    if (userId) await deleteAccount(userId)
    for (const child of processes) stop(child)
    stripe.server.close()
    ban.server.close()
  }
}

main().then(
  () => process.exit(0),
  (error: unknown) => {
    console.error(error)
    process.exit(1)
  },
)
