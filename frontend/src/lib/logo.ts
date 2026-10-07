/** Contrôle côté navigateur du logo de marque blanche ; le serveur revérifie le contenu. */

export const MAX_LOGO_BYTES = 200 * 1024
const ACCEPTED = ['image/png', 'image/jpeg']

/** Message d'erreur si le fichier ne convient pas, null s'il est acceptable. */
export function logoProblem(file: { type: string; size: number }): string | null {
  if (!ACCEPTED.includes(file.type)) return 'Le logo doit être une image PNG ou JPEG.'
  if (file.size > MAX_LOGO_BYTES) return `Le logo doit peser moins de ${MAX_LOGO_BYTES / 1024} Ko.`
  return null
}

export function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('lecture impossible'))
    reader.readAsDataURL(file)
  })
}
