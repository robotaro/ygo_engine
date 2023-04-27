import re
import pandas as pd
import numpy as np

# ================================================================
#                        Constants
# ================================================================

CARD_DB_COLUMNS = [
    "section",
    "name",
    "status",
    "idle",
    "counter",
    "ownership",
    "zone",
    "zone_index",
    "equipped_to"
]

DECK_BLUEPRINT_TYPE_YGOPRODEK = 'ygoprodeck'

DECK_MAIN_SECTION = 'main'
DECK_EXTRA_SECTION = 'extra'
DECK_FUSION_SECTION = 'fusion'
DECK_SECTIONS = [DECK_MAIN_SECTION, DECK_EXTRA_SECTION, DECK_FUSION_SECTION]


class Deck:

    """
    The deck class stores all cards and performs all operations that change card states.
    """

    def __init__(self):

        # Main variables
        self.cards_df = pd.DataFrame(columns=CARD_DB_COLUMNS)

        # Loading map type
        self.deck_loading_function_map = {
            DECK_BLUEPRINT_TYPE_YGOPRODEK: Deck._load_ygoprodeck_blueprint
        }

        #
        self.main_cards_indices = None
        self.extra_cards_indices = None
        self.fusion_cards_indices = None

    # ================================================================
    #                        Game Action Functions
    # ================================================================

    def shuffle_cards(self, seed=0):
        np.random.seed(seed)
        indices_to_shuffle = np.argwhere((self.cards_df['section'] == DECK_MAIN_SECTION).values).flatten()
        shuffled_indices = indices_to_shuffle.copy()
        np.random.shuffle(shuffled_indices)
        self.cards_df.iloc[indices_to_shuffle] = self.cards_df.iloc[shuffled_indices]

    def draw_cards(self, num_cards=1):

        # Step 1) Find the indices of the cards in the deck zone
        selected_cards_df = self.cards_df[self.cards_df['zone'] == 'deck']

        # Step 2) Get the N last cards according to their zone indices
        # TODO: Change their zone to hand and set their indices according to the hand's current holding cards

    # ================================================================
    #                               Getters
    # ================================================================
    @property
    def size(self):
        return self.cards_df.index.size

    @property
    def main_section_size(self):
        return (self.cards_df['section'] == DECK_MAIN_SECTION).sum()

    @property
    def extra_section_size(self):
        return (self.cards_df['section'] == DECK_EXTRA_SECTION).sum()

    @property
    def fusion_section_size(self):
        return (self.cards_df['section'] == DECK_FUSION_SECTION).sum()

    def get_card_names(self):
        return self.cards_df['name'].tolist()

    # ================================================================
    #                    Deck Construction Functions
    # ================================================================

    def load(self, fpath: str) -> None:

        """
        This function loads a deck from a blueprint into a dataframe that is stored in self.cards_df.
        The blueprint is a text file with a list of cards in the format found in from the following sources:
            - https://ygoprodeck.com/
            - https://ygored.com/

        :param fpath: str, filepath to the blueprint .txt file
        :return: None
        """

        deck_blueprint = {}
        deck_blueprint_type = None
        with open(fpath, 'r') as file:
            first_line = file.readline()
            parts = first_line.split(' ')

            if len(parts) == 0:
                raise ValueError(f'[ERROR] Failing while loading file {fpath}, file not supported')

            if parts[0] == "//":
                deck_blueprint_type = DECK_BLUEPRINT_TYPE_YGOPRODEK
            elif parts[0] == "main":
                raise NotImplementedError(f'[ERROR] YGORED is not supported yet')

            if deck_blueprint_type not in self.deck_loading_function_map:
                raise ValueError(f'[ERROR] Failing while loading file {fpath}, file not supported')

        deck_blueprint = self.deck_loading_function_map[deck_blueprint_type](fpath)

        self.cards_df = self.deck_blueprint2cards_df(deck_blueprint=deck_blueprint)

    @staticmethod
    def validate_deck_blueprint(deck_blueprint: dict, card_db_df: pd.DataFrame):

        """
        This function returns a valid version of the deck. It automatically removes any missing cards and return
        them as an "invalid deck"

        :param deck_blueprint: dict, deck blueprint
        :param card_db_df: Pandas Dataframe
        :return:
        """

        valid_deck_blueprint = {section: [] for section in deck_blueprint.keys()}
        invalid_deck_blueprint = {section: [] for section in deck_blueprint.keys()}
        card_db_names = card_db_df['Name'].tolist()

        for section_name, section_cards in deck_blueprint.items():
            for card_tuple in section_cards:
                if card_tuple[1] in card_db_names:
                    valid_deck_blueprint[section_name].append(card_tuple)
                else:
                    invalid_deck_blueprint[section_name].append(card_tuple)

        return valid_deck_blueprint, invalid_deck_blueprint

    def remove_cards_not_in_list(self, valid_card_names: list):
        valid_card_indices = [card.Index for card in self.cards_df.itertuples() if card.name in valid_card_names]
        self.cards_df = self.cards_df.iloc[valid_card_indices]
        self.cards_df.reset_index(inplace=True, drop=True)

    # ================================================================
    #                      Utility Functions
    # ================================================================

    @staticmethod
    def _load_ygoprodeck_blueprint(blueprint_fpath: str) -> dict:

        blueprint = {}
        with open(blueprint_fpath, 'r') as file:

            lines = file.readlines()
            valid_lines = [line for line in lines if len(line) > 0]
            section = DECK_MAIN_SECTION

            # Prepare blueprint
            blueprint = dict()
            blueprint[DECK_MAIN_SECTION] = []
            blueprint[DECK_EXTRA_SECTION] = []

            # Process each line from thee deck file
            for line in valid_lines:

                if 'EXTRA DECK' in line:
                    section = DECK_EXTRA_SECTION
                    continue

                matches = re.findall(r'([0-9]*) (.*)', line)

                if matches is None or len(matches) == 0:
                    continue

                if len(matches[0][0]) == 0 or len(matches[0][1]) == 0:
                    continue

                try:
                    num_cards = int(matches[0][0])
                except Exception as error:
                    raise Exception(f'[ERROR] Error while loading {error}')

                blueprint[section].append((num_cards, matches[0][1]))
        return blueprint

    def deck_blueprint2cards_df(self, deck_blueprint: dict) -> pd.DataFrame:

        """
        Converts a deck blueprint to a deck dataframe state so it can be used by the game engine
        :param deck_blueprint: dict, with lists of cards split into sections 'main', 'extra' and 'fusion'
        :param auto_validate: if TRUE, it will remove any cards that are not in the card database
        :return: Pandas Dataframe
        """

        zone_index = 0
        card_list = []

        for section_name, section_cards in deck_blueprint.items():
            for (num_cards, card_name) in deck_blueprint[section_name]:
                for _ in range(num_cards):
                    new_card = {
                        "section": section_name,
                        "name": card_name,
                        "status": "inactive",
                        "counter": 0,
                        "ownership": 0,  # Which player owns this card
                        "zone": "deck",  # Zone where this card is in
                        "zone_index": zone_index,  # Index of the zone this card is in
                        "equipped_to": None  # Card index it is attached to (equipped)
                    }
                    card_list.append(new_card)
                    zone_index += 1

        return pd.DataFrame(card_list)
