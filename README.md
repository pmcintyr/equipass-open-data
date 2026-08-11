# equipass-open-data architecture Git & CI/CD

Structure de dépôt épurée, pensée pour un environnement d'équipe FEI
(collaboration DevOps GIT/Jira/CI-CD mentionnée dans l'offre), appliquée
ici aux deux livrables précédents (pipeline + dashboard).

## Structure du dépôt

```
.
├── .github/workflows/ci.yml    # pipeline CI/CD (lint, tests, exécution, publication)
├── src/
│   ├── pipeline/                # livrable 1 pipeline Open Data
│   │   ├── pipeline.py
│   │   └── requirements.txt
│   └── dashboard/                # livrable 2 dashboard qualité
│       ├── quality_analysis.sql
│       ├── build_dashboard_data.py
│       └── index.html
├── data/raw/                    # extraits bruts d'entrée (versionnés pour la démo)
├── tests/                        # tests unitaires pytest, exécutés en CI
├── output/                       # généré par le pipeline gitignored, publié en artefact CI
├── docs/                         # documentation complémentaire
├── pyproject.toml                # config ruff (lint) + pytest
├── .gitignore
└── CONTRIBUTING.md
```

## Stratégie de branches

- **`main`** toujours déployable. Protégée : merge uniquement via Pull
  Request, CI verte obligatoire (lint + tests + seuil qualité).
- **`develop`** intégration continue des fonctionnalités avant passage
  en `main`.
- **`feature/<sujet>`** une branche par fonctionnalité ou correction,
  créée depuis `develop`, ex. `feature/microchip-validation`,
  `fix/date-parsing-edge-case`.
- **Tags** `vX.Y.Z` sur `main` à chaque publication de dataset significative
  (changement de schéma, nouvelle règle de qualité).

## Convention de commits

Type Conventional Commits, pour un changelog exploitable et une CI qui
peut réagir au type de changement :

```
feat(pipeline): add ISO 11784 microchip format validation
fix(dashboard): correct completeness calc for internal-only fields
docs(readme): document branching strategy
test(pipeline): cover date parsing edge cases
chore(ci): raise quality gate threshold to 75
```

## Pipeline CI/CD (`.github/workflows/ci.yml`)

| Étape | Déclencheur | Ce qu'elle fait |
|---|---|---|
| `lint-and-test` | push, PR | `ruff check` + `pytest` — bloque le merge si échec |
| `run-pipeline` | push sur `main`, cron quotidien, déclenchement manuel | exécute le pipeline, vérifie un **seuil qualité minimum (70/100)**, publie l'export en artefact CI, commit l'export public rafraîchi |

Le **quality gate** est le point clé pour un contexte Open Data : la CI
échoue explicitement si le score qualité descend sous le seuil, plutôt que
de publier silencieusement un jeu de données dégradé.

## Pourquoi cette architecture pour Equipass

- **Traçabilité** : chaque publication de dataset correspond à un commit
  identifiable, avec son rapport qualité associé en artefact CI.
- **Sécurité de publication** : impossible de publier une régression
  qualité sans passer le gate, utile quand le dataset est public.
- **Onboarding rapide** : structure `src/` par domaine (pipeline,
  dashboard) lisible immédiatement pour un nouveau contributeur de
  l'équipe Technology Operations.
- **Cohérence avec l'existant** : compatible GIT/Jira/CI-CD tel que
  mentionné dans la description de poste, sans réinventer d'outillage
  propriétaire.
