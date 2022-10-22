
GAME_PHASES = ['draw_phase',
               'standby_phase',
               'main_phase_1',
               'battle_phase',
               'main_phase_2',
               'end_phase']

class ConditionalNode:

    def __init__(self):
        pass

    def add_condition(self):

        pass

class LogicEngine:

    def __init__(self):

        pass

    def demo(self, player_list: list, num_turns=10):

        for _ in range(num_turns):

            for player in player_list:
                print(f'[{player}]')
                for phase in GAME_PHASES:
                    print(f' > {phase}')



if __name__ == "__main__":

    app = LogicEngine()
    app.demo(player_list=['player_1', 'player_2'])





