import pandas as pd

class CardDatabase:

    def __init__(self):
        self.database_df = None
        self.loaded = False
        pass

    def load(self, fpath: str):

        """
        Loads a card database in the .csv format
        :param fpath: str, absolute location of the card database
        :return:
        """
        self.card_db_df = pd.read_csv(fpath)
        self.loaded = True