 """
╔══════════════════════════════════════════════════════════════╗
║         QuizMaster – L'Arène du Savoir                      ║
║         Version Flet (Python desktop / mobile web)          ║
╠══════════════════════════════════════════════════════════════╣
║  INSTALLATION (une seule fois) :                            ║
║      pip install flet requests                              ║
║                                                              ║
║  LANCER SUR PC (fenêtre bureau) :                           ║
║      python main.py                                         ║
║                                                              ║
║  LANCER EN MODE WEB (test sur téléphone) :                  ║
║      flet run --web --port 8080 main.py                     ║
║  → ouvre http://<IP-de-ton-PC>:8080 dans Chrome Android    ║
║                                                              ║
║  GÉNÉRER UN EXÉCUTABLE WINDOWS :                            ║
║      flet build windows                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── Vérification des dépendances AVANT tout import ─────────────────────────────
import sys
import subprocess

def _check_dep(package: str, import_name: str = None) -> bool:
    name = import_name or package
    try:
        __import__(name)
        return True
    except ImportError:
        return False

_missing = []
if not _check_dep("flet"):
    _missing.append("flet")

if _missing:
    print("=" * 60)
    print("  DÉPENDANCES MANQUANTES — QuizMaster ne peut pas démarrer")
    print("=" * 60)
    for pkg in _missing:
        print(f"  ✗  {pkg}  →  pip install {pkg}")
    print("\n  Lance cette commande et relance le programme :")
    print(f"  pip install {' '.join(_missing)}")
    print("=" * 60)
    sys.exit(1)

# ── Imports standards ───────────────────────────────────────────────────────────
import html
import json
import os
import random
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

import flet as ft

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES & PALETTE
# ══════════════════════════════════════════════════════════════════════════════
TIMER_TOTAL   = 10
QUESTIONS_NB  = 10
HISTORY_FILE  = None  # Sera défini dans main() après avoir accès à page.app_data_dir

# Couleurs (format hex pour Flet)
C_BG      = "#0D0D1A"
C_CARD    = "#181830"
C_CARD2   = "#1E1E3A"
C_GOLD    = "#FFD700"
C_GREEN   = "#44FF88"
C_RED     = "#FF4444"
C_ORANGE  = "#FF9900"
C_PURPLE  = "#6666FF"
C_CYAN    = "#33BBEE"
C_VIOLET  = "#BB44EE"
C_TEXT    = "#F2F2FF"
C_MUTED   = "#8080A6"
C_WHITE   = "#FFFFFF"

# Couleurs des 4 boutons réponse
ANSWER_COLORS = [C_PURPLE, C_ORANGE, C_CYAN, C_VIOLET]

# Catégories Open Trivia DB
CATEGORIES = {
    "🎲 Général":      9,
    "🎬 Cinéma":       11,
    "🎵 Musique":      12,
    "🖥️ Informatique": 18,
    "🔬 Sciences":     17,
    "⚽ Sports":       21,
    "🌍 Géographie":   22,
    "📜 Histoire":     23,
    "🎨 Art":          25,
    "🐾 Animaux":      27,
}
DIFFICULTIES = {"Facile": "easy", "Moyen": "medium", "Difficile": "hard"}


# ══════════════════════════════════════════════════════════════════════════════
#  HISTORIQUE LOCAL (JSON)
# ══════════════════════════════════════════════════════════════════════════════
def load_history() -> list:
    try:
        if HISTORY_FILE and os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_game(player: str, score: int, total: int,
              category: str, difficulty: str, mode: str = "Solo"):
    if not HISTORY_FILE:
        return
    history = load_history()
    history.insert(0, {
        "player":     player,
        "score":      score,
        "total":      total,
        "pct":        round(score / total * 100) if total > 0 else 0,
        "category":   category,
        "difficulty": difficulty,
        "mode":       mode,
        "date":       datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    history = history[:50]
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def get_best_score() -> tuple:
    history = load_history()
    if not history:
        return 0, 0
    best = max(history, key=lambda x: x["pct"])
    return best["score"], best["total"]


# ══════════════════════════════════════════════════════════════════════════════
#  API OPEN TRIVIA DB + TRADUCTION
# ══════════════════════════════════════════════════════════════════════════════
def translate_text(text: str) -> str:
    """Traduit EN→FR via MyMemory (gratuit, sans clé). Silencieux en cas d'erreur."""
    try:
        params = urllib.parse.urlencode({"q": text, "langpair": "en|fr"})
        url = f"https://api.mymemory.translated.net/get?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "QuizMaster/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        t = data["responseData"]["translatedText"]
        return t if t and len(t) > 2 else text
    except Exception:
        return text


