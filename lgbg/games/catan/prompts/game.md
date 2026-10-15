# CATAN — the shared game prompt

This file is handed to every player of every Catan game in LBGB. It says what the game is, how a
position is written down, and what each action means. It says **nothing about how to play well**:
no openings, no priorities, no evaluation of moves. What is legal is documented here; what is good
is the thing being measured.

## 1. The board

A standard island: 19 hexes, 54 intersections and 72 edges. Every one of them has an integer
identifier, and every identifier is written with its kind: `h` for a hex, `v` for an intersection,
`e` for an edge. `h9` is a hex; `v14` is an intersection; `e17` is an edge between two intersections.

Each hex has a terrain and, unless it is the desert, a number token from 2 to 12 (never 7):

| Terrain | Produces | Terrain | Produces |
|---|---|---|---|
| forest | wood | hills | brick |
| pasture | wool | field | wheat |
| mountains | ore | desert | nothing |

An edge carries a road or is empty; an intersection carries a settlement or a city, or is empty.
The five resources are always listed in this order: **brick, wood, wool, wheat, ore**.

Nine edges carry harbours. A harbour is written as its edge and its rate: `e6 wood 2:1` means the
edge e6 carries the wood harbour, which trades two wood for one card of another resource. `e0 3:1`
is a generic harbour, three of any one resource for one other. A player controls the harbours their
own settlements and cities border, and nobody else's.

The robber starts on the desert and blocks whatever hex it stands on: the hex produces nothing
while it is there.

## 2. The observation

Each turn you are shown a position. The fields are:

| Field | Meaning |
|---|---|
| `turn` | whose turn it is: the seat index |
| `phase` | what the game is waiting for (see below) |
| `round` | how many times play has come back round to seat 0 |
| `board` | every hex with its terrain and token, and every harbour with its edge, rate and resource |
| `robber` | the hex the robber occupies |
| `pieces` | every settlement, city and road on the board, as `[site, seat]` |
| `bank` | what is left in the shared supply, per resource |
| `hand_counts` | how many cards each seat holds, in seat order |
| `supply` | how many roads, settlements and cities each seat has left to build with |
| `awards` | which seat holds Longest Road and Largest Army, or `-1` for nobody |
| `dice` | the two dice of this turn's roll, or `null` before the roll |
| `offer` | the trade offer standing on the table, or `null` |
| `hand` | **your own** cards, per resource, exact |
| `points` | every seat's score as far as it can be computed: yours exactly, everybody else's without their hidden victory-point cards |

What is public: the board, every piece, every hand *count*, the bank, the awards, the dice and any
trade offer that has been announced. What is private: the contents of every other hand, the order
of the undealt development deck, and any victory-point card another player holds. A hand is held
face up in count and face down in kind.

## 3. The turn

A turn has two phases. In **`turn_production`** you roll the dice, or play a development card
first; nothing else may happen before the roll. The roll gives every hex whose token matches the
total one card per adjacent building: one for a settlement, two for a city. If the total is seven,
no hex produces, every player holding more than seven cards returns half of them (rounded down),
and then you move the robber and may take one card from a player who has a building on the hex it
now occupies.

In **`action`** you build, trade, buy and play development cards in any order, as often as you
like, until you end the turn. The phases you will see are:

| Phase | Who is asked | What ends it |
|---|---|---|
| `setup_round_1` | seats in seat order | every seat has placed one settlement and the road attached to it |
| `setup_round_2` | seats in reverse order | the same, and each seat takes one card for each hex its second settlement borders |
| `turn_production` | the current seat | a roll, or a development card and then a roll |
| `discard` | everybody over the limit, at once | every one of them has returned their cards |
| `robber` | the current seat | the robber has moved and the steal is resolved or skipped |
| `action` | the current seat | the turn ends |
| `road_building` | the current seat | the two free roads are placed, or cannot be |
| `trade_response` | every other seat holding a card, at once | all have answered, the offer is withdrawn, or the offerer picks among acceptors |
| `terminal` | nobody | somebody reached ten points |

## 4. The actions

Every action is a JSON object with a `type` and its parameters. What each type means and what it
needs:

