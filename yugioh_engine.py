
DEFAULT_LIFE_POINTS = 8000

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


class Deck:

    def __init__(self):
        pass

    def load(self, deck_fpath: str):
        pass

    def draw_card(self):
        pass


class Player:

    def __init__(self, name: str, deck: Deck, life_points=DEFAULT_LIFE_POINTS):
        self.name = name
        self.deck = deck
        self.life_points = life_points


class YugiohEngine:

    def __init__(self, card_db_fpath: str):

        pass

    def load_card_db(self, fpath: str):
        pass

    def start_game(self):
        pass