def fetch_questions(category_id: int, difficulty: str, amount: int = QUESTIONS_NB):
    """
    Retourne (list[dict], None) en cas de succès,
    ou (None, str_erreur) en cas d'échec.
    """
    params = urllib.parse.urlencode({
        "amount": amount,
        "category": category_id,
        "difficulty": difficulty,
        "type": "multiple"
    })
    url = f"https://opentdb.com/api.php?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QuizMaster/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())

        if data.get("response_code") == 1:
            return None, "Pas assez de questions pour cette catégorie.\nEssaie 'Général'."
        if data.get("response_code") == 5:
            return None, "Trop de requêtes. Attends quelques secondes."
        if data.get("response_code") != 0:
            return None, f"Erreur API (code {data.get('response_code')})."

        questions = []
        for q in data["results"]:
            answers = [html.unescape(a) for a in q["incorrect_answers"]]
            correct = html.unescape(q["correct_answer"])
            answers.append(correct)
            random.shuffle(answers)
            questions.append({
                "question": html.unescape(q["question"]),
                "answers":  answers,
                "correct":  correct,
                "category": html.unescape(q["category"]),
            })

        # Traduction FR
        translated = []
        for q in questions:
            q["question"] = translate_text(q["question"])
            q["answers"]  = [translate_text(a) for a in q["answers"]]
            q["correct"]  = translate_text(q["correct"])
            translated.append(q)
        return translated, None

    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            return None, "Délai dépassé (10s).\nRéessaie dans un instant."
        return None, "Pas de connexion internet.\nVérifie ton WiFi/données."
    except OSError:
        return None, "Pas de connexion internet.\nVérifie ton WiFi/données."
    except Exception as e:
        return None, f"Erreur inattendue :\n{e}"


# ══════════════════════════════════════════════════════════════════════════════
#  ÉTAT GLOBAL DE LA PARTIE
# ══════════════════════════════════════════════════════════════════════════════
class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.mode          = "solo"
        self.p1_name       = "Joueur 1"
        self.p2_name       = "Joueur 2"
        self.category_name = "🎲 Général"
        self.category_id   = 9
        self.difficulty    = "medium"
        self.difficulty_name = "Moyen"
        self.questions     = []
        self.q_index       = 0
        self.current_player = 1   # 1 ou 2
        self.p1_score      = 0
        self.p2_score      = 0


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS UI
# ══════════════════════════════════════════════════════════════════════════════
def card(content, padding=16, radius=16, bg=C_CARD) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=bg,
        border_radius=radius,
        padding=padding,
    )


def answer_btn(text: str, color: str, on_click) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text=text,
        on_click=on_click,
        width=999,
        height=58,
        style=ft.ButtonStyle(
            bgcolor={"": color},
            color={"": C_WHITE},
            shape={"": ft.RoundedRectangleBorder(radius=14)},
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD),
            elevation={"": 2},
            overlay_color={"hovered": ft.Colors.with_opacity(0.15, C_WHITE)},
        ),
    )


def primary_btn(text: str, on_click, color=C_GOLD, text_color="#000000",
                height=56, font_size=17) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text=text,
        on_click=on_click,
        width=999,
        height=height,
        style=ft.ButtonStyle(
            bgcolor={"": color},
            color={"": text_color},
            shape={"": ft.RoundedRectangleBorder(radius=14)},
            text_style=ft.TextStyle(size=font_size, weight=ft.FontWeight.BOLD),
            elevation={"": 3},
        ),
    )