| Action | Parameters | Meaning |
|---|---|---|
| `place_settlement` | `vertex` | the opening draft: an empty intersection, clear of every building |
| `place_road` | `edge` | the opening draft: an empty edge at the settlement just placed |
| `roll_dice` | none | roll the two dice |
| `discard_resources` | one count per resource, summing to half your hand rounded down | the seven's forfeit |
| `move_robber` | `hex` | send the robber to any hex but the one it is on |
| `choose_robber_victim` | `victim` | which of the players at the robber's hex is robbed |
| `build_road` | `edge` | brick 1, wood 1: an empty edge attached to your own network |
| `build_settlement` | `vertex` | brick 1, wood 1, wool 1, wheat 1: an empty intersection attached to your network and at least two edges from every building |
| `build_city` | `vertex` | ore 3, wheat 2: one of your own settlements becomes a city |
| `buy_dev_card` | none | ore 1, wool 1, wheat 1: the top card of the deck |
| `play_dev_card` | `card`, and for two of them `resources` | see section 5 |
| `place_free_road` | `edge` | a road the Road Building card owes, costing nothing |
| `maritime_trade` | `give_resource`, `give_count`, `want_resource` | exchange with the bank at your best rate |
| `offer_trade` | `give`, `want`, each a map of resource to count | propose a trade to the table |
| `respond_trade` | `response`, either `accept` or `decline` | answer an offer that was made to you |
| `choose_partner` | `partner` | which of the players who accepted an offer you trade with |
| `cancel_trade` | none | withdraw your offer |
| `end_turn` | none | the turn is over |

## 5. The development cards

A card bought this turn may not be played this turn, and at most one card may be played in a turn.
A card may be played in `turn_production` before the roll, or in `action` after it.

| Card | What it does | What it is told |
|---|---|---|
| knight | move the robber and steal, exactly as a seven does | nothing |
| road_building | two roads, free, placed one at a time | nothing |
| year_of_plenty | take two cards from the bank, the same or different | the two resources |
| monopoly | every other player hands you every card they hold of one resource | that resource |
| victory_point | one point, revealed rather than played | nothing |

Three knights make you the holder of Largest Army. The longest continuous road of at least five
edges makes you the holder of Longest Road. Each award is worth two points, and each is held by
exactly one player at a time: a tie takes it from the holder and leaves it with nobody.

## 6. Worked examples

**Placing a settlement.** The observation shows `v14` empty, with the hexes `h3 forest t2`,
`h7 pasture t6` and `h8 field t4` around it, and no building on `v14` or on any intersection one
edge away. The action is:

```json
{"type": "place_settlement", "vertex": 14}
```

**Building a road.** You hold brick 2 and wood 1, and `e17` is empty and touches `v14`, where you
have a settlement. You need one more wood. With brick 1 and wood 2:

```json
{"type": "build_road", "edge": 17}
```

**Trading with a harbour.** You have a settlement on a vertex of `e6`, the wood harbour, so you
trade wood at 2:1. Two wood become one ore, and the bank must hold ore:

```json
{"type": "maritime_trade", "give_resource": "wood", "give_count": 2, "want_resource": "ore"}
```

**Offering a trade to the table.** You hold two wood and want one ore. The offer is announced to
every other player holding a card, and each answers it once:

```json
{"type": "offer_trade", "give": {"wood": 2}, "want": {"ore": 1}}
{"type": "respond_trade", "response": "accept"}
{"type": "choose_partner", "partner": 2}
```

**Playing a Year of Plenty.** You hold the card and the bank holds at least two ore. The action
names the card and the two cards it takes - here two ore, the same resource twice:

```json
{"type": "play_dev_card", "card": "year_of_plenty", "resources": ["ore", "ore"]}
```

**A refusal.** An action that cannot be taken is refused with a code and a sentence, and the
position does not change. Refusals are part of the game, not errors in the protocol: `VERTEX_OCCUPIED`
means the intersection already carries a building, `TOO_CLOSE` means a neighbouring one does,
`NOT_ENOUGH_RESOURCES` means the cards are not in your hand, `WRONG_PHASE` means the action does
not belong to the phase the game is in.

## 7. How to answer

You will be asked for one action at a time. Reply with a single JSON object of the shape above,
naming only the parameters that action declares. When a decision is addressed to a particular
player, the request carries its identifier and the acting seat; the same action is refused if it
arrives from a seat that is not the one being asked.

What is legal is what this file describes and what the position allows. Nothing in this file says
which legal action is better.



