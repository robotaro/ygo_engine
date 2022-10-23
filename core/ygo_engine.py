import pandas as pd
from core.card_database import CardDatabase
from core.deck import Deck

DEFAULT_LIFE_POINTS = 8000


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

    def __init__(self, card_database: CardDatabase):

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

        # Add new player
        self.players[player_id] = {"life_points": DEFAULT_LIFE_POINTS,  "deck": deck}

        # Remove any cards now supported in the current card database


        self.decks[player_id].load(fpath=fpath)
        valid_card_names = self.card_db_df['Name'].tolist()
        self.decks[player_id].remove_cards_not_in_list(valid_card_names=valid_card_names)

    def play(self, num_turns=10):

        self.decks['player_1'].shuffle_cards(seed=123)

        for turn_index in range(num_turns):
            print(f'\n==== Game Turn {turn_index + 1} ====')
            for player_id, deck in self.decks.items():
                print(f'> Player: {player_id}')
                for phase in GAME_PHASES:
                    print(f'  - {phase}')