def ghost_btn(text: str, on_click, height=46) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        text=text,
        on_click=on_click,
        width=999,
        height=height,
        style=ft.ButtonStyle(
            bgcolor={"": C_CARD2},
            color={"": C_TEXT},
            shape={"": ft.RoundedRectangleBorder(radius=14)},
            text_style=ft.TextStyle(size=14),
        ),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  APPLICATION PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════
def main(page: ft.Page):
    # ── Écran de démarrage immédiat ──────────────────────────────────────────
    page.bgcolor = "#000000"
    page.add(ft.Text("⚡ QuizMaster démarre...", color="white", size=20))
    page.update()

    # ── Configuration de la fenêtre ──────────────────────────────────────────
    page.title        = "QuizMaster – L'Arène du Savoir"
    page.bgcolor      = C_BG
    # Dimensions fenêtre — ignorées sur Android (mobile gère nativement)
    try:
        page.window.width     = 400
        page.window.height    = 800
        page.window.resizable = True
    except Exception:
        pass
    page.fonts = {}  # Flet gère les emojis nativement — aucune police spéciale nécessaire
    page.theme_mode   = ft.ThemeMode.DARK
    page.padding      = 0

    # ── Chemin historique compatible Android ────────────────────────────────
    global HISTORY_FILE
    HISTORY_FILE = os.path.join(page.app_data_dir, "data", "history.json")

    gs = GameState()

    # ── Navigation ───────────────────────────────────────────────────────────
    def go(screen_name: str):
        page.views.clear()
        builders = {
            "home":     build_home,
            "config":   build_config,
            "loading":  build_loading,
            "quiz":     build_quiz,
            "result":   build_result,
            "history":  build_history,
        }
        if screen_name in builders:
            page.views.append(builders[screen_name]())
            page.update()
        else:
            page.snack_bar = ft.SnackBar(ft.Text(f"Écran inconnu : {screen_name}"))
            page.snack_bar.open = True
            page.update()

    # ══════════════════════════════════════════════════════════════════════════
    #  ÉCRAN 1 — ACCUEIL
    # ══════════════════════════════════════════════════════════════════════════
    def build_home() -> ft.View:
        best_s, best_t = get_best_score()
        best_txt = f"🏆  Meilleur : {best_s}/{best_t}" if best_t > 0 else "🏆  Aucune partie"

        return ft.View(
            route="/",
            bgcolor=C_BG,
            padding=24,
            controls=[
                ft.Column(
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=16,
                    controls=[
                        ft.Container(height=16),
                        card(
                            ft.Column(
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=4,
                                controls=[
                                    ft.Text("⚡", size=52, text_align=ft.TextAlign.CENTER),
                                    ft.Text("QUIZMASTER", size=30, weight=ft.FontWeight.BOLD,
                                            color=C_GOLD, text_align=ft.TextAlign.CENTER),
                                    ft.Text("L'Arène du Savoir", size=13, color=C_MUTED,
                                            text_align=ft.TextAlign.CENTER),
                                ],
                            ),
                            padding=20,
                        ),
                        ft.Text(best_txt, size=13, color=C_GOLD,
                                text_align=ft.TextAlign.CENTER),
                        ft.Container(height=8),
                        ft.Text("Choisir un mode", size=12, color=C_MUTED,
                                text_align=ft.TextAlign.CENTER),
                        primary_btn("🎮  Mode Solo",
                                    on_click=lambda _: _start_mode("solo"),
                                    height=58, font_size=17),
                        primary_btn("⚔️  Mode Duel",
                                    on_click=lambda _: _start_mode("duel"),
                                    color=C_PURPLE, text_color=C_WHITE,
                                    height=58, font_size=17),
                        ft.Container(expand=True),
                        ghost_btn("📜  Historique", on_click=lambda _: go("history")),
                    ],
                )
            ],
        )

    def _start_mode(mode: str):
        gs.mode = mode
        go("config")

    # ══════════════════════════════════════════════════════════════════════════
    #  ÉCRAN 2 — CONFIGURATION
    # ══════════════════════════════════════════════════════════════════════════
    def build_config() -> ft.View:
        mode_label = "⚔️ Mode Duel" if gs.mode == "duel" else "🎮 Mode Solo"

        inp_p1 = ft.TextField(
            hint_text="Ton pseudo...", value=gs.p1_name if gs.p1_name != "Joueur 1" else "",
            bgcolor=C_CARD2, color=C_TEXT, hint_style=ft.TextStyle(color=C_MUTED),
            border_color=C_PURPLE, focused_border_color=C_GOLD,
            border_radius=10, height=48,
        )
        inp_p2 = ft.TextField(
            hint_text="Pseudo joueur 2...", value=gs.p2_name if gs.p2_name != "Joueur 2" else "",
            bgcolor=C_CARD2, color=C_TEXT, hint_style=ft.TextStyle(color=C_MUTED),
            border_color=C_PURPLE, focused_border_color=C_GOLD,
            border_radius=10, height=48,
            visible=(gs.mode == "duel"),
        )
        lbl_p2 = ft.Text("Joueur 2 – Pseudo :", size=12, color=C_MUTED,
                         visible=(gs.mode == "duel"))

        dd_cat = ft.Dropdown(
            value=gs.category_name,
            options=[ft.dropdown.Option(k) for k in CATEGORIES],
            bgcolor=C_CARD2, color=C_TEXT,
            border_color=C_PURPLE, focused_border_color=C_GOLD,
            border_radius=10, height=48,
        )
        dd_diff = ft.Dropdown(
            value=gs.difficulty_name,
            options=[ft.dropdown.Option(k) for k in DIFFICULTIES],
            bgcolor=C_CARD2, color=C_TEXT,
            border_color=C_PURPLE, focused_border_color=C_GOLD,
            border_radius=10, height=48,
        )
        err_lbl = ft.Text("", color=C_RED, size=13, text_align=ft.TextAlign.CENTER)

        def _launch(_):
            # Validation
            p1 = inp_p1.value.strip() or "Joueur 1"
            p2 = inp_p2.value.strip() or "Joueur 2"
            if gs.mode == "duel" and p1.lower() == p2.lower():
                err_lbl.value = "❌ Les deux joueurs doivent avoir des pseudos différents."
                page.update()
                return
            cat_name  = dd_cat.value or "🎲 Général"
            diff_name = dd_diff.value or "Moyen"

            gs.p1_name        = p1
            gs.p2_name        = p2
            gs.category_name  = cat_name
            gs.category_id    = CATEGORIES[cat_name]
            gs.difficulty     = DIFFICULTIES[diff_name]
            gs.difficulty_name = diff_name
            gs.current_player = 1
            err_lbl.value = ""
            go("loading")

        return ft.View(
            route="/config",
            bgcolor=C_BG,
            padding=24,
            controls=[
                ft.Column(
                    expand=True,
                    spacing=14,
                    controls=[
                        ft.Row(
                            controls=[
                                ghost_btn("← Retour", on_click=lambda _: go("home"),
                                          height=40),
                                ft.Text(mode_label, size=17, weight=ft.FontWeight.BOLD,
                                        color=C_GOLD, expand=True,
                                        text_align=ft.TextAlign.RIGHT),
                            ],
                        ),
                        card(
                            ft.Column(
                                spacing=8,
                                controls=[
                                    ft.Text("Joueur 1 – Pseudo :", size=12, color=C_MUTED),
                                    inp_p1,
                                    lbl_p2,
                                    inp_p2,
                                ],
                            ),
                            padding=14,
                        ),
                        ft.Text("Catégorie", size=12, color=C_MUTED),
                        dd_cat,
                        ft.Text("Difficulté", size=12, color=C_MUTED),
                        dd_diff,
                        err_lbl,
                        ft.Container(expand=True),
                        primary_btn("🚀  Lancer la partie !", on_click=_launch,
                                    height=62, font_size=18),
                    ],
                )
            ],
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  ÉCRAN 3 — CHARGEMENT
    # ══════════════════════════════════════════════════════════════════════════
    def build_loading() -> ft.View:
        pb     = ft.ProgressBar(width=280, color=C_GOLD, bgcolor=C_CARD2, value=0)
        status = ft.Text("⚡ Chargement & traduction\ndes questions...",
                         size=17, color=C_GOLD, weight=ft.FontWeight.BOLD,
                         text_align=ft.TextAlign.CENTER)

        def _load():
            # Animation progressive de la barre
            for v in range(0, 85, 3):
                pb.value = v / 100
                try:
                    page.update()
                except Exception:
                    return
                time.sleep(0.04)

            questions, err = fetch_questions(gs.category_id, gs.difficulty)

            pb.value = 1.0
            try:
                page.update()
            except Exception:
                return
            time.sleep(0.3)

            if err:
                status.value = f"❌ {err}"
                try:
                    page.update()
                except Exception:
                    return
                time.sleep(3)
                go("home")
            else:
                gs.questions  = questions
                gs.p1_score   = 0
                gs.p2_score   = 0
                gs.q_index    = 0
                go("quiz")

        t = threading.Thread(target=_load, daemon=True)
        t.start()

        return ft.View(
            route="/loading",
            bgcolor=C_BG,
            padding=24,
            controls=[
                ft.Column(
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    main_axis_alignment=ft.MainAxisAlignment.CENTER,
                    spacing=24,
                    controls=[
                        ft.Text("QuizMaster", size=22, color=C_MUTED,
                                weight=ft.FontWeight.BOLD),
                        status,
                        pb,
                        ft.Text(f"Catégorie : {gs.category_name}  •  {gs.difficulty_name}",
                                size=12, color=C_MUTED),
                    ],
                )
            ],
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  ÉCRAN 4 — QUIZ
    # ══════════════════════════════════════════════════════════════════════════
    def build_quiz() -> ft.View:
        # ── Refs aux widgets dynamiques ──
        lbl_player   = ft.Ref[ft.Text]()
        lbl_progress = ft.Ref[ft.Text]()
        lbl_score    = ft.Ref[ft.Text]()
        lbl_timer    = ft.Ref[ft.Text]()
        timer_bar    = ft.Ref[ft.ProgressBar]()
        lbl_category = ft.Ref[ft.Text]()
        lbl_question = ft.Ref[ft.Text]()
        feedback_txt = ft.Ref[ft.Text]()

        # Boutons réponse (liste pour accès par index)
        _btn_refs = [ft.Ref[ft.ElevatedButton]() for _ in range(4)]

        _state = {"answered": False, "timer_event": None, "timer_val": TIMER_TOTAL}

        # ── Rendu d'une question ──────────────────────────────────────────────
        def load_question():
            _state["answered"] = False
            idx = gs.q_index
            q   = gs.questions[idx]
            p   = gs.current_player

            lbl_progress.current.value = f"{idx + 1} / {len(gs.questions)}"
            if gs.mode == "duel":
                name = gs.p1_name if p == 1 else gs.p2_name
                lbl_player.current.value = f"⚔️ {name}"
                lbl_player.current.color = C_GOLD if p == 1 else C_PURPLE
            else:
                lbl_player.current.value = f"🎮 {gs.p1_name}"
                lbl_player.current.color = C_GOLD

            score = gs.p1_score if p == 1 else gs.p2_score
            lbl_score.current.value = f"Score : {score}"

            lbl_category.current.value = q["category"]
            lbl_question.current.value = q["question"]
            feedback_txt.current.value = ""

            for i, ref in enumerate(_btn_refs):
                ref.current.text     = q["answers"][i]
                ref.current.disabled = False
                ref.current.style.bgcolor = {"": ANSWER_COLORS[i]}

            # Timer
            _stop_timer()
            _state["timer_val"] = TIMER_TOTAL
            lbl_timer.current.value = str(TIMER_TOTAL)
            lbl_timer.current.color = C_GREEN
            timer_bar.current.value = 1.0

            try:
                page.update()
            except Exception:
                pass
            _start_timer()

        # ── Timer ────────────────────────────────────────────────────────────
        def _start_timer():
            def _tick():
                while _state["timer_val"] > 0 and not _state["answered"]:
                    time.sleep(1)
                    _state["timer_val"] -= 1
                    v = _state["timer_val"]
                    ratio = v / TIMER_TOTAL

                    try:
                        lbl_timer.current.value = str(v)
                        timer_bar.current.value = ratio
                        lbl_timer.current.color = (
                            C_GREEN  if ratio > 0.5 else
                            C_ORANGE if ratio > 0.25 else
                            C_RED
                        )
                        page.update()
                    except Exception:
                        return

                if not _state["answered"]:
                    _time_up()

            t = threading.Thread(target=_tick, daemon=True)
            _state["timer_event"] = t
            t.start()

        def _stop_timer():
            _state["answered"] = True   # stoppe le thread proprement

        # ── Temps écoulé ─────────────────────────────────────────────────────
        def _time_up():
            _state["answered"] = True
            q = gs.questions[gs.q_index]
            _reveal_correct(q["correct"])
            feedback_txt.current.value = "⏰ Temps écoulé !"
            feedback_txt.current.color = C_RED
            try:
                page.update()
            except Exception:
                pass
            time.sleep(1.5)
            _next_question()

        # ── Répondre ─────────────────────────────────────────────────────────
        def on_answer(e, btn_idx: int):
            if _state["answered"]:
                return
            _state["answered"] = True

            q       = gs.questions[gs.q_index]
            chosen  = _btn_refs[btn_idx].current.text
            correct = q["correct"]

            if chosen == correct:
                _btn_refs[btn_idx].current.style.bgcolor = {"": C_GREEN}
                feedback_txt.current.value = "✔ Bonne réponse !"
                feedback_txt.current.color = C_GREEN
                if gs.current_player == 1:
                    gs.p1_score += 1
                else:
                    gs.p2_score += 1
            else:
                _btn_refs[btn_idx].current.style.bgcolor = {"": C_RED}
                feedback_txt.current.value = "✘ Mauvaise réponse"
                feedback_txt.current.color = C_RED
                _reveal_correct(correct)

            for ref in _btn_refs:
                ref.current.disabled = True

            try:
                page.update()
            except Exception:
                pass

            def _delayed():
                time.sleep(1.3)
                _next_question()
            threading.Thread(target=_delayed, daemon=True).start()

        def _reveal_correct(correct_text: str):
            for ref in _btn_refs:
                if ref.current.text == correct_text:
                    ref.current.style.bgcolor = {"": C_GREEN}
                ref.current.disabled = True

        # ── Question suivante / fin ───────────────────────────────────────────
        def _next_question():
            mode  = gs.mode
            idx   = gs.q_index
            total = len(gs.questions)

            if mode == "duel" and gs.current_player == 1:
                # Passer au joueur 2 pour la MÊME question
                gs.current_player = 2
                _show_handoff()
            else:
                gs.current_player = 1
                gs.q_index = idx + 1
                if gs.q_index >= total:
                    _finish()
                else:
                    load_question()

        def _finish():
            mode = gs.mode
            save_game(gs.p1_name, gs.p1_score, len(gs.questions),
                      gs.category_name, gs.difficulty_name,
                      "Solo" if mode == "solo" else "Duel")
            if mode == "duel":
                save_game(gs.p2_name, gs.p2_score, len(gs.questions),
                          gs.category_name, gs.difficulty_name, "Duel")
            go("result")

        def _show_handoff():
            """Dialog de passage de téléphone en mode Duel."""
            def _close(_):
                dlg.open = False
                page.update()
                load_question()

            dlg = ft.AlertDialog(
                modal=True,
                bgcolor=C_CARD,
                title=ft.Text("⚔️ Passage de tour", color=C_GOLD,
                               weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                content=ft.Text(
                    f"Passe le téléphone à\n{gs.p2_name} !",
                    color=C_TEXT, size=16, text_align=ft.TextAlign.CENTER,
                ),
                actions=[
                    ft.ElevatedButton(
                        "✅ Je suis prêt(e) !",
                        on_click=_close,
                        style=ft.ButtonStyle(
                            bgcolor={"": C_GREEN},
                            color={"": "#000000"},
                            shape={"": ft.RoundedRectangleBorder(radius=10)},
                        ),
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            )
            page.open(dlg)

        # ── Construction de la vue ────────────────────────────────────────────
        view = ft.View(
            route="/quiz",
            bgcolor=C_BG,
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            controls=[
                ft.Column(
                    expand=True,
                    spacing=10,
                    controls=[
                        # Barre haute
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text("", ref=lbl_player, size=15,
                                        weight=ft.FontWeight.BOLD, color=C_GOLD),
                                ft.Text("", ref=lbl_progress, size=13, color=C_MUTED),
                            ],
                        ),
                        # Timer
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text("10", ref=lbl_timer, size=22,
                                        weight=ft.FontWeight.BOLD, color=C_GREEN,
                                        width=36),
                                ft.ProgressBar(ref=timer_bar, value=1.0,
                                               expand=True, height=12,
                                               color=C_GREEN, bgcolor=C_CARD2),
                            ],
                        ),
                        # Score
                        ft.Text("Score : 0", ref=lbl_score, size=13,
                                color=C_MUTED, text_align=ft.TextAlign.RIGHT),
                        # Carte question
                        card(
                            ft.Column(
                                spacing=6,
                                controls=[
                                    ft.Text("", ref=lbl_category, size=11,
                                            color=C_MUTED),
                                    ft.Text("", ref=lbl_question, size=15,
                                            weight=ft.FontWeight.BOLD,
                                            color=C_TEXT,
                                            max_lines=5,
                                            overflow=ft.TextOverflow.VISIBLE),
                                ],
                            ),
                            padding=16,
                        ),
                        # Boutons réponse
                        *[
                            ft.ElevatedButton(
                                ref=_btn_refs[i],
                                text=f"Option {i+1}",
                                on_click=lambda e, idx=i: on_answer(e, idx),
                                width=999,
                                height=58,
                                style=ft.ButtonStyle(
                                    bgcolor={"": ANSWER_COLORS[i]},
                                    color={"": C_WHITE},
                                    shape={"": ft.RoundedRectangleBorder(radius=14)},
                                    text_style=ft.TextStyle(size=14,
                                                            weight=ft.FontWeight.BOLD),
                                ),
                            )
                            for i in range(4)
                        ],
                        # Feedback
                        ft.Text("", ref=feedback_txt, size=14,
                                text_align=ft.TextAlign.CENTER,
                                weight=ft.FontWeight.BOLD),
                    ],
                )
            ],
        )

        # Charger la première question après que la vue est montée
        page.on_view_pop = lambda _: None
        threading.Thread(target=lambda: (time.sleep(0.1), load_question()),
                         daemon=True).start()
        return view

    # ══════════════════════════════════════════════════════════════════════════
    #  ÉCRAN 5 — RÉSULTAT
    # ══════════════════════════════════════════════════════════════════════════
    def build_result() -> ft.View:
        mode  = gs.mode
        s1, s2 = gs.p1_score, gs.p2_score
        total = len(gs.questions)

        if mode == "duel":
            if s1 > s2:
                title, title_color = f"🏆 {gs.p1_name} gagne !", C_GOLD
            elif s2 > s1:
                title, title_color = f"🏆 {gs.p2_name} gagne !", C_GOLD
            else:
                title, title_color = "🤝 Égalité parfaite !", C_GREEN
        else:
            pct = round(s1 / total * 100) if total else 0
            if pct >= 80:
                title, title_color = "🌟 Excellent !", C_GOLD
            elif pct >= 50:
                title, title_color = "👍 Bien joué !", C_GREEN
            else:
                title, title_color = "💪 Continue !", C_ORANGE

        def score_card_widget(name, score, color):
            pct = round(score / total * 100) if total else 0
            return card(
                ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                    controls=[
                        ft.Text(name, size=12, color=C_MUTED),
                        ft.Text(f"{score}/{total}", size=26,
                                weight=ft.FontWeight.BOLD, color=color),
                        ft.Text(f"{pct}%", size=12, color=C_MUTED),
                    ],
                ),
                padding=12,
            )

        scores_row_controls = [score_card_widget(gs.p1_name, s1, C_GOLD)]
        if mode == "duel":
            scores_row_controls.append(score_card_widget(gs.p2_name, s2, C_PURPLE))

        return ft.View(
            route="/result",
            bgcolor=C_BG,
            padding=24,
            controls=[
                ft.Column(
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=16,
                    controls=[
                        ft.Container(height=16),
                        ft.Text(title, size=28, weight=ft.FontWeight.BOLD,
                                color=title_color, text_align=ft.TextAlign.CENTER),
                        ft.Row(
                            controls=scores_row_controls,
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=12,
                        ),
                        ft.Text(f"📂 {gs.category_name}  •  {gs.difficulty_name}",
                                size=13, color=C_MUTED,
                                text_align=ft.TextAlign.CENTER),
                        ft.Container(expand=True),
                        primary_btn("🔄  Rejouer",
                                    on_click=lambda _: go("config"),
                                    height=56, font_size=17),
                        ghost_btn("🏠  Accueil", on_click=lambda _: go("home")),
                        ghost_btn("📜  Voir l'historique",
                                  on_click=lambda _: go("history")),
                    ],
                )
            ],
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  ÉCRAN 6 — HISTORIQUE
    # ══════════════════════════════════════════════════════════════════════════
    def build_history() -> ft.View:
        history = load_history()

        if not history:
            content = ft.Text("Aucune partie jouée pour l'instant.",
                               size=15, color=C_MUTED,
                               text_align=ft.TextAlign.CENTER)
        else:
            rows = []
            for entry in history:
                clr = (C_GREEN  if entry["pct"] >= 80 else
                       C_ORANGE if entry["pct"] >= 50 else C_RED)
                rows.append(
                    card(
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Column(
                                    expand=True,
                                    spacing=2,
                                    controls=[
                                        ft.Text(
                                            f"{entry['player']}  –  {entry['mode']}",
                                            size=14, weight=ft.FontWeight.BOLD,
                                            color=C_TEXT,
                                        ),
                                        ft.Text(
                                            f"{entry['category']}  •  {entry['difficulty']}  •  {entry['date']}",
                                            size=11, color=C_MUTED,
                                        ),
                                    ],
                                ),
                                ft.Column(
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=0,
                                    controls=[
                                        ft.Text(f"{entry['score']}/{entry['total']}",
                                                size=15, weight=ft.FontWeight.BOLD,
                                                color=clr),
                                        ft.Text(f"{entry['pct']}%",
                                                size=11, color=C_MUTED),
                                    ],
                                ),
                            ],
                        ),
                        padding=12,
                    )
                )
            content = ft.ListView(controls=rows, spacing=8, expand=True)

        return ft.View(
            route="/history",
            bgcolor=C_BG,
            padding=16,
            controls=[
                ft.Column(
                    expand=True,
                    spacing=12,
                    controls=[
                        ft.Row(
                            controls=[
                                ghost_btn("← Retour", on_click=lambda _: go("home"),
                                          height=40),
                                ft.Text("📜 Historique", size=19,
                                        weight=ft.FontWeight.BOLD,
                                        color=C_GOLD, expand=True,
                                        text_align=ft.TextAlign.RIGHT),
                            ],
                        ),
                        content if isinstance(content, ft.ListView)
                        else ft.Column(
                            expand=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            main_axis_alignment=ft.MainAxisAlignment.CENTER,
                            controls=[content],
                        ),
                    ],
                )
            ],
        )

    # ── Démarrage sur l'écran Accueil ────────────────────────────────────────
    go("home")


# ══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  QuizMaster – L'Arène du Savoir")
    print("  Démarrage en cours...")
    print("=" * 60)
    try:
        ft.app(target=main)
    except Exception as e:
        print(f"\n[ERREUR FATALE] {e}")
        print("Vérifie que Flet est bien installé : pip install flet")
        sys.exit(1)
