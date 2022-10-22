import re
import pandas as pd


class Deck:

    def __init__(self):
        self.cards_df = None

    def load_ygoprodeck_deck(self, blueprint_fpath: str):

        with open(blueprint_fpath, 'r') as file:

            lines = file.readlines()
            valid_lines = [line for line in lines if len(line) > 0]
            section = 'main'

            # Prepare blueprint
            blueprint = dict()
            blueprint['main'] = []
            blueprint['extra'] = []

            for line in valid_lines:

                if 'EXTRA DECK' in line:
                    section = 'extra'
                    continue

                matches = re.findall(r'([0-9]*) (.*)', line)

                if matches is None or len(matches) == 0:
                    continue

                if len(matches[0][0]) == 0 or len(matches[0][1]) == 0:
                    continue

                try:
                    num_cards = int(matches[0][0])
                except Exception:
                    continue

                blueprint[section].append((num_cards, matches[0][1]))

        self.cards_df = self._create_deck_df(deck_blueprint=blueprint)

    def remove_cards_not_in_list(self, valid_card_names: list):
        valid_card_indices = [card.Index for card in self.cards_df.itertuples()
                                if card.name in valid_card_names]
        self.cards_df = self.cards_df.iloc[valid_card_indices]
        self.cards_df.reset_index(inplace=True, drop=True)

    def _create_deck_df(self, deck_blueprint: dict) -> pd.DataFrame:

        """
        Converts a deck blueprint to a deck dataframe state so it can be used by the game engine
        :param deck_blueprint: dict, with lists of cards split into sections 'main', 'extra' and 'fusion'
        :return: Pandas Dataframe
        """

        zone_index = 0
        card_list = []
        for section_name, section_cards in deck_blueprint.items():
            for (num_cards, card_name) in deck_blueprint['main']:
                for _ in range(num_cards):
                    new_card = {
                        "section": section_name,
                        "name": card_name,
                        "status": "idle",
                        "counter": 0,
                        "ownership": 0,  # Which player owns this card
                        "zone": "deck",  # Zone where this card is in
                        "zone_index": zone_index,  # Index of the zone this card is in
                        "equipped_to": None  # Card index it is attached to (equippe)
                    }
                    card_list.append(new_card)
                    zone_index += 1

        return pd.DataFrame(card_list)

    def _validate_deck_blueprint(self, deck_blueprint: dict, card_db_df: pd.DataFrame):

        """
        This function returns a valid version of the deck. It automatically removes any missing cards and return
        them as an "invalid deck"

        :param deck_blueprint: dict, deck blueprint
        :param card_db_df:
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