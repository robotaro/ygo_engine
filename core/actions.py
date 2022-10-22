



class Action:

    _TYPE: None

    def __init__(self):
        pass


class ActionMoveCard(Action):

    _TYPE = "action_move_card"

    def __init__(self, card_index: int, from_zone: int, to_zone: int):
        super().__init__()
        self.card_index = card_index
        self.from_zone = from_zone
        self.to_zone = to_zone



