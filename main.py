# QuizMaster - L'Arène du Savoir
# Version Flet (Python desktop / mobile)
# Un jeu de quiz interactif multijoueur avec chronomètre, sons et historique.

import flet as ft
import urllib.request
import json
import html
import time
import os
import threading
from typing import List, Dict, Any

# ==========================================
# CONSTANTES DE DESIGN & COULEURS (FLET UI)
# ==========================================
C_BG = "#0B0F19"         # Bleu nuit profond (Fond d'écran)
C_SURFACE = "#1E293B"    # Gris bleuté Slate 800 (Cartes, containers)
C_PRIMARY = "#7C3AED"    # Violet profond (Boutons principaux)
C_SECONDARY = "#F43F5E"  # Rose vif (Accents, erreurs)
C_GOLD = "#FBBF24"       # Jaune or (Trophées, scores)
C_SUCCESS = "#10B981"    # Vert émeraude (Bonnes réponses)
C_MUTED = "#64748B"      # Slate 500 (Texte secondaire)

# Palette des boutons de réponses
ANSWER_COLORS = [
    "#8B5CF6",  # Violet (A)
    "#F97316",  # Orange (B)
    "#06B6D4",  # Cyan (C)
    "#EC4899"   # Rose/Violet (D)
]

# ==========================================
# MOTEUR D'ÉTAT DE JEU (GAME STATE)
# ==========================================
class GameState:
    def __init__(self):
        self.mode = "solo"              # "solo" ou "duel"
        self.player1_name = "Joueur 1"
        self.player2_name = "Joueur 2"
        self.category_id = "any"         # Catégorie Open Trivia DB
        self.difficulty = "medium"      # easy, medium, hard
        
        self.questions: List[Dict[str, Any]] = []
        self.current_question_index = 0
        
        # Mode Solo
        self.solo_score = 0
        
        # Mode Duel
        self.p1_score = 0
        self.p2_score = 0
        self.current_player = 1         # Joueur actif : 1 ou 2
        self.p1_answers: List[int] = [] # Réponses du Joueur 1
        self.p2_answers: List[int] = [] # Réponses du Joueur 2
        
        # Variables de manche
        self.timer_val = 10
        self.timer_running = False
        self.selected_index = None

# Instance globale de l'état
gs = GameState()

# ==========================================
# REQUÊTE ET TRADUCTION DES QUESTIONS (API)
# ==========================================
def fetch_questions(category_id: str, difficulty: str) -> List[Dict[str, Any]]:
    """
    Récupère des questions depuis Open Trivia DB et les traduit en français.
    Remarque importante pour Android : Nécessite une connexion Internet active
    et la permission android.permission.INTERNET déclarée.
    """
    url = f"https://opentdb.com/api.php?amount=10&type=multiple&difficulty={difficulty}"
    if category_id != "any":
        url += f"&category={category_id}"
        
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode())
            if data.get("response_code") == 0:
                raw_questions = data["results"]
                translated_questions = []
                
                for index, q in enumerate(raw_questions):
                    # Traduction simplifiée via l'API publique MyMemory
                    txt_en = html.unescape(q["question"])
                    txt_fr = translate_text(txt_en)
                    
                    # Traduction des options de réponse
                    corr_en = html.unescape(q["correct_answer"])
                    corr_fr = translate_text(corr_en)
                    
                    opts_fr = []
                    for opt in q["incorrect_answers"]:
                        opt_en = html.unescape(opt)
                        opts_fr.append(translate_text(opt_en))
                        
                    # Insertion de la bonne réponse de manière aléatoire
                    import random
                    correct_idx = random.randint(0, 3)
                    options = list(opts_fr)
                    options.insert(correct_idx, corr_fr)
                    
                    translated_questions.append({
                        "category": q["category"],
                        "text": txt_fr,
                        "options": options,
                        "correctIndex": correct_idx,
                        "explanation": f"La bonne réponse était : {corr_fr}."
                    })
                return translated_questions
    except Exception as e:
        print(f"Erreur API / Réseau : {e}")
    return []

