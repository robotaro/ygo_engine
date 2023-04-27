from core.ygo_engine import YGOEngine
from core.card_database import CardDatabase
from core.deck import Deck

# DEBUG
from game_state_visualiser import GameStateVisualiser

if __name__ == "__main__":

    card_db_fpath = r"D:\git_repositories\alexandrepv\ygo_engine\card_databases\card_db_worldwide_edition_stariway_to_the_destined_duel.csv"
    player_1_deck_fpath = r"deck_blueprints/ygoprodeck/kaiba_deck.txt"
    player_2_deck_fpath = r"deck_blueprints/ygoprodeck/ninja_dice_deck.txt"

    card_db = CardDatabase()
    card_db.load(fpath=card_db_fpath)
    deck_p1 = Deck()
    deck_p1.load(fpath=player_1_deck_fpath)
    deck_p2 = Deck()
    deck_p2.load(fpath=player_2_deck_fpath)

    viz = GameStateVisualiser()
    viz.show_game_state(player_1_deck=deck_p1,
                        player_2_deck=deck_p2)

    game = YGOEngine(card_database=card_db)
    game.add_player(player_id='Yugi', deck=deck_p1)
    game.add_player(player_id='Kaiba', deck=deck_p2)
    game.play(num_turns=5)
