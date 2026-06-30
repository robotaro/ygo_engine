"""Random self-play fuzzer for the engine.

Runs N seeded ``RandomAgent``-vs-``RandomAgent`` games on a deck stuffed with the cards
whose effects the campaign has authored — heavy on the interacting mechanisms (Special
Summon / negation / attack-reaction / stat-anthem cards) so random play collides them —
and asserts only that no game raises. It complements the deterministic unit tests in
``tests/``: long, randomised game states catch crashes the per-card tests don't (it first
surfaced a latent Token-tribute ``KeyError`` that only a Token tributed mid-game hits).

  uv run python scripts/fuzz_selfplay.py            # default game count
  uv run python scripts/fuzz_selfplay.py 200        # 200 games

Importable, too: ``tests/test_fuzz_smoke.py`` runs a small slice of these games on every
pytest run via ``play_game`` / ``play_games`` below.
"""

from __future__ import annotations

import sys
import traceback

from ygo.agents import RandomAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Zone
from ygo.state import GameState

_REGISTRY = CardRegistry.load_csv()

# A duel deck spanning the authored-effects campaign — both players run it, so the
# mechanisms (locks, class/monster negation, the attack-reaction Traps, the stat anthems)
# routinely meet on the same board. Grouped by the batch that added the cards.
DECK = (
    ["Decoyroid"] * 3
    + ["Marauding Captain"] * 3
    + ["Queen's Bodyguard"] * 2
    + ["Allure Queen LV3"] * 2
    + ["Marshmallon"] * 2
    + ["Marshmallon Glasses"] * 2
    + ["Celtic Guardian"] * 3
    + ["Summoned Skull"] * 3
    + ["Mystical Elf"] * 3
    + ["La Jinn the Mystical Genie of the Lamp"] * 3
    + ["Gemini Elf"] * 3
    + ["Hayabusa Knight"] * 2
    + ["Mad Sword Beast"] * 2
    + ["Smashing Ground"] * 2
    + ["Fissure"] * 2
    + ["Pot of Greed"] * 2
    # Special Summon locks + the SS routes they gate
    + ["Vanity's Fiend"] * 2
    + ["Vanity's Ruler"] * 2
    + ["Barrier Statue of the Inferno"] * 2
    + ["Barrier Statue of the Torrent"] * 2
    + ["Mystic Tomato"] * 2
    + ["UFO Turtle"] * 2
    + ["Mother Grizzly"] * 2
    + ["Monster Reborn"] * 2
    + ["Scapegoat"] * 2
    + ["Cyber Dragon"] * 2
    # response cards that fire on effect-driven Special Summons (window stress)
    + ["Bottomless Trap Hole"] * 2
    + ["Black Horn of Heaven"] * 2
    + ["Torrential Tribute"] * 2
    # class negators + the Spell/Trap/Field they negate
    + ["Jinzo"] * 2
    + ["Spell Canceller"] * 2
    + ["Royal Decree"] * 2
    + ["Imperial Order"] * 2
    + ["Just Desserts"] * 2
    + ["Ookazi"] * 2
    + ["Sogen"] * 2
    + ["Trap Hole"] * 2
    # Skill Drain + monsters whose effects/riders it negates
    + ["Skill Drain"] * 2
    + ["Chaos Necromancer"] * 2
    + ["Airknight Parshath"] * 2
    + ["Gravekeeper's Curse"] * 2
    + ["Man-Eater Bug"] * 2
    # "destroy all Special Summoned monsters" floodgates + was-SS flag
    + ["Fossil Dyna Pachycephalo"] * 2
    + ["Jowgen the Spiritualist"] * 2
    + ["Special Hurricane"] * 2
    + ["Dandylion"] * 2
    # reactive attack-declaration Traps
    + ["Sakuretsu Armor"] * 2
    + ["Negate Attack"] * 2
    + ["Malevolent Catastrophe"] * 2
    + ["Widespread Ruin"] * 2
    + ["Radiant Mirror Force"] * 2
    + ["Dark Mirror Force"] * 2
    # battle-position change
    + ["Block Attack"] * 2
    + ["Book of Moon"] * 2
    + ["Earthquake"] * 2
    + ["No Entry!!"] * 2
    + ["Zero Gravity"] * 2
    + ["Windstorm of Etaqua"] * 2
    + ["Kunai with Chain"] * 2
    + ["Big Shield Gardna"] * 2
    # coin-flip
    + ["Jirai Gumo"] * 2
    + ["Abare Ushioni"] * 2
    + ["Cup of Ace"] * 2
    + ["Barrel Dragon"] * 2
    + ["Blowback Dragon"] * 2
    # attack redirect + cost-bearing attack Trap
    + ["Call of the Earthbound"] * 2
    + ["Jam Defender"] * 2
    + ["Revival Jam"] * 2
    + ["Chaos Burst"] * 2
    # take-control-the-attack + battle-damage reflection
    + ["Magical Arm Shield"] * 2
    + ["Dimension Wall"] * 2
    # "selected as attack target" gate + board-state attack Traps
    + ["Mirage Tube"] * 2
    + ["Froggy Forcefield"] * 2
    + ["Des Frog"] * 2
    + ["Justi-Break"] * 2
    + ["Supercharge"] * 2
    + ["Cycroid"] * 2
    + ["Amazoness Archers"] * 2
    + ["Amazoness Swords Woman"] * 2
    # forced attack target
    + ["Staunch Defender"] * 2
    # Special Summon from hand on an attack
    + ["A Hero Emerges"] * 2
    + ["Relieve Monster"] * 2
    # was-Tribute-Summoned gate
    + ["Blast Held by a Tribute"] * 2
    # monster on-attack-declare (Necrovalley-gated)
    + ["Gravekeeper's Assailant"] * 2
    + ["Necrovalley"] * 2
    # continuous ATK scaling by your own monsters
    + ["Amazoness Paladin"] * 2
    + ["Amazoness Tiger"] * 2
    + ["Botanical Lion"] * 2
    + ["Lava Battleguard"] * 2
    + ["Swamp Battleguard"] * 2
    # monster-borne attribute anthems
    + ["Bladefly"] * 2
    + ["Milus Radiant"] * 2
    + ["Star Boy"] * 2
    + ["Witch's Apprentice"] * 2
    + ["Luster Dragon"] * 2
    # conditional flat self-ATK
    + ["Boot-Up Soldier - Dread Dynamo"] * 2
    + ["Green Gadget"] * 2
    + ["Cybernetic Cyclopean"] * 2
    + ["Theban Nightmare"] * 2
    # Damage-Step combat pumps
    + ["Cipher Soldier"] * 2
    + ["Etoile Cyber"] * 2
    + ["Insect Soldiers of the Sky"] * 2
    + ["Penumbral Soldier Lady"] * 2
    + ["Steamroid"] * 2
    + ["Black Veloci"] * 2
    # archetype/race anthems + self-shield lords
    + ["Command Knight"] * 2
    + ["Freya, Spirit of Victory"] * 2
    + ["Shining Angel"] * 2
    + ["Hunter Owl"] * 2
    + ["Nightmare Penguin"] * 2
    + ["Mother Grizzly"] * 2
    # more attribute anthems + a position-gated anthem
    + ["Harpie Lady 1"] * 2
    + ["Hoshiningen"] * 2
    + ["Little Chimera"] * 2
    + ["Fairy King Truesdale"] * 2
    # clean Flip effects (position / GY-recover / take-control)
    + ["Bite Shoes"] * 2
    + ["Gravitic Orb"] * 2
    + ["DUCKER Mobile Cannon"] * 2
    + ["Mask of Darkness"] * 2
    + ["Rafflesia Seduction"] * 2
    + ["Jowls of Dark Demise"] * 2
    + ["Dragon Manipulator"] * 2
    # clean Flip effects (GY summon / GY->Deck / LP / count-burn)
    + ["Spirit Caller"] * 2
    + ["Des Feral Imp"] * 2
    + ["Princess of Tsurugi"] * 2
    + ["The Immortal of Thunder"] * 2
    # turn-scoped lockout flips
    + ["Guard Dog"] * 2
    + ["Sonic Jammer"] * 2
    + ["Whirlwind Weasel"] * 2
    + ["Searchlightman"] * 2
    # continuous activation locks
    + ["Mirage Dragon"] * 2
    + ["Pitch-Black Warwolf"] * 2
    + ["Invader of Darkness"] * 2
    + ["Mechanical Hound"] * 2
    # Standby-Phase effects (StandbyTrigger)
    + ["Bowganian"] * 2
    + ["Ebon Magician Curran"] * 2
    + ["Dancing Fairy"] * 2
    + ["Spirit of the Breeze"] * 2
    + ["Destiny HERO - Defender"] * 2
    + ["Minor Goblin Official"] * 2
    # "destroys a monster by battle" SELF triggers
    + ["Masked Chopper"] * 2
    + ["Guardian Angel Joan"] * 2
    + ["Hydrogeddon"] * 2
    + ["Divine Knight Ishzark"] * 2
    + ["Blue Thunder T-45"] * 2
    # during-End-Phase triggers (EndPhaseTrigger)
    + ["Elemental HERO Lady Heat"] * 2
    + ["Little-Winguard"] * 2
    + ["Garuda the Wind Spirit"] * 2
    + ["Lumina, Lightsworn Summoner"] * 2
    + ["The Wicked Worm Beast"] * 2
    # attack-lock floodgates (AttackRestriction extension)
    + ["Swords of Revealing Light"] * 2
    + ["Gravity Bind"] * 2
    # "switch to Defense after attacking" family (DefenseAfterAttack)
    + ["Spear Dragon"] * 2
    + ["Goblin Attack Force"] * 2
    + ["Goblin Elite Attack Force"] * 2
    + ["Axe Dragonute"] * 2
    + ["Goblin Black Ops"] * 2
    # deck-impact staples
    + ["Ring of Destruction"] * 2
    + ["Card Destruction"] * 2
    + ["Dust Tornado"] * 2
    # permanent ATK debuff + Megamorph + Nimble (deck-impact)
    + ["Slate Warrior"] * 2
    + ["Zombyra the Dark"] * 2
    + ["Megamorph"] * 2
    + ["Nimble Momonga"] * 3
    # deck-impact win conditions + toolbox flips
    + ["Cyber Jar"] * 2
    + ["Time Wizard"] * 2
    + ["Maha Vailo"] * 2
    + ["Exodia the Forbidden One"]
    + ["Right Arm of the Forbidden One"]
    + ["Left Arm of the Forbidden One"]
    + ["Right Leg of the Forbidden One"]
    + ["Left Leg of the Forbidden One"]
    # battle-banish trigger + GY-Standby self-return + conditional named SS
    + ["D.D. Warrior Lady"] * 2
    + ["Sinister Serpent"] * 2
    + ["Elegant Egotist"] * 2
    + ["Harpie Lady"] * 2
    + ["Harpie Lady Sisters"] * 2
    # Extra-Deck cheat + board-reset flood + Machine ATK-doubler
    + ["Cyber-Stein"] * 2
    + ["Morphing Jar #2"] * 2
    + ["Limiter Removal"] * 2
    # both-GY stat anthem + battle-recruiter + Battle-Phase-ender
    + ["Dark Magician Girl"] * 2
    + ["Dark Magician"] * 2
    + ["Giant Germ"] * 3
    + ["The Unhappy Maiden"] * 2
    # coin attacker-zero Trap + GY-Standby LP drip + End-Phase summon floodgate
    + ["Fairy Box"] * 2
    + ["Darklord Marie"] * 2
    + ["Infinite Dismissal"] * 2
    # pay-LP-to-attack + face-down banisher + Nomi banish-SS with a phase-gated debuff
    + ["Dark Elf"] * 2
    + ["Nobleman of Crossout"] * 2
    + ["Soul of Purity and Light"] * 2
    + ["Mystical Elf"] * 2  # LIGHT fodder for Soul of Purity + a Set target for Nobleman
    # "when you take battle damage" reactive Traps
    + ["Numinous Healer"] * 2
    + ["Attack and Receive"] * 2
    + ["Damage Condenser"] * 2
    # deck-completion: a Ritual, a Nomi Winged Beast, and a piercing Equip
    + ["Black Magic Ritual"] * 2
    + ["Magician of Black Chaos"] * 2
    + ["Harpie Lady Sisters"] * 1
    + ["Elegant Egotist"] * 2
    + ["Harpie Lady"] * 2  # the Egotist condition + a Big Bang Shot host
    + ["Big Bang Shot"] * 2
    # Batch 82: Blast Sphere (attacked -> equip to attacker -> delayed Standby kill)
    + ["Blast Sphere"] * 2
    # Batch 83: the "when destroyed" bucket -- Babycerasaurus (destroyed by effect ->
    # recruit a Dinosaur) plus a Dinosaur for it to fetch, and Granadora (unified
    # destroyed -> self-burn 2000). Sabersaurus is the recruit target.
    + ["Babycerasaurus"] * 2
    + ["Granadora"] * 2
    + ["Sabersaurus"] * 2
    # Batch 84: Fire Princess ("each time you gain LP, burn 500") + its LP-gain partners
    # (Solemn Wishes gains on draw, Cure Mermaid each Standby) so the life-gain window is
    # exercised end-to-end.
    + ["Fire Princess"] * 2
    + ["Solemn Wishes"] * 1
    + ["Cure Mermaid"] * 1
    # Batch 85: battle-damage prevention — Kuriboh (hand discard in the damage-step window
    # -> 0 damage from that battle) and Winged Kuriboh (destroyed -> no battle damage the
    # rest of the turn).
    + ["Kuriboh"] * 2
    + ["Winged Kuriboh"] * 2
    # Batch 86: Nutrient Z (Set Trap — gain 4000 before taking 2000+ battle damage), which
    # exercises the battle-damage preview run at every attack.
    + ["Nutrient Z"] * 2
    # Batch 87: draw-again engines — Heart of the Underdog (draw a Normal Monster -> draw
    # again) and Tethys (draw a Fairy -> draw again), plus a Fairy to feed Tethys. Celtic
    # Guardian / Mystical Elf already in the deck are the Normal-Monster fuel for Heart.
    + ["Heart of the Underdog"] * 1
    + ["Tethys, Goddess of Light"] * 1
    + ["Dunames Dark Witch"] * 2
    # Batch 88: Parasite Paracide — FLIP buries it in the opponent's deck; when they draw
    # it, it Special Summons onto their field and burns them 1000 (exercises the plant +
    # ownership transfer + the timing="drawn" ambush across many self-play draws).
    + ["Parasite Paracide"] * 2
    # Batch 89: the Exodia package. The five pieces exercise the kernel win check; Big Eye
    # (Flip deck-reorder), Backup Soldier (GY recover, gated on 5+ GY monsters), and Buster
    # Blader (scales off the opponent's Dragons — fed by Blue-Eyes already in the deck).
    + ["Exodia the Forbidden One", "Right Arm of the Forbidden One",
       "Left Arm of the Forbidden One", "Right Leg of the Forbidden One",
       "Left Leg of the Forbidden One"]
    + ["Big Eye"] * 1 + ["Backup Soldier"] * 1 + ["Buster Blader"] * 1
    + ["Koumori Dragon"] * 2  # a vanilla Dragon so Buster Blader's scaling actually fires
    # Batch 90: Solemn Judgment (negate a Summon OR a S/T activation, pay half LP) and
    # Tribe-Infecting Virus (discard 1, declare a Type, wipe it from the field).
    + ["Solemn Judgment"] * 2 + ["Tribe-Infecting Virus"] * 2
    # Batch 91: Magical Mallet (hand refresh), Metalmorph (equip Trap: +300 + half target's
    # ATK on attack), Wall of Illusion (bounce the attacker), Panther Warrior (Tribute to
    # attack — exercises the attack-tribute cost across many Battle Phases).
    + ["Magical Mallet"] * 1 + ["Metalmorph"] * 2
    + ["Wall of Illusion"] * 2 + ["Panther Warrior"] * 2
    # Batch 92: the Toon monsters + their Toon World enabler. Exercises the SS-by-tribute
    # hand summon, the 500-LP attack cost, the Toon-World-gone cleanup, and the Toon Gemini
    # Elf battle-damage discard.
    + ["Toon World"] * 2 + ["Blue-Eyes Toon Dragon"] * 1
    + ["Toon Summoned Skull"] * 1 + ["Toon Gemini Elf"] * 2
    # Batch 93: Relinquished + its Ritual Spell (exercises the Ritual summon and the absorb
    # equip/stat-copy). Thousand-Eyes Restrict is a Fusion (extra deck) — covered by unit
    # tests, not the main-deck fuzz.
    + ["Relinquished"] * 1 + ["Black Illusion Ritual"] * 1
    # Batch 94: the Water/Umi cluster. A Legendary Ocean (treated as Umi, WATER +200/+200),
    # Tornado Wall (no battle damage while Umi), The Legendary Fisherman (untargetable while
    # Umi) + a couple of WATER bodies to exercise the boost and the Umi-gated riders.
    + ["A Legendary Ocean"] * 2 + ["Tornado Wall"] * 1
    + ["The Legendary Fisherman"] * 1 + ["7 Colored Fish"] * 2
    # Batch 95: the GY/discard punishers. Banisher of the Light (every send-to-GY is
    # banished instead — exercises the floodgate redirect across the whole match);
    # Magical Thorn (burns the opponent on each hand discard).
    + ["Banisher of the Light"] * 1 + ["Magical Thorn"] * 1
    # Batch 96: the Weevil insect-trap pair. Acid Trap Hole (flip a face-down DEF monster,
    # destroy if DEF <= 2000); Drill Bug (on battle damage, set Parasite Paracide on top
    # of the deck — pairs with the Parasite already in the fuzz pool).
    + ["Acid Trap Hole"] * 1 + ["Drill Bug"] * 1
    # Batch 97: a summon/attack/flip trio. Eatgaboon (destroy an opponent's <=500-ATK
    # Summon — Petit Moth gives it a target); The Stern Mystic (no-op reveal Flip);
    # Gravekeeper's Servant (mill-tax on the opponent's every attack declaration).
    + ["Eatgaboon"] * 1 + ["Petit Moth"] * 1 + ["The Stern Mystic"] * 1
    + ["Gravekeeper's Servant"] * 1
    # Batch 98: Susa Soldier (cannot be SS; End-Phase self-bounce; halved battle damage).
    + ["Susa Soldier"] * 2
    # Batch 99: a Ritual pair + their boss. The Ritual Spells + their monsters + Level-8
    # Tribute fodder (Blue-Eyes) so the Ritual Summons can actually fire; Shinato's
    # Defense-Position battle burn exercises the new died_in_defense flag.
    + ["Curse of the Masked Beast"] * 1 + ["The Masked Beast"] * 1
    + ["Shinato's Ark"] * 1 + ["Shinato, King of a Higher Plane"] * 1
    + ["Blue-Eyes White Dragon"] * 1
    # Batch 100: position & flip control. Dream Clown (switch to Defense -> destroy a
    # monster; exercises the new changed_to_defense trigger) and Invader of the Throne
    # (FLIP control swap; exercises state.swap_control + the flip-condition gate).
    + ["Dream Clown"] * 1 + ["Invader of the Throne"] * 1
    # Batch 101: Insect Queen (Insect anthem via race_on_field, attack-Tribute cost, and
    # the End-Phase Insect Token recursion on a battle kill). Insect bodies already in pool.
    + ["Insect Queen"] * 1
)


