#!/usr/bin/env python3
"""Hook PreToolUse : refuse la lecture des fichiers .env et les commits qui sautent le hook.

Les règles `deny` de `.claude/settings.json` ne voient que la forme exacte d'une commande
(`cat .env` est bloqué, `head .env` passe) : ce script regarde ce que la commande vise.
Code de sortie 2 : Claude Code annule l'appel et transmet le message à l'agent.
"""

import json
import re
import shlex
import sys

# Fichiers versionnés et publics : les lire ne livre aucun secret.
PUBLIC_ENV = {".env.example", ".env.production"}

ENV_NAME = re.compile(r"\.env(?:\.[\w-]+)*(?![\w-])")

# Options de `git commit` qui prennent une valeur : dans `-am`, ce qui suit `m` est le message.
COMMIT_OPTS_WITH_VALUE = set("mFcCt")


def touches_secret_env(text: str) -> bool:
    for match in ENV_NAME.finditer(text):
        start = match.start()
        # `.venv`, `foo.env` : le point doit commencer un nom de fichier.
        if start > 0 and text[start - 1] not in " \t\n/'\"=<>|;&(`@{,\\:*":
            continue
        if match.group(0) not in PUBLIC_ENV:
            return True
    return False


def split_commands(command: str) -> list[list[str]]:
    """Découpe une ligne en commandes simples, aux séparateurs `;`, `&&`, `||` et `|`."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= set(";&|()"):
            segments.append([])
        else:
            segments[-1].append(token)
    return segments


def skips_commit_hook(command: str) -> bool:
    return any(_segment_skips_hook(tokens) for tokens in split_commands(command))


def _segment_skips_hook(tokens: list[str]) -> bool:
    if not any(token.endswith("git") for token in tokens):
        return False
    # Aussi hors commit : `git config core.hooksPath …` désactive le hook pour la suite.
    for i, token in enumerate(tokens):
        if "core.hooksPath" in token:
            # La lecture seule (`git config core.hooksPath`) reste permise.
            is_read = token == "core.hooksPath" and i == len(tokens) - 1
            if not is_read or any(t.startswith("--unset") for t in tokens):
                return True
    if "commit" not in tokens:
        return False
    for token in tokens[tokens.index("commit") + 1 :]:
        # git accepte les options longues abrégées (`--no-veri`).
        if token.startswith("--no-v"):
            return True
        if token.startswith("-") and not token.startswith("--"):
            for letter in token[1:]:
                if letter == "n":
                    return True
                if letter in COMMIT_OPTS_WITH_VALUE:
                    break
    return False


# Paramètres qui désignent un fichier lu ou écrit, y compris ceux des outils du MCP WebStorm.
# Le `pattern` de Grep porte sur le contenu cherché, pas sur le fichier lu.
PATH_KEYS = (
    "file_path",
    "notebook_path",
    "path",
    "glob",
    "pathInProject",
    "filePath",
    "fileMask",
    "directoryToSearch",
    # apply_patch : le texte du correctif nomme les fichiers touchés.
    "input",
    "patch",
)


def refusal(event: dict) -> str | None:
    tool = event.get("tool_name", "")
    params = event.get("tool_input", {})
    command = params.get("command")
    if isinstance(command, str):
        if touches_secret_env(command):
            return "Commande refusée : elle vise un fichier .env (secrets). Lire .env.example."
        if skips_commit_hook(command):
            return "Commit refusé : --no-verify, -n ou core.hooksPath sautent le hook pre-commit."
    targets = [params.get(key) for key in PATH_KEYS]
    if any(isinstance(target, str) and touches_secret_env(target) for target in targets):
        return f"{tool} refusé : le fichier .env contient des secrets. Lire .env.example."
    return None


def main() -> None:
    message = refusal(json.load(sys.stdin))
    if message:
        print(message, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
