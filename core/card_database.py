import os
import pandas as pd

DB_COLUMN_NAME = 'Name'
DB_COLUMN_ATTRIBUTE = 'Attribute'
DB_COLUMN_TYPE = 'Type'
DB_COLUMN_LEVEL = 'Level'
DB_COLUMN_ATTACK = 'Attack'
DB_COLUMN_DEFENSE = 'Defense'
DB_COLUMN_DESCRIPTION = 'Description'
DB_COLUMN_PROPERTY = 'Property'
DB_COLUMN_STATUS = 'Status'
DB_COLUMN_LIMITATION = 'Limitation text'


class CardDatabase:

    def __init__(self):
        self.database_df = None
        self.card_name_index_map = None
        self.__loaded = False

    def load(self, fpath: str):

        """
        Loads a card database in the .csv format
        :param fpath: str, absolute location of the card database
        :return:
        """

        # Load the database, or at least try to
        if not os.path.isfile(fpath):
            raise FileNotFoundError(f'[ERROR] Could not open file {fpath}')
        try:
            # Load initial database
            self.database_df = pd.read_csv(fpath)

            # Separate olist
        except Exception as error:
            raise Exception(f'[ERROR] Failed when reading database : {error}')

        # Check for repeated cards
        """card_db_groupped = self.database_df.groupby(DB_COLUMN_NAME)
        for card_name, group_df in card_db_groupped:
            if group_df.index.size > 1:
                print(card_name)
                print(group_df)
                print('')"""
        card_names = self.database_df[DB_COLUMN_NAME].tolist()

        # Create optimised datastructures
        self.card_name_to_index_map = {name: index for index, name in enumerate(card_names)}

        self.__loaded = True

    # ================================================================
    #                           Getters
    # ================================================================

    @property
    def size(self) -> int:  # Total number of cards in the database
        return self.database_df.index.size

    @property
    def card_names(self) -> list:  # List of all card names loaded
        return self.database_df[DB_COLUMN_NAME].tolist()

    @property
    def columns(self):  # List of all card attributes in the database
        return self.database_df.columns

    @property
    def num_spells(self):  # List of all card attributes in the database
        return self.database_df[DB_COLUMN_TYPE] == 'Spell'

    # ================================================================
    #                           Utilities
    # ================================================================

