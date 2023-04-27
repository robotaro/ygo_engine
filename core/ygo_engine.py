import pandas as pd
from core.card_database import CardDatabase
from game_state_visualiser import GameStateVisualiser
from core.deck import Deck

DEFAULT_LIFE_POINTS = 8000

PLAYER_PHASES = [
    "draw_phase",
    "standby_phase",
    "main_phase_1",
    "battle_phase",
    "main_phase_2",
    "end_phase"
]

class PlayField:

    FIELD_SIZE = 5

    def __init__(self):

        self.monster_zone = [None for _ in range(PlayField.FIELD_SIZE)]
        self.spell_and_trap_zone = [None for _ in range(PlayField.FIELD_SIZE)]
        self.graveyard = []
        self.deck = []
        self.extra_deck = []
        self.field_zone = None


class Player:

    def __init__(self, name: str, deck: Deck, life_points=DEFAULT_LIFE_POINTS):
        self.name = name
        self.deck = deck
        self.life_points = life_points


class YGOEngine:

    def __init__(self, card_database: CardDatabase, life_points=DEFAULT_LIFE_POINTS):

        self.initial_player_life_points = life_points
        self.card_db = card_database
        self.players = dict()

    def print_status(self):

        print('[ YGO Engine Status ]')

        # Card Database
        print(' > Card DB: ', end='')
        if self.card_db is None:
            print('Not Loaded')
        else:
            print(f'{self.card_db_df.index.size} cards loaded')

        # Player decks
        for player_name, deck in self.decks.items():
            print(' > Player Deck: ', end='')
            if deck is None:
                print('Not Loaded')
            else:
                print(f'{deck.size} cards loaded '
                      f'(Main: {deck.main_section_size}, '
                      f'Extra: {deck.extra_section_size}, '
                      f'Fusion: {deck.fusion_section_size})')

    def add_player(self, player_id: str, deck: Deck):

        self.players[player_id] = {
            "life_points": self.initial_player_life_points,
            "deck": deck
        }

    def play(self, num_turns=10):

        # Generate game phases
        game_phases = [(player, phase) for player in self.players for phase in PLAYER_PHASES]

        print(' > Game Started:')
        phase_counter = 0
        for turn_index in range(num_turns):

            for _ in range(len(PLAYER_PHASES)):

                current_phase = game_phases[phase_counter % len(game_phases)]
                next_phase = game_phases[(phase_counter + 1) % len(game_phases)]

                self.callback_phase_state(current_stage=current_phase)
                self.callback_phase_transition(stage_from=current_phase, stage_to=next_phase)

                phase_counter += 1

    def callback_phase_transition(self, stage_from: tuple, stage_to: tuple):

        print(f' > {stage_from} -> {stage_to}')


    def callback_phase_state(self, current_stage: tuple):
        print(f' > {current_stage}')

    def show_game_state(self):

        viz = GameStateVisualiser()
        viz.show_game_state()