from core.ygo_engine import YGOEngine

if __name__ == "__main__":

    card_db_fpath = r"D:\git_repositories\alexandrepv\ygo_engine\card_databases\card_db_worldwide_edition_stariway_to_the_destined_duel.csv"
    player_1_deck_fpath = r"deck_blueprints/ygoprodeck/kaiba_deck.txt"
    player_2_deck_fpath = r"deck_blueprints/ygoprodeck/ninja_dice_deck.txt"

    app = YGOEngine()
    app.load_card_db(fpath=card_db_fpath)
    app.load_player_deck(player_id="player_1", fpath=player_1_deck_fpath)
    app.load_player_deck(player_id="player_2", fpath=player_2_deck_fpath)
    app.print_status()
    #app.play()