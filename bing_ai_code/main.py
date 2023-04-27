import matplotlib.pyplot as plt
import matplotlib.patches as patches


"""
Great, now let's look into the logic of the game. Each card contains a short description of it's illustration and/or effects. For cards with effects, these are designed to change the battle mechanics so that the flow of the game changes in favour of the player. Here is an example of a trap card description: "Select 1 of your opponent's face-up monsters. The ATK of the selected monster is decreased by 700 points and its battle position cannot be changed. When the monster is destroyed, this card is also destroyed."
"""

class Card:
    def __init__(self, name, description):
        self.name = name
        self.description = description

    def select_opponent_monster(self, game_state):
        # Implement logic for selecting one of the opponent's face-up monsters
        pass

    def decrease_atk(self, monster, amount):
        # Implement logic for decreasing a monster's ATK by the specified amount
        pass

    def prevent_battle_position_change(self, monster):
        # Implement logic for preventing a monster's battle position from being changed
        pass

    def activate(self, game_state):
        # Implement logic for activating the card and applying its effects
        pass

class Game:
    def __init__(self):
        # Initialize game state here
        self.board_positions = {
            0: (2.5, 7), 1: (3.5, 7), 2: (4.5, 7), 3: (5.5, 7), 4: (6.5, 7),
            5: (2.5, 6), 6: (3.5, 6), 7: (4.5, 6), 8: (5.5, 6), 9: (6.5, 6),
            10: (1.5, 7),
            11: (2.5, 2), 12: (3.5, 2), 13: (4.5, 2), 14: (5.5, 2), 15: (6.5, 2),
            16: (2.5, 3), 17: (3.5, 3), 18: (4.5, 3), 19: (5.5, 3), 20: (6.5, 3),
            21: (1.5, 2)
        }

    def plot_board(self, card_positions=None):
        fig, ax = plt.subplots(1)
        ax.set_xlim([0, 10])
        ax.set_ylim([0, 10])

        if card_positions is None:
            card_positions = []

        # Draw Main Monster Zones
        for i in range(5):
            ax.add_patch(patches.Rectangle((i + 2.5, 7), 1, 1, edgecolor='black', facecolor='none'))
            ax.add_patch(patches.Rectangle((i + 2.5, 2), 1, 1, edgecolor='black', facecolor='none'))

        # Draw Spell & Trap Zones
        for i in range(5):
            ax.add_patch(patches.Rectangle((i + 2.5, 6), 1, 1, edgecolor='black', facecolor='none'))
            ax.add_patch(patches.Rectangle((i + 2.5, 3), 1, 1, edgecolor='black', facecolor='none'))

        # Draw Extra Deck Zones
        ax.add_patch(patches.Rectangle((1.5, 7), 1, 1, edgecolor='black', facecolor='none'))
        ax.add_patch(patches.Rectangle((1.5, 2), 1, 1, edgecolor='black', facecolor='none'))

        # Draw cards
        for position in card_positions:
            index, label = position
            x, y = self.board_positions[index]
            ax.add_patch(patches.Rectangle((x, y), 1, 1, edgecolor='black', facecolor='red'))
            ax.text(x + 0.5, y + 0.5, label, horizontalalignment='center', verticalalignment='center')

        plt.show()


if __name__ == "__main__":

    cards = [(0, 'Apple'), (7, 'Orange')]

    app = Game()
    app.plot_board(card_positions=cards)