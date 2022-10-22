import pandas as pd
from core.deck import Deck
from core import utils

DEFAULT_LIFE_POINTS = 8000

DECK_SECTIONS = ['main', 'extra', 'fusion']
GAME_PHASES = ["draw_phase",
               "standby_phase",
               "main_phase_1",
               "battle_phase",
               "main_phase_2",
               "end_phase"]

class PlayField:

    FIELD_SIZE = 5

    def __init__(self):

        self.monster_zone = [None for _ in range(PlayField.FIELD_SIZE)]
        self.spell_and_trap_zone = [None for _ in range(PlayField.FIELD_SIZE)]
        self.graveyard = []
        self.deck = []
        self.extra_deck = []
        self.field_zone = None


class Card:

    def __init__(self):
        pass


class Player:

    def __init__(self, name: str, deck: Deck, life_points=DEFAULT_LIFE_POINTS):
        self.name = name
        self.deck = deck
        self.life_points = life_points


class YGOEngine:

    def __init__(self):

        self.card_db_df = None
        self.decks = {'player_1': Deck(),
                      'player_2': Deck()}

    def load_card_db(self, fpath: str):
        self.card_db_df = pd.read_csv(fpath)

    def load_player_deck(self, player_id: str, fpath: str):
        self.decks[player_id].load_ygoprodeck_deck(blueprint_fpath=fpath)
        valid_card_names = self.card_db_df['Name'].tolist()
        self.decks[player_id].remove_cards_not_in_list(valid_card_names=valid_card_names)

    def play(self, num_turns=10, debug=False):

        for turn_index in range(num_turns):
            print(f'\n==== Game Turn {turn_index + 1} ====')
            for player_id, deck in self.decks.items():
                print(f'> Player: {player_id}')
                for phase in GAME_PHASES:
                    print(f'  - {phase}')

