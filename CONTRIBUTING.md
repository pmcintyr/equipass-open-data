# Contribuer

1. Créer une branche depuis `develop` : `git checkout -b feature/mon-sujet develop`
2. Installer les dépendances : `pip install -r src/pipeline/requirements.txt ruff pytest`
3. Développer, avec tests associés dans `tests/`
4. Vérifier localement avant de pousser :
   ```bash
   ruff check src/
   pytest tests/ -v
   python src/pipeline/pipeline.py --input data/raw/equine_passports_raw.csv --outdir output/
   ```
5. Ouvrir une Pull Request vers `develop`, avec un titre au format
   Conventional Commits (voir README). La CI doit être verte avant merge.
6. `develop` est mergée vers `main` par un mainteneur lors d'une publication.
