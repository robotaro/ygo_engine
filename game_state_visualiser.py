import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

# Useful Matplolib links
# https://matplotlib.org/stable/tutorials/text/text_props.html#sphx-glr-tutorials-text-text-props-py
# https://matplotlib.org/stable/gallery/text_labels_and_annotations/demo_text_rotation_mode.html#sphx-glr-gallery-text-labels-and-annotations-demo-text-rotation-mode-py

# ==============================================
#              Field Constants
# ==============================================

CARD_WIDTH = 5.9  # cm
CARD_HEIGHT = 8.6  # cm

MAIN_CARD_SLOTS = 5
MAIN_CARD_SLOT_WIDTH = CARD_WIDTH
MAIN_CARD_SLOT_HEIGHT = CARD_HEIGHT
CARD_SLOT_MARGIN = 1.35
BOARD_SCALE = 0.015

# Player Display
DISPLAY_WIDTH = 0.3
DISPLAY_HEIGHT = 0.085

DEFAULT_LIFE_POINTS = 8000

class GameStateVisualiser:

    def __init__(self):

        pass

    def add_card_slot(self, figure_axes: plt.Axes,
                      center_x: float,
                      center_y: float,
                      width: float,
                      height: float,
                      color='b'):

        half_width = width * 0.5
        half_height = height * 0.5

        x = center_x - half_width
        y = center_y - half_height

        figure_axes.add_patch(
                patches.Rectangle(
                (x, y),
                width,
                height,
                fill=False,
                transform=figure_axes.transAxes,
                clip_on=False
            )
        )

    def add_player_display_to_axes(self,
                                   figure_axes: plt.Axes,
                                   center_x: float,
                                   center_y: float,
                                   selected_stage=None,
                                   life_points=8000,
                                   rotated=False):

        offset_x = -DISPLAY_WIDTH * 0.5
        offset_y = -DISPLAY_HEIGHT * 0.5

        # Text alignement offsets
        top_line_y = DISPLAY_HEIGHT * 0.75
        bottom_line_y = DISPLAY_HEIGHT * 0.25
        if rotated:
            top_line_y, bottom_line_y = bottom_line_y, top_line_y


        display_x = center_x + offset_x
        display_y = center_y + offset_y

        # Internal display components
        lp_label_x = DISPLAY_WIDTH * 0.1
        lp_value_x = DISPLAY_WIDTH * 0.5

        # Add Display border
        figure_axes.add_patch(
            patches.Rectangle(
                (display_x, display_y),
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT,
                fill=False,
                transform=figure_axes.transAxes,
                clip_on=False
            )
        )

        # Add Life Points Label text
        figure_axes.text(
            display_x + lp_label_x,
            display_y + top_line_y,
            'LP',
            fontsize=20,
            color='black',
            horizontalalignment='center',
            verticalalignment='center',
            transform=figure_axes.transAxes)

        # Add Life Points Value text
        figure_axes.text(
            display_x + lp_value_x,
            display_y + top_line_y,
            str(life_points),
            fontsize=20,
            color='black',
            horizontalalignment='right',
            verticalalignment='center',
            transform=figure_axes.transAxes)
 
    def add_player_field_to_axes(self, figure_axes: plt.Axes, center_x: float, center_y: float, rotated=False) -> dict:

        """
        Draw a card square
        :param figure_axes:
        :param center_x: Center for board
        :param center_y:
        :return:
        """
        half_margin = CARD_SLOT_MARGIN * 0.5
        slot_size_x = (MAIN_CARD_SLOT_WIDTH + half_margin) * BOARD_SCALE
        slot_size_y = (MAIN_CARD_SLOT_HEIGHT + half_margin) * BOARD_SCALE

        board_offset_x = -slot_size_x * (MAIN_CARD_SLOTS + 1) * 0.5
        board_offset_y = -slot_size_y * 0.5

        temp_card_slot_locations = np.ndarray((2, MAIN_CARD_SLOTS + 2, 2), dtype=np.float32)

        # Draw rows
        for index_y in range(2):
            for index_x in range(MAIN_CARD_SLOTS + 2):

                # Calculate the location for the current card slot and store it
                x = (index_x * slot_size_x) + board_offset_x + center_x
                y = (index_y * slot_size_y) + board_offset_y + center_y
                temp_card_slot_locations[index_y, index_x, :] = (x, y)

                # Add slot to board
                self.add_card_slot(
                    figure_axes=figure_axes,
                    center_x=x,
                    center_y=y,
                    width=MAIN_CARD_SLOT_WIDTH * BOARD_SCALE,
                    height=MAIN_CARD_SLOT_HEIGHT * BOARD_SCALE
                )

        if rotated:
            # Rotate the board by 180 degrees - to be used by the other player
            temp_card_slot_locations = np.flipud(np.fliplr(temp_card_slot_locations))

        # Store final card slot locations into final dictionary
        board = {
            'monster_zone': [tuple(location) for location in temp_card_slot_locations[0, 1:-1, :].tolist()],
            'spell_trap_zone': [tuple(location) for location in temp_card_slot_locations[1, 1:-1, :].tolist()],
            'graveyard': tuple(temp_card_slot_locations[0, -1, :].tolist()),
            'deck_zone': tuple(temp_card_slot_locations[1, -1, :].tolist()),
            'field_card_zone': tuple(temp_card_slot_locations[0, 0, :].tolist()),
            'fusion_deck_zone': tuple(temp_card_slot_locations[0, 0, :].tolist())
        }

        return board

    def show_game_state(self):

        fig = plt.figure(figsize=(8, 8))
        figure_axes = fig.add_axes([0, 0, 1, 1])
        player_1_card_locations = self.add_player_field_to_axes(figure_axes=figure_axes,
                                                                center_x=0.5,
                                                                center_y=0.25)
        player_2_card_locations = self.add_player_field_to_axes(figure_axes=figure_axes,
                                                                center_x=0.5,
                                                                center_y=0.75,
                                                                rotated=True)
        self.add_player_display_to_axes(figure_axes=figure_axes,
                                        center_x=0.25,
                                        center_y=0.45)
        self.add_player_display_to_axes(figure_axes=figure_axes,
                                        center_x=0.75,
                                        center_y=0.55,
                                        rotated=True)

        figure_axes.set_aspect('equal')
        figure_axes.set_axis_off()
        plt.show()

        pass


if __name__ == "__main__":

    viz = GameStateVisualiser()
    viz.show_game_state()