def build_state(seed: int) -> GameState:
    """A fresh duel: both players shuffle ``DECK`` (seeded) and draw 5."""
    state = GameState.new(("A", "B"), seed=seed)
    for owner in (0, 1):
        for name in DECK:
            inst = state.create_instance(_REGISTRY.get(name), owner=owner, zone=Zone.DECK)
            state.players[owner].deck.append(inst.iid)
        state.shuffle_deck(owner)
        state.draw(owner, 5)
    return state


def play_game(seed: int, max_turns: int = 120) -> None:
    """Play one seeded RandomAgent-vs-RandomAgent game to completion. Raises if the
    engine raises — that's the property the fuzzer (and the smoke test) checks."""
    state = build_state(seed)
    agents = [RandomAgent(seed=seed), RandomAgent(seed=seed + 1000)]
    Engine(state, agents, max_turns=max_turns).run()


def play_games(n: int, *, start: int = 0, verbose: bool = False) -> int:
    """Play games with seeds ``[start, start + n)``; return the number that crashed
    (printing each traceback when ``verbose``)."""
    fails = 0
    for seed in range(start, start + n):
        try:
            play_game(seed)
        except Exception:
            fails += 1
            if verbose:
                print(f"--- game seed={seed} CRASHED ---")
                traceback.print_exc()
    return fails


def main(argv: list[str]) -> int:
    n = int(argv[1]) if len(argv) > 1 else 80
    fails = play_games(n, verbose=True)
    print(f"\n{n - fails}/{n} games clean" if not fails else f"\n{fails}/{n} games CRASHED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
