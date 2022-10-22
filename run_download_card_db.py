import json

import pandas as pd
import requests

import argparse
import concurrent.futures
import os




if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Download all card details from ygoprodeck.com')
    parser.add_argument('output_dir',
                        type=str,
                        help='Output directory where you want ot save the card_db.json')
    parser.add_argument('--num_threads',
                        type=int,
                        default=16,
                        help='Number of threads to download all cards')
    parser.add_argument('--max_pages',
                        type=int,
                        default=511,
                        help='Maximum number of pages of cards to go through')

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Get all cards information using their provided API:
    get_all_cards_url_api = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    r = requests.get(get_all_cards_url_api)
    all_cards_dict = json.loads(r.text)

    # Stage 1) Get a list of all card URLs to download
    page_urls = []
    def page_listing_callback(future):
        card_url_list, page_number = future.result()
        print(f' > Page {page_number}')
        page_urls.append(card_url_list)

    print(f'[ Downloading {args.max_pages} pages of Yu-Gi-Oh Cards]')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.num_threads) as executor:
        for i in range(args.max_pages):
            result = executor.submit(
                utils.list_card_urls_in_search_page,
                i,
                24  # Cards per page
            )
            result.add_done_callback(page_listing_callback)

    card_urls = [card_url for url_list in page_urls for card_url in url_list]
    num_cards = len(card_urls)
    print(f' > Pages processed. {num_cards} Cards found.')

    all_cards = []
    def card_callback(future):
        card = future.result()
        image_filename = os.path.basename(card['image_url'])
        print(f' > Card {image_filename}')

        all_cards.append(card)

    print(f'[ Downloading {num_cards} Yu-Gi-Oh Cards]')
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.num_threads) as executor:
        for url in card_urls:
            result = executor.submit(
                utils.get_card_from_url,
                url
            )
            result.add_done_callback(card_callback)
    print(' > Complete')

    fpath = os.path.join(args.output_dir, 'yu_gi_oh_cards.csv')
    cards_df = pd.DataFrame(all_cards)
    cards_df.to_csv(fpath, index=False, index_label=False)
    print(f' > Cards saved in file: {fpath}')
