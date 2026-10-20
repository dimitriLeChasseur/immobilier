---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

If the user passes a ticket reference, fetch it from the issue tracker and state its title before starting. If the reference is ambiguous, ask.

> Retouche locale : ce dépôt n'a pas de gestionnaire de tickets ; le travail à faire est celui
> discuté dans la conversation.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "code-review" to review the work.

> Retouche locale : avant le commit, l'agent `verificateur` doit rendre OK, puis
> `gardien-du-projet` ne rien signaler de bloquant sur le diff.

Commit your work to the current branch.
