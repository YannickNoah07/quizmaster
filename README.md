# 🏆 QuizMaster – L'Arène du Savoir

## Structure du projet

```
quizmaster/
├── main.py                        ← app principale (point d'entrée Flet)
├── pyproject.toml                 ← config Flet build (PAS de requirements.txt)
├── README.md
└── .github/
    └── workflows/
        └── build.yml              ← workflow GitHub Actions → APK
```

## Tester en local (VS Code / Pydroid)

```bash
pip install flet
python main.py
```

## Tester sur téléphone via WiFi

```bash
flet run --web --port 8080 main.py
```
Ouvre `http://<IP-de-ton-PC>:8080` dans Chrome Android.

## Générer l'APK via GitHub Actions

1. Push sur la branche `main`
2. Va dans l'onglet **Actions** de ton repo GitHub
3. Attends 15–25 minutes (cercle jaune → coche verte)
4. Clique sur le run → télécharge **QuizMaster-APK-v1.0.X**
5. Installe le `.apk` sur Android (active "Sources inconnues")
