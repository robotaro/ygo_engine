import matplotlib.pyplot as plt
import matplotlib.patches as patches
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
MAIN_CARD_SLOT_WIDTH = CARD_HEIGHT
MAIN_CARD_SLOT_HEIGHT = CARD_HEIGHT
CARD_SLOT_MARGIN = 1.5
OFFSET_X = MAIN_CARD_SLOT_WIDTH + CARD_SLOT_MARGIN
OFFSET_Y = MAIN_CARD_SLOT_HEIGHT + CARD_SLOT_MARGIN

BOARD_SCALE = 0.02

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

    def add_game_field(self, figure_axes: plt.Axes):

        space_x = MAIN_CARD_SLOT_WIDTH + CARD_SLOT_MARGIN
        space_y = MAIN_CARD_SLOT_HEIGHT + CARD_SLOT_MARGIN

        field_offset_x = space_x * (1 + MAIN_CARD_SLOTS * 0.5)
        field_offset_y = 0

        # Draw rows
        for index_y in range(2):
            for index_x in range(MAIN_CARD_SLOTS):
                x = (index_x * space_x + OFFSET_X) * BOARD_SCALE
                y = (index_y * space_y + OFFSET_Y) * BOARD_SCALE
                print(x, y)
                self.add_card_slot(
                    figure_axes=figure_axes,
                    center_x=x,
                    center_y=y,
                    width=MAIN_CARD_SLOT_WIDTH * BOARD_SCALE,
                    height=MAIN_CARD_SLOT_HEIGHT * BOARD_SCALE
                )

        figure_axes.set_aspect('equal')


    def show_game_state(self):

        fig = plt.figure()
        figure_axes = fig.add_axes([0, 0, 1, 1])
        self.add_game_field(figure_axes=figure_axes)

        figure_axes.set_axis_off()
        plt.show()

        pass


if __name__ == "__main__":

    viz = GameStateVisualiser()
    viz.show_game_state()