import os

import pandas as pd
import requests
import re
from bs4 import BeautifulSoup
import concurrent.futures

SCRAPPER_HEADER = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' \
                     '(KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

CARD_DB_COLUMNS = ['table_number', 'internal_number', 'name', 'type', ]
YUGIOH_WIKI_URL = 'https://yugipedia.com'

def get_card_from_id(id: int) -> dict:

    # Get the URL we've been redirect to and process it
    url = f"https://ygoprodeck.com/card/?search={id}"
    r = requests.get(url, {'user-agent': SCRAPPER_HEADER})
    return get_card_from_url(r.url)

def get_card_from_url(url: str) -> dict:

    r = requests.get(url, {'user-agent': SCRAPPER_HEADER})
    soup = BeautifulSoup(r.content, 'lxml')

    card = {}
    card_details_soup = soup.find('div', attrs={'class': 'column2'})

    # Card images
    card['name'] = soup.find('div', attrs={'class': 'card-name'}).text
    card['image_url'] = ''
    card['cropped_image_url'] = ''
    if card_details_soup is not None:
        links = [link.attrs['href'] for link in card_details_soup.find_all('a') if 'href' in link.attrs]
        for link in links:
            matches = re.findall(r'https://images.ygoprodeck.com/images/(.*)/(.*)', link)
            if len(matches) > 0 and len(matches[0]) > 0:
                if matches[0][0] == 'cards':
                    card['image_url'] = link
                if matches[0][0] == 'cards_cropped':
                    card['cropped_image_url'] = link

    # Card attributes
    fields_soup = soup.find_all('li')
    #card['attributes'] = {}
    for field_soup in fields_soup:
        header = field_soup.find('span', attrs={"class": "card-data-header"})
        if header is None:
            continue
        subheader = field_soup.find('span', attrs={"class": "card-data-cost card-data-subheader"})
        if subheader is None:
            continue
        card[header.text.strip(' ').lower()] = subheader.text.strip(' ').lower()

    # Card text
    card['text'] = ''
    card_text_soup = card_details_soup.find('div', attrs={'class': 'card-text'})
    if card_text_soup is not None:
        card['text'] = card_text_soup.text

    return card


def list_card_urls_in_search_page(page_number=1, cards_per_page=24) -> (list, int):

    page_number = page_number if page_number > 0 else 1

    offset = cards_per_page * (page_number - 1)
    url = f"https://ygoprodeck.com/card-database/?&sort=name&num={cards_per_page}&offset={offset}"
    print(url)

    r = requests.get(url, {'user-agent': SCRAPPER_HEADER})
    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.content, 'lxml')
    links = [link.attrs['href'] for link in soup.find_all('a') if 'href' in link.attrs]
    card_urls = [link for link in links if link.startswith('https://ygoprodeck.com/card/')]
    print(card_urls)

    return card_urls, page_number


def get_single_wiki_card(url: str) -> dict:

    r = requests.get(url, {'user-agent': SCRAPPER_HEADER})
    if r.status_code != 200:
        return {}

    card = {}

    soup = BeautifulSoup(r.content, 'lxml')
    card_soup = soup.find('div', attrs={'class': 'card-table'})
    card_name = card_soup.find('div', attrs={'class': 'heading'}).text

    # Add card name
    card['Name'] = card_name

    # Extract default attributes
    card_table_soup = card_soup.find('table', attrs={'class': 'innertable'})
    row_soups = card_table_soup.find_all('tr')
    for row_soup in row_soups:

        # Key
        key_soup = row_soup.find('th')
        if key_soup is None:
            continue
        key = key_soup.text.replace('\n', '').strip()

        # Fix "card type" naming variation
        if key.lower() == 'card type':
            key = 'Type'

        # Value
        value_soup = row_soup.find('td')
        card[key] = value_soup.text.replace('\n', '').strip()

    # Fix Attack and defense values
    if "ATK / DEF" in card:
        matches = re.findall(r"([0-9]*) / ([0-9]*)", card["ATK / DEF"])
        if matches is not None and len(matches[0]) == 2:
            del card["ATK / DEF"]
            card['Attack'] = int(matches[0][0])
            card['Defense'] = int(matches[0][1])

    # Add card description
    description_soup = card_table_soup.find('div', attrs={'class': 'lore'})
    if description_soup is not None:
        card['Description'] = description_soup.text.replace('\n', '').strip()

    return card


def get_card_db_from_wiki(num_threads=32) -> pd.DataFrame:

    """
    Downloads the cards from the Y
    :param num_threads:
    :return:
    """

    cards = []
    def callback(future):
        card = future.result()
        if len(card) > 0:
            print(f" > Card {card['Number']}: {card['Name']}")
            cards.append(card)

    url = "https://yugipedia.com/wiki/List_of_Yu-Gi-Oh!_Worldwide_Edition:_Stairway_to_the_Destined_Duel_cards"

    r = requests.get(url, {'user-agent': SCRAPPER_HEADER})
    if r.status_code != 200:
        return pd.DataFrame()

    soup = BeautifulSoup(r.content, 'lxml')
    table_soup = soup.find('table', attrs={'class': 'wikitable sortable card-list'})
    row_soups = table_soup.find_all('tr')

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        for row_soup in row_soups:

            column_soups = row_soup.find_all('td')
            if len(column_soups) == 0:
                continue

            url = YUGIOH_WIKI_URL + column_soups[2].find('a').attrs['href']
            result = executor.submit(
                get_single_wiki_card,
                url
            )
            result.add_done_callback(callback)

    card_db = pd.DataFrame(cards).drop(columns=['Number', 'Internal number', 'Password'])
    card_db.sort_values(by='Name', inplace=True)
    card_db.reset_index(inplace=True, drop=True)

    return card_db


def load_ygoprodeck_deck(fpath: str):

    with open(fpath, 'r') as file:

        lines = file.readlines()
        valid_lines = [line for line in lines if len(line) > 0]
        section = 'main'

        # Prepare deck
        deck = dict()
        deck['main'] = []
        deck['extra'] = []

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

            deck[section].append((num_cards, matches[0][1]))

    return deck


def create_deck_df(deck_blueprint: dict):

    zone_index = 0
    card_list = []
    for (num_cards, card_name) in deck_blueprint['main']:

        for _ in range(num_cards):
            new_card = {
                "name": card_name,
                "status": "idle",
                "counter": 0,
                "location": "deck",
                "index": zone_index
            }
            card_list.append(new_card)
            zone_index += 1
    return pd.DataFrame(card_list)


if __name__ == "__main__":

    fields = ['id', 'counter', 'location', 'location_index']

    deck_fpath = r"D:\git_repositories\alexandrepv\webscrappers\yugioh_pro_deck\yugioh_engine\decks_ygoprodeck\gaia_deck.txt"
    deck_blueprint = load_ygoprodeck_deck(fpath=deck_fpath)
    deck_df = create_deck_df(deck_blueprint=deck_blueprint)
    g = 0