def translate_text(text: str) -> str:
    """Traduit une chaîne de caractères de l'anglais vers le français."""
    try:
        query = urllib.parse.quote(text)
        url = f"https://api.mymemory.translated.net/get?q={query}&langpair=en|fr"
        req = urllib.request.Request(url, headers={'User-Agent': 'QuizMasterApp'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            res_data = json.loads(resp.read().decode())
            return res_data["matches"][0]["translation"]
    except Exception:
        # En cas d'erreur de traduction, on retourne le texte brut non traduit
        return text

# ==========================================
# APPLICATION PRINCIPALE FLET
# ==========================================
def main(page: ft.Page):
    page.title = "QuizMaster - L'Arène du Savoir"
    page.bgcolor = C_BG
    page.padding = 0
    # Forcer la taille de la fenêtre (uniquement sur Desktop, ignoré en toute sécurité sur Android)
    try:
        if page.window:
            page.window.width = 410
            page.window.height = 800
            page.window.resizable = True
    except Exception:
        pass
    
    # ------------------------------------------
    # GESTIONNAIRE D'HISTORIQUE LOCAL
    # ------------------------------------------
    def get_history_file_path():
        try:
            # Utilisation de app_data_dir sécurisé sous mobile et desktop
            data_dir = page.app_data_dir if page.app_data_dir else "."
            history_dir = os.path.join(data_dir, "data")
            os.makedirs(history_dir, exist_ok=True)
            return os.path.join(history_dir, "history.json")
        except Exception:
            # Fallback en cas de dossier d'application inaccessible en écriture sur mobile
            return "history.json"

    def load_history() -> list:
        try:
            path = get_history_file_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Erreur de lecture d'historique : {e}")
        return []

    def save_to_history(entry: dict):
        try:
            history = load_history()
            history.insert(0, entry) # Ajoute au début
            # Limite à 15 entrées dans l'historique
            history = history[:15]
            with open(get_history_file_path(), "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erreur d'écriture d'historique : {e}")

    # ------------------------------------------
    # CONTROLES & COMPOSANTS VISUELS
    # ------------------------------------------
    content_area = ft.Container(expand=True)
    
    # Événement : Retourner à l'accueil
    def go_home(e):
        show_home_screen()
        
    def show_home_screen():
        # Chargement du meilleur score
        history = load_history()
        best_score = 0
        for h in history:
            score_val = h.get("score_p1", 0)
            if h.get("mode") == "duel":
                score_val = max(h.get("score_p1", 0), h.get("score_p2", 0))
            if score_val > best_score:
                best_score = score_val

        # Composants de l'écran d'accueil
        logo_icon = ft.Icon(name=ft.Icons.SPARKLES, color=C_GOLD, size=64)
        
        best_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.TROPHY, color=C_GOLD, size=16),
                    ft.Text(f"Meilleur score : {best_score} / 10", color=C_GOLD, weight=ft.FontWeight.BOLD, size=13),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor="#1E1B4B",
            border=ft.border.all(1, "#3730A3"),
            border_radius=20,
            padding=ft.padding.symmetric(16, 8),
            margin=ft.margin.only(bottom=24)
        )

        title = ft.Text(
            "QUIZMASTER",
            size=36,
            weight=ft.FontWeight.BLACK,
            color=ft.Colors.WHITE,
            text_align=ft.TextAlign.CENTER,
            font_family="sans-serif",
        )
        subtitle = ft.Text(
            "L'Arène du Savoir",
            size=18,
            weight=ft.FontWeight.BOLD,
            color=C_SECONDARY,
            text_align=ft.TextAlign.CENTER,
            margin=ft.margin.only(bottom=40),
        )

        btn_solo = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PERSON, size=24),
                    ft.Text("MODE SOLO", size=16, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=C_PRIMARY,
                padding=18,
                shape=ft.RoundedRectangleBorder(radius=14),
            ),
            on_click=lambda e: start_config_flow("solo"),
            width=280,
        )

        btn_duel = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PEOPLE, size=24),
                    ft.Text("MODE DUEL", size=16, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=C_SECONDARY,
                padding=18,
                shape=ft.RoundedRectangleBorder(radius=14),
            ),
            on_click=lambda e: start_config_flow("duel"),
            width=280,
        )

        btn_history = ft.TextButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.HISTORY, color=ft.Colors.WHITE70, size=20),
                    ft.Text("Historique des parties", color=ft.Colors.WHITE70, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_click=lambda e: show_history_screen(),
            width=280,
        )

        home_view = ft.Column(
            [
                ft.Container(height=40),
                logo_icon,
                title,
                subtitle,
                best_badge if best_score > 0 else ft.Container(),
                ft.Column([btn_solo, btn_duel, ft.Container(height=10), btn_history], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO
        )

        content_area.content = ft.Container(
            content=home_view,
            padding=30,
            alignment=ft.alignment.center,
        )
        page.update()

    # ------------------------------------------
    # ÉCRAN DE CONFIGURATION (SAISIE + THÈMES)
    # ------------------------------------------
    def start_config_flow(mode: str):
        gs.mode = mode
        
        lbl_p1 = ft.Text("Pseudo Joueur 1 :", color=ft.Colors.WHITE70, weight=ft.FontWeight.BOLD)
        tf_p1 = ft.TextField(
            value="Joueur 1",
            bgcolor=C_SURFACE,
            border_color="#334155",
            focused_border_color=C_PRIMARY,
            text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            border_radius=10,
        )

        lbl_p2 = ft.Text("Pseudo Joueur 2 :", color=ft.Colors.WHITE70, weight=ft.FontWeight.BOLD)
        tf_p2 = ft.TextField(
            value="Joueur 2",
            bgcolor=C_SURFACE,
            border_color="#334155",
            focused_border_color=C_SECONDARY,
            text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            border_radius=10,
        )

        # Choix de Catégorie
        categories = {
            "Général": "any",
            "Cinéma": "11",
            "Musique": "12",
            "Informatique": "18",
            "Sciences": "17",
            "Sports": "21",
            "Géographie": "22",
            "Histoire": "23",
            "Art": "25",
            "Animaux": "27"
        }
        
        dropdown_cat = ft.Dropdown(
            label="Catégorie de questions",
            options=[ft.dropdown.Option(v, k) for k, v in categories.items()],
            value="any",
            bgcolor=C_SURFACE,
            color=ft.Colors.WHITE,
            border_color="#334155",
            border_radius=10,
        )

        # Difficultés
        dropdown_diff = ft.Dropdown(
            label="Niveau de difficulté",
            options=[
                ft.dropdown.Option("easy", "Facile"),
                ft.dropdown.Option("medium", "Moyen"),
                ft.dropdown.Option("hard", "Difficile")
            ],
            value="medium",
            bgcolor=C_SURFACE,
            color=ft.Colors.WHITE,
            border_color="#334155",
            border_radius=10,
        )

        def on_launch(e):
            gs.player1_name = tf_p1.value.strip() if tf_p1.value.strip() else "Joueur 1"
            if mode == "duel":
                gs.player2_name = tf_p2.value.strip() if tf_p2.value.strip() else "Joueur 2"
            gs.category_id = dropdown_cat.value
            gs.difficulty = dropdown_diff.value
            launch_game()

        btn_launch = ft.ElevatedButton(
            text="LANCER LA PARTIE !",
            on_click=on_launch,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=C_PRIMARY if mode == "solo" else C_SECONDARY,
                padding=16,
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
            width=280
        )

        btn_back = ft.TextButton("Retour", on_click=go_home)

        config_list = [
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_home, icon_color=ft.Colors.WHITE70), ft.Text("Configuration de la partie", size=20, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.START),
            ft.Container(height=15),
            lbl_p1,
            tf_p1,
        ]

        if mode == "duel":
            config_list.extend([ft.Container(height=10), lbl_p2, tf_p2])

        config_list.extend([
            ft.Container(height=15),
            dropdown_cat,
            ft.Container(height=10),
            dropdown_diff,
            ft.Container(height=30),
            ft.Column([btn_launch, btn_back], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        ])

        content_area.content = ft.Container(
            content=ft.Column(config_list, scroll=ft.ScrollMode.AUTO),
            padding=24
        )
        page.update()

    # ------------------------------------------
    # CHARGEMENT DES QUESTIONS INTERACTIF
    # ------------------------------------------
    def launch_game():
        # Écran de chargement
        progress_bar = ft.ProgressBar(width=300, color=C_PRIMARY, bgcolor="#1E293B")
        status_txt = ft.Text("Génération de l'arène de jeu...", color=ft.Colors.WHITE70, size=14, text_align=ft.TextAlign.CENTER)
        
        content_area.content = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.AUTORENEW, color=C_PRIMARY, size=48, animate_rotation=True),
                    ft.Container(height=10),
                    status_txt,
                    ft.Container(height=20),
                    progress_bar
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            alignment=ft.alignment.center
        )
        page.update()

        # Fetch asynchrone des questions
        def worker():
            status_txt.value = "Interrogation de l'API de questions..."
            page.update()
            questions = fetch_questions(gs.category_id, gs.difficulty)
            
            # En cas de panne d'API, charger les questions locales
            if not questions:
                status_txt.value = "API indisponible, chargement des questions locales..."
                page.update()
                time.sleep(1.0)
                # Charger des questions locales simulées
                questions = simulate_local_questions(gs.category_id)
            
            gs.questions = questions
            gs.current_question_index = 0
            gs.solo_score = 0
            gs.p1_score = 0
            gs.p2_score = 0
            gs.current_player = 1
            gs.p1_answers = []
            gs.p2_answers = []
            
            # Début de la partie
            show_question_screen()

        threading.Thread(target=worker, daemon=True).start()

    def simulate_local_questions(category_id: str):
        # Questions locales de secours si l'API est inaccessible ou s'il n'y a pas d'internet
        import random
        
        local_pool = [
            {
                "category": "Science",
                "text": "Quelle est la vitesse de la lumière dans le vide ?",
                "options": ["Environ 300 000 km/s", "Environ 150 000 km/s", "Environ 1 000 000 km/s", "Environ 30 000 km/s"],
                "correctIndex": 0,
                "explanation": "La lumière se déplace à environ 300 000 km/s (exactement 299 792 458 m/s)."
            },
            {
                "category": "Science",
                "text": "Quel est l'élément le plus abondant dans l'univers ?",
                "options": ["L'Oxygène", "L'Hydrogène", "L'Hélium", "Le Carbone"],
                "correctIndex": 1,
                "explanation": "L'Hydrogène représente près de 75% de la masse de toute la matière de l'univers."
            },
            {
                "category": "Science",
                "text": "Quelle planète est surnommée la 'Planète Rouge' ?",
                "options": ["Vénus", "Jupiter", "Mars", "Saturne"],
                "correctIndex": 2,
                "explanation": "Mars a cette couleur en raison de l'oxyde de fer (rouille) sur sa surface."
            },
            {
                "category": "Histoire",
                "text": "En quelle année s'est effondré le mur de Berlin ?",
                "options": ["1985", "1989", "1991", "1993"],
                "correctIndex": 1,
                "explanation": "Le mur est tombé le 9 novembre 1989."
            },
            {
                "category": "Géographie",
                "text": "Quelle est la capitale de l'Australie ?",
                "options": ["Sydney", "Melbourne", "Canberra", "Brisbane"],
                "correctIndex": 2,
                "explanation": "Canberra a été désignée capitale en 1908 comme compromis entre Sydney et Melbourne."
            },
            {
                "category": "Culture Générale",
                "text": "Combien d'octets y a-t-il dans un mégaoctet (Mo) en binaire ?",
                "options": ["1 000 000 octets", "1 048 576 octets", "1 024 octets", "100 000 octets"],
                "correctIndex": 1,
                "explanation": "En informatique, 1 Mo = 1024 Ko = 1 048 576 octets."
            },
            {
                "category": "Histoire",
                "text": "Quel roi de France était surnommé le 'Roi-Soleil' ?",
                "options": ["Louis XIV", "Louis XVI", "Henri IV", "François Ier"],
                "correctIndex": 0,
                "explanation": "Louis XIV a gouverné en monarque absolu sous l'emblème du Soleil."
            },
            {
                "category": "Géographie",
                "text": "Quel est le plus grand océan du globe terrestre ?",
                "options": ["L'océan Atlantique", "L'océan Indien", "L'océan Arctique", "L'océan Pacifique"],
                "correctIndex": 3,
                "explanation": "L'océan Pacifique couvre environ un tiers de la surface de la Terre."
            },
            {
                "category": "Sport",
                "text": "Tous les combien d'années ont lieu les Jeux Olympiques d'été ?",
                "options": ["2 ans", "3 ans", "4 ans", "5 ans"],
                "correctIndex": 2,
                "explanation": "Les JO d'été modernes se déroulent tous les 4 ans."
            },
            {
                "category": "Culture Générale",
                "text": "Qui a peint la célèbre fresque de la Chapelle Sixtine ?",
                "options": ["Léonard de Vinci", "Michel-Ange", "Raphaël", "Donatello"],
                "correctIndex": 1,
                "explanation": "Michel-Ange a réalisé cette œuvre colossale entre 1508 et 1512."
            },
            {
                "category": "Géographie",
                "text": "Quel est le plus long fleuve du monde ?",
                "options": ["Le Nil", "L'Amazone", "Le Mississippi", "Le Yangzi Jiang"],
                "correctIndex": 1,
                "explanation": "L'Amazone est le fleuve le plus long et ayant le débit le plus élevé."
            },
            {
                "category": "Science",
                "text": "Quel organe humain consomme le plus de glucose et d'énergie ?",
                "options": ["Le cœur", "Le cerveau", "Le foie", "Les muscles"],
                "correctIndex": 1,
                "explanation": "Le cerveau consomme environ 20% de toute l'énergie de l'organisme."
            }
        ]
        
        # Filtrer par catégorie si possible
        cat_map = {
            "any": "any",
            "11": "Cinéma",
            "12": "Musique",
            "18": "Informatique",
            "17": "Science",
            "21": "Sport",
            "22": "Géographie",
            "23": "Histoire",
            "25": "Art",
            "27": "Animaux"
        }
        
        target_cat = cat_map.get(category_id, "any")
        
        if target_cat != "any":
            filtered = [q for q in local_pool if q["category"].lower() == target_cat.lower()]
            if len(filtered) >= 3:
                return random.sample(filtered, min(len(filtered), 10))
        
        sample_size = min(len(local_pool), 10)
        return random.sample(local_pool, sample_size)

    # ------------------------------------------
    # ÉCRAN DE QUIZ ET GESTION DU CHRONOMÈTRE
    # ------------------------------------------
    lbl_timer = ft.Text("10s", size=18, weight=ft.FontWeight.BLACK, color=C_GOLD)
    progress_timer = ft.ProgressBar(width=350, value=1.0, color=C_GOLD, bgcolor="#1E293B")
    
    def run_timer():
        """Fonction exécutée dans un thread pour le compte à rebours de 10s."""
        while gs.timer_running and gs.timer_val > 0:
            time.sleep(1)
            if not gs.timer_running:
                break
            gs.timer_val -= 1
            
            # Mise à jour des contrôleurs
            lbl_timer.value = f"{gs.timer_val}s"
            progress_timer.value = gs.timer_val / 10.0
            
            # Alerte couleur si temps faible
            if gs.timer_val <= 3:
                lbl_timer.color = C_SECONDARY
                progress_timer.color = C_SECONDARY
            else:
                lbl_timer.color = C_GOLD
                progress_timer.color = C_GOLD
            page.update()
            
        if gs.timer_running and gs.timer_val == 0:
            # Fin du temps !
            gs.timer_running = False
            handle_time_up()

    def stop_timer():
        gs.timer_running = False

    def handle_time_up():
        # Action de fin de temps
        process_answer(None)

    def show_question_screen():
        if gs.current_question_index >= len(gs.questions):
            # Plus de questions, aller aux résultats
            stop_timer()
            show_results_screen()
            return

        q = gs.questions[gs.current_question_index]
        gs.timer_val = 10
        gs.timer_running = True
        gs.selected_index = None
        
        # Titre d'entête (Solo ou Duel)
        header_text = ""
        header_color = ft.Colors.WHITE
        if gs.mode == "solo":
            header_text = f"Question {gs.current_question_index + 1} / 10"
            score_text = f"Score : {gs.solo_score}"
        else:
            player_active_name = gs.player1_name if gs.current_player == 1 else gs.player2_name
            header_text = f"Tour de {player_active_name}"
            header_color = C_PRIMARY if gs.current_player == 1 else C_SECONDARY
            score_text = f"Q{gs.current_question_index + 1} • P1: {gs.p1_score} - P2: {gs.p2_score}"

        # Éléments de l'interface
        lbl_header = ft.Text(header_text, size=15, weight=ft.FontWeight.BOLD, color=header_color)
        lbl_score = ft.Text(score_text, size=13, weight=ft.FontWeight.BOLD, color=C_MUTED)
        
        # Titre catégorie
        cat_badge = ft.Container(
            content=ft.Text(q["category"].upper(), size=10, weight=ft.FontWeight.BLACK, color=ft.Colors.WHITE),
            bgcolor="#312E81",
            border_radius=4,
            padding=ft.padding.all(4),
            margin=ft.margin.only(bottom=8)
        )

        lbl_question = ft.Text(
            q["text"],
            size=16,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE,
            text_align=ft.TextAlign.CENTER
        )
        
        # Zone de question
        card_question = ft.Container(
            content=ft.Column(
                [
                    cat_badge,
                    lbl_question
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            bgcolor=C_SURFACE,
            padding=20,
            border_radius=16,
            border=ft.border.all(1, "#334155"),
            margin=ft.margin.only(bottom=20),
            shadow=ft.BoxShadow(blur_radius=10, color="rgba(0,0,0,0.3)")
        )

        # Boutons d'options de réponses
        option_buttons = []
        for index, option in enumerate(q["options"]):
            btn = ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(chr(65+index), size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            bgcolor="#0B0F19",
                            border_radius=10,
                            width=24,
                            height=24,
                            alignment=ft.alignment.center
                        ),
                        ft.VerticalDivider(width=1, color="#334155"),
                        ft.Text(option, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                     ],
                    spacing=12,
                ),
                bgcolor=C_SURFACE,
                border=ft.border.all(1, "#1E293B"),
                border_radius=12,
                padding=14,
                on_click=lambda e, idx=index: process_answer(idx),
                animate=ft.Animation(150, "ease")
            )
            option_buttons.append(btn)

        # Affichage du feedback de correction
        feedback_area = ft.Container(visible=False, margin=ft.margin.only(top=15))

        layout = ft.Column(
            [
                ft.Row([lbl_header, lbl_score], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=5),
                ft.Row([lbl_timer, progress_timer], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=10),
                card_question,
                ft.Column(option_buttons, spacing=8),
                feedback_area
            ],
            scroll=ft.ScrollMode.AUTO
        )

        content_area.content = ft.Container(content=layout, padding=20)
        page.update()

        # Démarrage du thread du chronomètre
        threading.Thread(target=run_timer, daemon=True).start()

        # Gestion de clic réponse
        def process_answer(selected_idx: int | None):
            if not gs.timer_running:
                return # Déjà répondu ou temps écoulé
                
            stop_timer()
            gs.selected_index = selected_idx
            correct_idx = q["correctIndex"]
            is_correct = (selected_idx == correct_idx)

            # Enregistrer les scores
            if gs.mode == "solo":
                if is_correct:
                    gs.solo_score += 1
            else:
                if gs.current_player == 1:
                    gs.p1_answers.append(selected_idx)
                    if is_correct:
                        gs.p1_score += 1
                else:
                    gs.p2_answers.append(selected_idx)
                    if is_correct:
                        gs.p2_score += 1

            # Révélation graphique des boutons de réponses
            for i, btn in enumerate(option_buttons):
                btn.on_click = None # Désactive les clics ultérieurs
                if i == correct_idx:
                    btn.bgcolor = C_SUCCESS
                    btn.border = ft.border.all(1, "#34D399")
                elif i == selected_idx:
                    btn.bgcolor = C_SECONDARY
                    btn.border = ft.border.all(1, "#F87171")
                else:
                    btn.opacity = 0.4
            
            # Zone d'explication
            status_text = ""
            status_color = ft.Colors.WHITE
            if selected_idx is None:
                status_text = "⌛ TEMPS ÉCOULÉ !"
                status_color = C_GOLD
            elif is_correct:
                status_text = "✅ EXCELLENTE RÉPONSE !"
                status_color = C_SUCCESS
            else:
                status_text = "❌ MAUVAISE RÉPONSE !"
                status_color = C_SECONDARY

            feedback_area.content = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(status_text, size=14, weight=ft.FontWeight.BLACK, color=status_color),
                        ft.Text(q["explanation"], size=12, color=ft.Colors.WHITE70),
                        ft.Container(height=8),
                        ft.ElevatedButton(
                            text="CONTINUER",
                            on_click=lambda e: next_turn_flow(),
                            style=ft.ButtonStyle(
                                bgcolor=C_PRIMARY,
                                color=ft.Colors.WHITE,
                                shape=ft.RoundedRectangleBorder(radius=8)
                            ),
                            width=180
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                bgcolor="#111827",
                border=ft.border.all(1, "#1F2937"),
                border_radius=12,
                padding=12
            )
            feedback_area.visible = True
            page.update()

    # ------------------------------------------
    # FLUX DE TRANSITION SOLO / DUEL INTERACTIF
    # ------------------------------------------
    def next_turn_flow():
        if gs.mode == "solo":
            gs.current_question_index += 1
            show_question_screen()
        else:
            # Mode Duel : On alterne Joueur 1 et Joueur 2 pour la même question
            if gs.current_player == 1:
                gs.current_player = 2
                show_handoff_screen()
            else:
                gs.current_player = 1
                gs.current_question_index += 1
                show_question_screen()

    def show_handoff_screen():
        """Affiche un écran invitant à passer le téléphone au Joueur 2."""
        lbl_handoff = ft.Text(
            f"Passage de tour !",
            size=24,
            weight=ft.FontWeight.BLACK,
            color=C_GOLD,
            text_align=ft.TextAlign.CENTER
        )
        
        lbl_desc = ft.Text(
            f"Passez l'appareil à {gs.player2_name}\n\nC'est maintenant à son tour de répondre à la même question !",
            size=14,
            color=ft.Colors.WHITE70,
            text_align=ft.TextAlign.CENTER,
            margin=ft.margin.symmetric(0, 10)
        )

        btn_ready = ft.ElevatedButton(
            text="JE SUIS PRÊT !",
            on_click=lambda e: show_question_screen(),
            style=ft.ButtonStyle(
                bgcolor=C_SECONDARY,
                color=ft.Colors.WHITE,
                padding=18,
                shape=ft.RoundedRectangleBorder(radius=12)
            ),
            width=220
        )

        content_area.content = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.MOBILE_SCREEN_SHARE, size=64, color=C_GOLD),
                    ft.Container(height=15),
                    lbl_handoff,
                    ft.Container(height=10),
                    lbl_desc,
                    ft.Container(height=30),
                    btn_ready
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            alignment=ft.alignment.center
        )
        page.update()

    # ------------------------------------------
    # ÉCRAN DES RÉSULTATS FINAUX
    # ------------------------------------------
    def show_results_screen():
        # Sauvegarde de la partie dans l'historique local
        entry = {
            "date": time.strftime("%d/%m/%Y • %H:%M"),
            "mode": gs.mode,
            "category": "Général" if gs.category_id == "any" else gs.category_id,
            "difficulty": gs.difficulty,
            "score_p1": gs.solo_score if gs.mode == "solo" else gs.p1_score,
            "score_p2": gs.p2_score if gs.mode == "duel" else None,
            "p1_name": gs.player1_name,
            "p2_name": gs.player2_name if gs.mode == "duel" else ""
        }
        save_to_history(entry)

        # Design du résultat
        icon_trophy = ft.Icon(ft.Icons.EMOJI_EVENTS, color=C_GOLD, size=64)
        
        title_res = ft.Text("Résultats de la partie !", size=24, weight=ft.FontWeight.BLACK, color=ft.Colors.WHITE)
        
        card_p1 = None
        card_p2 = None

        if gs.mode == "solo":
            score_percent = gs.solo_score * 10
            card_p1 = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(gs.player1_name, size=16, weight=ft.FontWeight.BOLD, color=C_PRIMARY),
                        ft.Text(f"Score final : {gs.solo_score} / 10", size=20, weight=ft.FontWeight.BLACK, color=ft.Colors.WHITE),
                        ft.Text(f"Taux de réussite : {score_percent}%", size=12, color=C_MUTED)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                bgcolor=C_SURFACE,
                padding=20,
                border_radius=14,
                border=ft.border.all(1, "#334155"),
                alignment=ft.alignment.center,
                width=320
            )
        else:
            # Qui a gagné ?
            winner_text = ""
            if gs.p1_score > gs.p2_score:
                winner_text = f"🏆 {gs.player1_name} l'emporte !"
            elif gs.p2_score > gs.p1_score:
                winner_text = f"🏆 {gs.player2_name} l'emporte !"
            else:
                winner_text = "🤝 Match nul parfait !"

            lbl_winner = ft.Text(winner_text, size=18, weight=ft.FontWeight.BLACK, color=C_GOLD, text_align=ft.TextAlign.CENTER)

            card_p1 = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(gs.player1_name, size=14, weight=ft.FontWeight.BOLD, color=C_PRIMARY),
                        ft.Text(f"{gs.p1_score} / 10", size=22, weight=ft.FontWeight.BLACK, color=ft.Colors.WHITE)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                bgcolor=C_SURFACE,
                padding=16,
                border_radius=12,
                border=ft.border.all(1, "#334155"),
                width=150
            )

            card_p2 = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(gs.player2_name, size=14, weight=ft.FontWeight.BOLD, color=C_SECONDARY),
                        ft.Text(f"{gs.p2_score} / 10", size=22, weight=ft.FontWeight.BLACK, color=ft.Colors.WHITE)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ),
                bgcolor=C_SURFACE,
                padding=16,
                border_radius=12,
                border=ft.border.all(1, "#334155"),
                width=150
            )

        btn_retry = ft.ElevatedButton(
            text="REJOUER",
            on_click=lambda e: launch_game(),
            style=ft.ButtonStyle(
                bgcolor=C_PRIMARY,
                color=ft.Colors.WHITE,
                padding=16,
                shape=ft.RoundedRectangleBorder(radius=10)
            ),
            width=280
        )

        btn_home_back = ft.ElevatedButton(
            text="RETOUR ACCUEIL",
            on_click=go_home,
            style=ft.ButtonStyle(
                bgcolor="#1E293B",
                color=ft.Colors.WHITE,
                padding=16,
                shape=ft.RoundedRectangleBorder(radius=10)
            ),
            width=280
        )

        results_layout = [
            ft.Container(height=10),
            icon_trophy,
            title_res,
            ft.Container(height=15)
        ]

        if gs.mode == "solo":
            results_layout.append(card_p1)
        else:
            results_layout.extend([
                lbl_winner,
                ft.Container(height=10),
                ft.Row([card_p1, card_p2], alignment=ft.MainAxisAlignment.CENTER),
            ])

        results_layout.extend([
            ft.Container(height=30),
            ft.Column([btn_retry, btn_home_back], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10)
        ])

        content_area.content = ft.Container(
            content=ft.Column(results_layout, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
            padding=24
        )
        page.update()

    # ------------------------------------------
    # ÉCRAN DE L'HISTORIQUE DE JEUX
    # ------------------------------------------
    def show_history_screen():
        history = load_history()
        
        lbl_hist_title = ft.Text("Historique des scores", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
        
        history_cards = []
        if not history:
            history_cards.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.HISTORY_TOGGLE_OFF, size=48, color=C_MUTED),
                            ft.Text("Aucune partie enregistrée.", color=C_MUTED, size=12)
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    margin=ft.margin.only(top=40),
                    alignment=ft.alignment.center
                )
            )
        else:
            for entry in history:
                mode = entry.get("mode", "solo").upper()
                date = entry.get("date", "")
                
                # Format du texte de score
                score_str = ""
                if mode == "SOLO":
                    score_str = f"Score : {entry.get('score_p1', 0)} / 10"
                else:
                    score_str = f"P1 ({entry.get('p1_name', 'J1')}) : {entry.get('score_p1', 0)} / 10\nP2 ({entry.get('p2_name', 'J2')}) : {entry.get('score_p2', 0)} / 10"

                card = ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(f"MODE {mode}", size=11, weight=ft.FontWeight.BLACK, color=C_PRIMARY if mode == "SOLO" else C_SECONDARY),
                                    ft.Text(date, size=10, color=C_MUTED)
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                            ),
                            ft.Divider(height=1, color="#334155"),
                            ft.Text(score_str, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Row(
                                [
                                    ft.Text(f"Cat: {entry.get('category', 'Toutes')}", size=10, color=C_MUTED),
                                    ft.Text(f"Diff: {entry.get('difficulty', 'medium')}", size=10, color=C_MUTED)
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                            )
                        ],
                        spacing=6
                    ),
                    bgcolor=C_SURFACE,
                    padding=12,
                    border_radius=10,
                    border=ft.border.all(1, "#334155"),
                    margin=ft.margin.only(bottom=8)
                )
                history_cards.append(card)

        btn_back = ft.ElevatedButton(
            "RETOUR ACCUEIL", 
            on_click=go_home,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), bgcolor=C_PRIMARY, color=ft.Colors.WHITE),
            width=200
        )

        content_area.content = ft.Container(
            content=ft.Column(
                [
                    ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=go_home, icon_color=ft.Colors.WHITE70), lbl_hist_title]),
                    ft.Container(height=10),
                    ft.Column(history_cards, scroll=ft.ScrollMode.AUTO, height=480),
                    ft.Container(height=15),
                    ft.Row([btn_back], alignment=ft.MainAxisAlignment.CENTER)
                ],
            ),
            padding=20
        )
        page.update()

    # ------------------------------------------
    # INITIALISATION DE L'APPLICATION
    # ------------------------------------------
    page.add(content_area)
    show_home_screen()

ft.app(target=main)
