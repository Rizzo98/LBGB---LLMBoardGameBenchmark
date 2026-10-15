# RULES.md — CATAN (base game, 4 players): pinned rule interpretations

| Field | Value |
|---|---|
| **Document** | `lgbg/games/catan/RULES.md` |
| **Game** | CATAN (originally *The Settlers of Catan*) — base game, 4 players |
| **Plugin** | `catan` |
| **Status** | **PINNED** — this file is the rule authority for the plugin (`ARCHITECTURE.md` §7.9, PRD-v1 §11, SC-12) |
| **Document revision** | 2 |
| **Plugin `rules_version`** | `catan-rules-3` |
| **Edition basis** | CATAN 6th edition rulebook (2025) as the primary text; the 5th-edition *Game Rules & Almanac* (2015) and the official CATAN GmbH base-game FAQ for rules the 6th edition leaves implicit |
| **Written** | before any rules code exists (milestone M0, card K-001) |
| **Owner** | Maintainer |
| **Supersedes** | — |

## 1. Header block and pinning policy

### 1.1 What this document is

This document records **exactly which interpretation of each Catan rule this project implements**, with a
citation to the rulebook for every rule, and with the alternative reading recorded wherever the rulebook
admits more than one. It exists so that **no rule is ever implemented from memory** (PRD-v1 §2, risk R1).

It is the scope fence for the Catan plugin (PRD-v1 R9). Anything not stated here is a new requirement, not
a clarification, and requires this document to change first.

This document contains **no strategy advice**. It states legality, not quality of play.

### 1.2 Pinning and versioning

* The plugin declares `rules_version = "catan-rules-3"` (shape from `ARCHITECTURE.md` §8.3). The value
  is pinned by this document. It was bumped from `catan-rules-1` to `catan-rules-2` when the engine's
  phase vocabulary was brought into line with the table in §4.4: the phase name is part of the encoded
  state and therefore of every hash, so records made under the old names are not comparable with
  records made under these. The rules themselves did not change; the engine was corrected to the rule
  this document already pinned, and the golden fixture was regenerated in the same change.
* It was bumped again, to `catan-rules-3`, when the engine's canonical resource order was brought into
  line with §3. The position of each resource inside a hand is written into every encoded state, so
  two orders give two different hashes for one position: the §3 order - brick, wood, wool, wheat, ore,
  the order in which the rulebook lists the five resource-card stacks - is the pinned one, and the
  engine had picked an order of its own. The rules did not change here either, and the golden fixture
  was regenerated in the same change.
* **Any change to a pinned rule in this document MUST bump `rules_version`** (for example to
  `catan-rules-2`) before the change is implemented. A pinned rule is any sentence in §4, §5, §6 or §7
  under the labels *Rule as implemented*, *Chosen interpretation*, *Confirmation* or *Pinned draw*.
* A `rules_version` bump **invalidates the golden record corpus by design** (`ARCHITECTURE.md`
  §7.9, §15.3; PRD-v1 R4). Goldens are regenerated in the same change.
* Editorial changes (typos, formatting, added cross-references, added citations that do not alter a pinned
  rule) do not bump `rules_version`; they bump **Document revision** above.
* Where this document resolves an ambiguity that the rulebook genuinely leaves open, it says so explicitly
  and marks the entry **NO PRIMARY SOURCE**. Those pins are project decisions, not rulebook facts, and must
  never be cited as rulebook facts by later cards.

### 1.3 Requirement levels

`MUST`, `MUST NOT`, `SHOULD` and `MAY` are used with their RFC 2119 meaning, as in
PRD-v1. Where this document pins a rule that contradicts a literal reading of a PRD-v1 requirement, the
divergence is called out in a **PRD divergence** note and is also listed in §6.2 and §7 (summary).

---

## 2. Sources

Only sources actually retrieved are cited. Keys `S1` … `S7` below. Every citation in this
document uses one of these keys.

| Key | Source | Publisher | Edition / date | Retrieved from |
|---|---|---|---|---|
| **S1** | *CATAN — The Game* rulebook, document CN3081, version `v6.250401` | CATAN Studio / CATAN GmbH | 6th edition, April 2025 | https://www.catan.com/sites/default/files/2025-03/CN3081%20CATAN%E2%80%93The%20Game%20Rulebook%20secure%20%281%29.pdf |
| **S2** | *CATAN — Game Rules & Almanac* (the "Catan 2015 Base Rules", 5th English edition; copyright line "© 1995, 1997, 1999, 2005, 2007, 2015 Catan GmbH and Mayfair Games, Inc.") | Mayfair Games / CATAN GmbH | 5th English edition, January 2015 | https://www.racingcow.io/pdf/games/catan_optimized.pdf |
| **S3** | *CATAN — Basic Rules* / "Klaus Teuber's CATAN — Game Rules & Almanac" (25th-anniversary printing of the classic rules) | CATAN GmbH | 2015 printing | http://www.catancollector.com/images/uploads/catan-25th-rules_eng-200313.pdf |
| **S4** | *CATAN World Championship Stuttgart 2025 — Tournament Rules* | CATAN GmbH | 2025 | https://www.catan.com/sites/default/files/2025-04/CATAN%20CWC%202025_Tournament%20Rules.pdf |
| **S5** | *CATAN Basegame FAQ* | CATAN GmbH (official site) | retrieved 2026; entries undated | https://www.catan.com/faq/basegame |
| **S6** | *CATAN — Das Spiel* manual, CATAN Big Box (German; the same game, with the component and cost values spelled out in running text) | KOSMOS / CATAN GmbH | Big Box manual, 29.04.2025 | https://cms.kosmos.de/game-instructions/4002051685225_CATAN_BigBox_Manual_250429_web.pdf |
| **S7** | *CATAN 5–6 Player Extension* rules | CATAN Studio / Mayfair | 2020 printing | http://www.catancollector.com/images/uploads/catan_5-6_2020_rules_200707.pdf |

**S2, S3 and S7 are official published rulebooks hosted on third-party archives.** They are cited for
wording that the 6th edition compresses or omits. **S6** is an official KOSMOS/CATAN GmbH manual for the
same game, cited where the English rulebooks express a value only as artwork on the Building Costs card.

Two retrieved documents were **not** used: *Catan Card Game* rules (a different game) and the *Catan
Geographies* rules (a different product).

### 2.1 Source precedence

Where S1 and S2/S3 disagree, **S1 (6th edition) wins**, because S4 §1.0 says "Games follow current CATAN
English 6th Edition rules" and S1 is that edition. Where S1 is silent and S2/S3 are explicit, the older
Almanac is used and the fact is flagged *S1 silent*. Where S4 §3.0 states a clarification, **S4 wins over
the standard rules** — S4 says so in terms: "In the event of any disagreement between the standard rules and
these clarifications, the clarification is considered to be the official rule." S5 is used only for points
no rulebook addresses.

### 2.2 Naming differences between editions

The 6th edition renamed several things. The **code identifiers follow the PRD** (left column); the
**rulebook names are quoted verbatim in citations**.

| This project (code identifiers, PRD-v1) | 6th edition (S1) | 5th edition (S2/S3) |
|---|---|---|
| `longest_road` / "Longest Road" | **Longest Route** | Longest Road |
| `year_of_plenty` | **Invention** | Year of Plenty |
| `victory_point` | Victory Point | Victory Point |
| `knight` | Knight | Knight (earliest editions: Soldier) |
| `wool` | wool | wool |
| `wood` | wood | lumber |
| `wheat` | wheat | grain |
| bank / supply | "the supply" | "the bank", "supply stacks" |

These are naming differences only. No value in this table differs between editions.

### 2.3 Claims for which no primary source was retrieved

Honesty list. Each of these is pinned in §4 or §5 as a **project decision**; later cards MUST NOT cite them
as rulebook facts.

| Claim | Where pinned | Why no citation |
|---|---|---|
| 54 vertices and 72 edges on the standard board | §4.1, §6 A3 | No retrieved rulebook states these numbers; they are derived from the hex geometry (derivation in §4.1) |
| The physical number-token **letter → number** mapping (A…R) | §4.2, A-1 | Not stated in any retrieved rulebook; the tokens show letters only on their backs, and no retrieved source documents the mapping |
| Which 9 of the 30 coastal edges carry ports | §4.1 item 6, §4.12.1 | S2/S3 say only "randomly place [the 9 harbor pieces] one on top of each harbor on the frame" — the harbour locations live on the physical frame and are shown as a diagram, never enumerated |
| Road Building with fewer than two roads in supply | A-6, §5.6 | No retrieved rulebook, FAQ entry or tournament rule addresses it |
| Maritime trade when the bank holds none of the resource requested | A-7, §5.7 | No retrieved source addresses it |
| Setup starting-resource shortfall when the bank is short | §4.3 item 8 | S1/S2 give a bank-shortage rule for **dice production** only |
| Whether a discard's **composition** is public | §4.4, B-6 | S4 §3.0.12 and S5 cover hands, not discards |
| Whether an offer may name resources the offerer does not hold | §4.12.2, B-10 | Not addressed; derived from physical impossibility and PRD-v1 FR-14.7 |
| Whether the robber steal is mandatory | §4.9, B-7 | The rulebooks use the imperative ("Steal 1 random resource card…") but never say it is mandatory; S4 §3.0.2 requires the roll to be resolved |
| Largest Army vacating | A-8, §5.8 | The rules describe Largest Army only as *transferring upwards*; no vacating rule exists because a played knight can never leave play |
| Who chooses among multiple acceptors of a trade offer | §4.12.2, B-11 | Not addressed by any rules text; PRD-v1 FR-14.5 fixes the interpretation |

---

## 3. Conventions used throughout

| Convention | Pinned value |
|---|---|
| Seats | `0, 1, 2, 3`. Turn order is ascending seat order (S1: "moving clockwise around the table"; S2 Almanac p.12 "Set-up Phase": "The other players then follow clockwise"). Seat order is also the deterministic tie-break for simultaneous decisions. |
| First player | Seat `0`, taken from run configuration (`RunConfig.first_player`). See §4.3. |
| Resources | Canonical order **(brick, wood, wool, wheat, ore)** — the order in which S1 and S6 list the five resource-card stacks (S1 components: "19x brick, 19x wood, 19x wool, 19x wheat, 19x ore"; S6 p.3: "19 x Lehm, 19 x Holz, 19 x Wolle, 19 x Getreide, 19 x Erz"). Every list, projection and hash that enumerates resources uses this order. |
| Terrain → resource | forest → wood, pasture → wool, field → wheat, hills → brick, mountains → ore, desert → none (S1 §"Roll dice" panel and p.6 "RESOLVE A 7" side notes; S2 Almanac p.10 "Resource Cards (Resources)"). |
| Hand contents | The five resource counts in canonical resource order. |
| Board identifiers | Integers, assigned by a canonical sort of derived coordinates (`ARCHITECTURE.md` §7.5, PRD-v1 FR-7.3). This document speaks of "hex", "vertex" and "edge" and never of a specific identifier value. |
| "Bank" | The shared resource supply. Always 19 cards per resource (§4.6). |
| "Player supply" | A player's own unused pieces: 15 roads, 5 settlements, 4 cities (§4.7). There is no shared piece bank; pieces are never transferred between players. |
| Integer arithmetic | All quantities are integers. Discard counts use floor division; no floats appear anywhere (`ARCHITECTURE.md` §6 clause 2). |

### 3.1 Every random draw this document pins

Determinism is a hard requirement (`ARCHITECTURE.md` §6). Every random selection below is a **recorded
draw** through the injected `RandomSource` (`ARCHITECTURE.md` §5.4). Labels come from module
constants, never inline strings (PRD-v1 FR-2.3); the labels in this table are the pinned constants for this
plugin.

| # | Draw | Where | Kind | Args | Purpose label |
|---|---|---|---|---|---|
| D1 | Assign the 19 terrain faces to the 19 hexes, random boards only | board generation | `shuffle` | the 19 terrain faces in canonical terrain order | `board_terrain_shuffle` |
| D2 | Choose the spiral's starting corner hex, spiral number placement | board generation | `choice` | the six outer-ring corner hex ids in canonical order | `board_number_corner` |
| D3 | Order the 18 tokens on the 18 non-desert hexes, random number placement | board generation | `shuffle` | the 18 tokens in canonical token order | `board_number_shuffle` |
| D4 | Assign the 9 port faces to the 9 port edges | board generation | `shuffle` | the nine port faces in canonical port order (four `generic_3_1`, then `wood_2_1`, `brick_2_1`, `wool_2_1`, `wheat_2_1`, `ore_2_1`) | `board_port_shuffle` |
| D5 | Shuffle the 25-card development deck at game start | setup | `shuffle` | the 25 card ids in canonical deck order (§4.8) | `dev_deck_shuffle` |
| D6 | First die | each roll | `randint` | `lo=1, hi=6` | `dice_die_1` |
| D7 | Second die | each roll | `randint` | `lo=1, hi=6` | `dice_die_2` |
| D8 | Which card is stolen by the robber | robber resolution | `choice` | the victim's hand as a list in canonical resource order, repeated by count | `robber_steal` |
| D9 | First player, non-default `first_player: random` setting only | setup | `choice` | `[0, 1, 2, 3]` | `setup_first_player` |

Three further pinned consequences:

* **The two dice are two independent `randint(1, 6)` draws, never one `randint(2, 12)`.** The
  distributions differ (7 is six times as likely as 12), and `ARCHITECTURE.md` §5.4 requires draws to
  be replayable semantically (PRD-v1 FR-10.2).
* **Buying a development card performs no draw.** The deck order was fixed by D5; a purchase removes the
  front card. The rule is "draw the top card of the deck" (S1 p.9 "Development Cards": "When you build a
  development card, draw the top card of the deck"; S2 Almanac p.7 "Development Cards": "take the top card
  of the draw pile"). See §4.8.
* **No other operation in the game is random.** In particular, production, discards, building, road
  counting, award computation, scoring and terminality perform **no** draws (`ARCHITECTURE.md` §6,
  PRD-v1 FR-2.6, FR-15.3).

---

## 4. Rule areas

Each rule area states three things:

* **Rule as implemented** — precise and unambiguous, in this project's own words.
* **Citation** — the rulebook location (section or rule heading, plus page where the source numbers pages).
* **Ambiguity resolved** — where the rulebook admits more than one reading: the chosen interpretation, the
  alternative considered, and why.

### 4.1 Board and topology

**Rule as implemented.**

1. The board is a hexagon of side 3 with **19 hexes**, laid out on axial coordinates `(q, r)` with
   `max(|q|, |r|, |q + r|) <= 2`. The centre hex is `(0, 0)`.
2. Terrain composition is fixed: **4 forest (wood), 4 pasture (wool), 4 field (wheat), 3 hills (brick),
   3 mountains (ore), 1 desert (produces nothing)** — 19 hexes.
3. From those coordinates the derivation yields **54 vertices (intersections)** and **72 edges (paths)**.
   Vertices split as **24** where three hexes meet, **12** where two hexes plus the frame meet, and **18**
   where one hex plus the frame meet. Edges split as **42** interior edges (between two hexes) and **30**
   coastal edges (between one hex and the frame).
4. Adjacency and incidence are **derived from the coordinates**, never hand-authored
   (`ARCHITECTURE.md` §3, §7.5).
5. A vertex is *coastal* iff it lies on at least one coastal edge; otherwise it is *interior*. Coastal
   vertices are ordinary settlement sites and may carry ports (S5 "May I build a settlement on the coast if
   no harbor hex is located there? … Yes").
6. **Ports occupy 9 of the 30 coastal edges.** The multiset is **4 × generic 3:1** and **5 × 2:1, one for
   each resource**. Which nine coastal edges carry ports, and which port face sits on each, are properties
   of the frame and are supplied as board data (§4.12.1).
7. Nothing about a hex's number token, the robber, or a port is encoded in topology; those live in state.

**Citation.**
19 hexes: S1 p.3 "COMPONENTS" ("19 terrain hexes") and S2 p.2 "Game Components" ("19 terrain hexes
(tiles)"). Terrain composition: S1 p.3 "COMPONENTS" — "3x hills, 4x forests, 4x pastures, 4x fields,
3x mountains, 1x desert". 9 harbour pieces: S2 p.2 "Game Components" ("9 harbor pieces"). One 2:1 port per
resource and the generic/specific split: S2 Almanac p.9 "Maritime Trade" — "Generic Harbor (3:1) … Special
Harbor (2:1): There is only 1 special harbor for each type of resource (with the same symbol)". The frame's
harbour locations: S2 Almanac p.12 "Set-up, Variable", step 2 — "take the 9 harbor pieces … and randomly
place one on top of each harbor on the frame" (S1 p.11 "VARIABLE SETUP" is equivalent).

**Ambiguity resolved.**

* *54 vertices / 72 edges / the 24-12-18 and 42-30 splits — **NO PRIMARY SOURCE**.* No retrieved rulebook
  states these numbers; they are the algebraic consequence of item 1. The derivation, reproduced so M3 can
  assert it (PRD-v1 SC-7): each of 19 hexes contributes 6 edges and 6 corners; emitting all 114 corners in a
  plane and deduplicating coincident points yields 54 distinct vertices and 72 distinct edges; counting
  hex-incidences per vertex yields {3 hexes: 24, 2 hexes: 12, 1 hex: 18} and per edge {2 hexes: 42,
  1 hex: 30}. PRD-v1 Appendix A's "54 vertices, 72 edges" is therefore **derived, not confirmed**. The
  structural self-check of FR-6.10 is what makes the derivation falsifiable.
* *Which 9 coastal edges carry ports — **NO PRIMARY SOURCE**.* Alternatives: (a) derive the port positions
  from the frame-piece arrangement, as the physical game does; (b) curate them as board data. **Chosen:
  (b)**, because v1 makes fixed boards the default for comparability (`ARCHITECTURE.md` §7.6) and
  because (a) would require modelling the six frame pieces, which nothing else in the engine needs. The nine
  port edges are therefore a curated, tested fact of each fixed board, and PRD-v1 Q1 must record them.
* *Are coastal intersections legal settlement sites?* S2 Almanac p.11 "Settlements" defines intersections as
  "where 3 hexes meet **or 1 or 2 hexes meet the frame**", which settles it; S3 p.15 still says "the points
  where 3 hexes meet", and S5 shows the question is still asked. **Chosen: yes, coastal vertices are
  ordinary settlement sites.** Alternative considered: treat only 3-hex vertices as intersections. Rejected:
  contradicted by S1, S2 and S5, and it would make port access unbuildable.

---

### 4.2 Number-token placement

**Rule as implemented.**

The board is generated with a number-token placement selected by `RunConfig.number_placement`. Both
supported procedures are deterministic given recorded draws.

1. **The 18 tokens.** The multiset is exactly
   `{2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12}` — every value from 2 to 12 except 7,
   appearing twice except 2 and 12 which appear once. The desert hex never receives a token.
2. **Canonical token sequence.** The tokens are held in the fixed order
   `T = (5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11)`. `T[0]` is the first token
   placed, `T[17]` the last.
3. **The spiral walk.** For any board the plugin defines a *spiral walk* over its hexes: start at a chosen
   outer-ring corner hex, walk the outermost ring counterclockwise, step inward to the inner-ring corner on
   the same ray, walk that ring counterclockwise, and finish at the centre. On the standard 19-hex board
   this visits all 19 hexes in 19 contiguous steps — every consecutive pair of hexes is adjacent, verified
   exhaustively for all six possible starting corners.
4. **Mode `spiral`.** Walk order (3), skipping the desert wherever it lies, gives 18 hexes. Place
   `T` on those 18 hexes in walk order. The starting corner is chosen by draw **D2** (`choice`
   over the six corner hexes in canonical order) unless the board data fixes it.
5. **Mode `spiral_no_adjacent_red` (the v1 default, PRD-v1 §10.2).** Mode `spiral` followed by
   the adjacency check of item 7.
6. **Mode `random`.** Place `T` on the 18 non-desert hexes in an order produced by draw **D3**
   (`shuffle` of the canonical token list). Then apply the adjacency check of item 7.
7. **Adjacency check.** The four tokens showing 6 or 8 ("the red numbers") MUST NOT lie on mutually adjacent
   hexes. If any pair is adjacent, repair deterministically: repeatedly take the adjacent red token with the
   lowest spiral-walk index and swap it with the token on the lowest-index non-red hex whose swap removes
   that adjacency and creates none; repeat until no red pair is adjacent, with a hard cap of 100 swaps, after
   which board generation fails loudly rather than emitting a defective board. The repair performs **no**
   random draw.
8. **Property of the pinned sequence.** For the standard 19-hex board, mode `spiral_no_adjacent_red`
   with sequence `T` produces **zero** adjacent 6/8 pairs for **all 6 starting corners × all 19 desert
   positions** (114 configurations, checked exhaustively). The repair step of item 7 is therefore a guard for
   curated or future non-standard boards, not a routine step.

**Citation.**
18 tokens and their composition: S2 Almanac p.10 "Number Tokens" — "The 18 number tokens are marked with
the numerals '2' through '12.' There is only one '2' and one '12.' There is no '7'"; and S2 Almanac p.10
"Resource Production" — "Each number appears twice—except for '2' and '12,' which only appear once." The
desert never gets a token: S2 Almanac p.12 "Set-up, Variable", step 3 — "Note: The desert never gets a
number token. It should be skipped." Procedure: S1 p.11 "VARIABLE SETUP", step 3 — "Arrange the discs face
down in A-B-C order. Starting in any corner of the board, place the number discs on the hexes
counterclockwise, skipping the desert"; S2 Almanac p.12 "Set-up, Variable", step 3 — "Place the number
tokens on the terrain hexes in alphabetical order, proceeding counter-clockwise toward the center. Skip the
desert." The no-adjacent-red requirement: S2 Almanac p.12 — "Alternatively, you can use a fully random
set-up… In such case, the tokens with the red numbers must not be next to each other. You may have to swap
tokens to ensure that no red numbers are on adjacent hexes." The name "spiral" for the traditional
arrangement: S4 §2.0.1 — "organizers may choose not to use the traditional spiral setup".

**Ambiguity resolved.** This is ambiguity **A-1**; the full entry is in §5.1. In brief: the rulebook fixes
the *procedure* (a fixed order, counterclockwise from a corner, toward the centre, skipping the desert) but
not the *mapping from order to numbers*, and it gives no rule for what "a corner" means on a generated
board. Both gaps are pinned here, and the pinned sequence is verified never to place 6 and 8 adjacent on the
standard board.

---

### 4.3 Setup and the snake draft

**Rule as implemented.**

1. Setup is a **phase machine like any other**, not special-cased code: it emits decision requests
   (`ARCHITECTURE.md` §5.6, §7.7; PRD-v1 FR-8.5).
2. Setup has two rounds, eight placements in total, in the **snake order** `0, 1, 2, 3, 3, 2, 1, 0`
   (seats ascending in round 1, descending in round 2).
3. In each of the eight steps the acting player makes **two decisions in order**: place one settlement on a
   legal empty vertex, then place one road on a legal empty edge adjacent to the settlement just placed.
4. **Settlement legality during setup.** The vertex MUST be empty, and the **distance rule** (§4.7) applies
   to every other building on the board, the player's own included. There is no connectivity requirement: in
   round 1 there is no network yet, and in round 2 the rulebook explicitly says the second settlement "doesn't
   have to connect to the first settlement".
5. **Road legality during setup.** The edge MUST be empty and MUST be incident to the vertex of the
   settlement just placed in this same step. It need not connect to anything else.
6. **Starting endowment.** Immediately after a player places their **second** settlement, that player takes
   **one resource card from the bank for each hex adjacent to that settlement**, of the type that hex
   produces. The desert yields nothing. A settlement adjacent to two hexes of the same terrain yields two
   cards of that resource. Round-1 settlements yield nothing.
7. **Endowment order.** Endowments are taken in the order in which the second settlements were placed, i.e.
   seats `3, 2, 1, 0`. This matters only when the bank is short (item 8).
8. **Endowment under bank shortage — NO PRIMARY SOURCE.** If the bank holds fewer cards of a resource than
   the total endowment demand for it, the entitlements of item 6 are satisfied **in the order of item 7** and
   each player receives at most what remains; the shortfall is lost. (The rulebook's bank-shortage rule is
   about dice production, not setup — see §4.6.)
9. After the eighth placement and the last endowment, the setup phase ends and a `phase_started` event
   opens the first player's turn.

**Citation.**
Snake order and the two-settlement structure: S1 p.11 "VARIABLE SETUP", step 7 "Place Your Starting Pieces"
— "The first player places 1 settlement on an empty intersection of their choice. Then they place 1 road on
an empty edge next to that settlement. The next player to the left does the same until all players have
1 settlement and 1 road on the board. … Starting with the last player and going in reverse order, each
player places 1 settlement on an empty intersection of their choice and their second road on an empty
adjacent edge." S2 Almanac p.12 "Set-up Phase" states the same in two explicitly named rounds, with "the
starting player in round one places his second settlement last". Distance rule during setup: S1 p.11 — "As
before, when placing a settlement, stay two edges away from all other settlements"; S2 Almanac p.12 —
"Important: When placing all other settlements, the Distance Rule (see page 7) always applies!" Second road
attachment: S2 Almanac p.12 — "The second road must attach to the second settlement (pointing in any of the
3 directions)." Second settlement need not connect: S2 Almanac p.12 — "It doesn't have to connect to the
first settlement." Starting resources: S1 p.11, step 8 — "Each player takes 1 matching resource card from the
supply for each hex adjacent to their second settlement"; S2 Almanac p.12 — "Each player receives his
starting resources immediately after building his second settlement".

**Ambiguity resolved.**

* *Which player is first, and is the "each player rolls the dice, highest roll goes first" procedure part of
  setup?* S1 p.11 step 6 and S2 Almanac p.12 "Round One" both specify a dice-off. **Chosen: the first player
  is taken from run configuration, default seat `0`; no RNG is consumed.** Alternative considered:
  implement the dice-off as draw D9. Rejected as the default because (a) it spends randomness on a fact the
  benchmark wants held constant, (b) PRD-v1 FR-6.7 declares that seat order confers an advantage and that
  mirrored pairings are required — mirroring is only meaningful if the first player is a known input, and
  (c) the rulebook itself treats the convention as optional: S5 "Gameplay — Do we always have to observe the
  rule that the oldest player places the first settlement? No. This rule is a guideline". Draw D9 is retained
  for the non-default `first_player: random` setting.
* *Round 1 road placement — must it connect to the settlement just placed?* S2 Almanac p.12 says only that
  round 2's road must attach to the second settlement; S1 says the road goes "on an empty edge next to that
  settlement" in both rounds. **Chosen: yes, in both rounds the road must be incident to the settlement
  placed in the same step.** Alternative considered: allow any empty edge in round 1. Rejected as
  contradicted by S1.
* *Starting-endowment bank shortage.* **Chosen:** order-dependent partial grant, as in item 8. Alternative
  considered: apply the production rule of §4.6 (all-or-nothing unless only one player is affected).
  Rejected because §4.6's rule is quoted inside "Resource Production", is about the dice roll, and because
  the setup grant is taken one player at a time by explicit agreement of S1/S2. Flagged **NO PRIMARY
  SOURCE**.
* *PRD divergence — FR-8.4.* See §6.2 (D-3).

---

### 4.4 Turn structure and the decision queue

**Rule as implemented.**

The engine has no "turn index" as its primitive: it has phases that open **decision requests**
(`ARCHITECTURE.md` §5.6, §7.7; PRD-v1 FR-9.1–9.6). A phase is a named state with a set of open
requests; the phase ends when its request set is empty; every phase transition emits a
`phase_started` event and a `phase` record (PRD-v1 FR-3.9, FR-9.4).

**Phases.**

| Phase | Who decides | Requests open | Ends when |
|---|---|---|---|
| `setup_round_1` / `setup_round_2` | seats in snake order | `place_settlement`, then `place_road` | all 8 steps done |
| `turn_production` | current player | one request offering `play_dev_card` and `roll_dice` | the current player rolls |
| `discard` | **all** players holding more than 7 resource cards, concurrently | one `discard_resources` per eligible player | every eligible player has discarded |
| `robber` | current player | `move_robber`, then (if needed) `choose_robber_victim` | the robber has moved and the steal is resolved or skipped |
| `action` | current player | one request offering the whole action phase: `maritime_trade`, `offer_trade`, `respond_trade` (to others), `cancel_trade`, `build_road`, `build_settlement`, `build_city`, `buy_dev_card`, `play_dev_card`, `end_turn` | the current player ends the turn |
| `road_building` | current player | `place_free_road` (up to twice, §5.6) | both roads placed, or stopped by supply/legality |
| `trade_response` | all non-offering players holding at least one resource card, concurrently | `respond_trade` | all have responded, or the offerer cancels or selects a partner |
| `terminal` | nobody | none | — |

**Rules that govern all phases.**

1. **Turn order** is ascending seat order, wrapping `3 → 0`.
2. **Only the current player acts**, except in the concurrent phases `discard` and
   `trade_response`.
3. **Concurrent decisions are not sequential private turns** (`ARCHITECTURE.md` §7.7, PRD-v1 FR-9.5,
   FR-9.6). All requests in the phase open at once, and **every request in a concurrent phase is answered
   against the state as it was when the phase opened**:
   * a discard is computed from the hand the player held when the 7 was rolled, and no player sees another
     player's submitted discard before making their own;
   * a trade response is made without seeing any other player's response.
4. **Resolution order.** For logging and deterministic application, simultaneously open requests are
   processed in **ascending seat order** (PRD-v1 FR-9.3). Resolution order is a property of the engine, not
   of the order in which a runner delivers actions; a record produced by four concurrent clients is
   byte-identical to one produced sequentially in seat order.
5. **Consequences of a 7 are atomic within the turn.** After a 7 the roll must be fully resolved — discard
   phase, then robber move, then steal — before any other action is legal (PRD-v1 FR-10.5; S4 §3.0.2).
6. **No other action may precede the roll**, except playing a development card (PRD-v1 FR-10.1; S4 §3.0.1).
7. **Turn start.** At the transition into a player's turn the engine first tests the win condition (§4.13).
   If that player already has 10 or more victory points, the game terminates immediately and no roll happens
   (S5 "Victory Conditions — If upon starting my turn I already have the number of victory points required
   for a win, do I still have to roll the dice? No.").
8. **Rejected actions.** An action naming a request that is not open is rejected with `NO_SUCH_REQUEST`;
   an action addressed to a request open to a different player is rejected with `NOT_YOUR_DECISION`;
   both leave the state hash unchanged (PRD-v1 FR-9.2, FR-3.4).

**Citation.**
Turn order and the phase list: S1 p.5 "TURN OVERVIEW" — "Production Phase: play a development card
(optional), roll dice, collect resources or resolve a 7" and "Action Phase: in any order (optional): trade;
build roads, settlements, cities, and development cards; play a development card (if you did not play one
before the dice roll)"; S1 p.6 "RESOLVE A 7" — "1. DISCARD RESOURCES … 2. ACTIVATE THE ROBBER"; S1 p.7
"ACTION PHASE" — "You may take actions in this phase as often as you like and in any order, as long as you
have the resources to do so." "A turn consists of two phases" and "moving clockwise around the table": S1
p.5. Discard before robber: S2 Almanac p.11 "Rolling a '7' and Activating the Robber" — "(1) Each player
counts his resource cards … (2) Then you … must move the robber … (3) After discarding occurs, you also
steal…". Concurrent discard and trade responses: PRD-v1 FR-9.5, FR-9.6, `ARCHITECTURE.md` §7.7. Roll
resolution is atomic: S4 §3.0.2 — "Once the dice are rolled, the dice roll must be resolved (resources must
be distributed, or the robber must be placed and a card stolen) before any other actions may be taken."
Only a development card may precede the roll: S4 §3.0.1 — "Players are allowed to play any development card
(for example, a knight card) before they roll the dice. No other actions may occur prior to the rolling of
the dice."

**Ambiguity resolved.**

* *Is the discard phase sequential or concurrent?* The rulebook describes it as happening to everyone at
  once ("Each player who has more than 7 resource cards must choose half…"), and `ARCHITECTURE.md`
  §7.7 forbids simulating concurrent decisions as sequential private turns because that changes what players
  can observe. **Chosen: concurrent — all requests opened at once, each answered against the phase-opening
  state, logged in seat order.** Alternative considered: resolve discards one seat at a time, letting later
  players watch earlier hands shrink. Rejected: the *count* discarded is public anyway, but the *composition*
  is not, and a sequential simulation would leak it through subsequent hand sizes.
* *Is a discard's composition public — **NO PRIMARY SOURCE**?* **Chosen: the number of cards discarded is
  public, the identities are private** (they go to the bank unseen). Alternatives: (a) reveal the
  composition; (b) keep both private. Rejected (a) because S4 §3.0.12 prohibits showing resource cards to
  other players outside a trade display and S5 requires hands to stay face down; rejected (b) because the
  discard count is a trivial consequence of the public hand count.
* *Does a player with exactly 8 cards discard 4?* Yes: "more than 7" means 8 or more, and "half (rounded
  down)" is integer division (S1 p.6; S2 Almanac p.11). Recorded because it is a common implementation
  error.
* *Which requests count as "open" during a concurrent phase?* **Chosen:** exactly one request per eligible
  player, each carrying its own `request_id`. Alternative considered: a single broadcast request
  answered by several players. Rejected: `ARCHITECTURE.md` §5.6 makes a request addressed to one
  player the primitive, and FR-9.5/FR-14.4 speak of requests *to all* players.

---

### 4.5 Production and dice

**Rule as implemented.**

1. A turn opens with one decision offering exactly two actions: `roll_dice` and
   `play_dev_card` for any development card the player may legally play (§4.8). If no development card
   is playable, only `roll_dice` is offered.
2. `roll_dice` consumes draws **D6** and **D7** in that fixed order and produces
   `total = d1 + d2` in `2..12`.
3. **On a total other than 7:** every hex whose number token equals `total` and which does not hold
   the robber produces. Each player receives **1 resource card per settlement and 2 per city** on such a
   hex, in the corresponding resource.
4. Production is applied simultaneously and is subject to §4.6.
5. **On a total of 7:** no hex produces at all. The engine opens the `discard` phase (§4.4), then the
   `robber` phase (§4.9).
6. A rolled total always matches at least one hex: the 18 tokens cover every value in `2..12` except 7.
7. Rolling has no other side effect, and `is_terminal` / `outcome` never roll (PRD-v1 FR-15.3).

**Citation.**
Two dice: S1 p.5 "Production Phase" — "Roll both dice and add them together. This total determines which
hexes produce resources this turn." Production amounts: S1 p.6 — "Each player with a settlement on a
producing hex receives 1 resource card of the corresponding type from the supply… a player receives 2
resource cards for each of their cities on that hex"; S2 Almanac p.10 "Resource Production" — "Each
settlement produces 1 resource card and each city produces 2 resource cards." Robber blocks production:
S1 p.6 — "Important: A hex with the robber does not produce resources when its number is rolled"; S2 Almanac
p.11 "Robber". A 7 produces nothing: S1 p.6 "RESOLVE A 7" — "When you roll a 7, hexes do not produce any
resources." Roll must be resolved before anything else: S4 §3.0.2.

**Ambiguity resolved.**

* *May the current player decline to roll, or roll after acting?* **Chosen: no.** The roll is mandatory and
  is the second action of the production phase. Alternative considered: permit trade/build before rolling.
  Rejected: S4 §3.0.1 — "No other actions may occur prior to the rolling of the dice"; S5 "Resource Cards —
  After the production roll, may I voluntarily take fewer resources or none at all? No."
* *Is production applied to one player at a time?* **Chosen: production is computed for all players
  simultaneously, then applied.** This is what makes §4.6 well-defined. Alternative considered: apply seat by
  seat, letting earlier seats drain the bank. Rejected: the rulebook's shortfall rule ("if only one player is
  affected…") only makes sense if the demand set is computed before distribution begins, and S2 Almanac p.10
  speaks of the total earned by everyone.
* *May a player count the bank before distribution?* Yes: S5 "Resource Cards — May I count the Resource
  Cards in the supply stacks during play? Yes, immediately after a production roll, before distributing the
  resources — but only if it isn't sure whether there will be enough cards for all players entitled to
  receive them." The engine exposes bank contents publicly at all times, which is a superset of what the
  rulebook permits and leaks nothing.

---

### 4.6 Bank supply limits

**Rule as implemented.**

1. The bank holds **19 cards of each of the five resources** at the start of the game. Bank contents are
   public.
2. Production demand for a resource is the total number of cards of that resource all players earn from the
   roll. Distribution is decided **per resource, independently**:
   * If `bank[r] >= demand[r]`, every player receives exactly what they earned.
   * Otherwise, if **exactly one** player earns a positive amount of `r`, that player receives
     `bank[r]` cards — everything left — and the remainder of their entitlement is lost.
   * Otherwise (**two or more** players earn a positive amount of `r`), **no player receives any
     `r`**; the cards stay in the bank.
3. A shortage of one resource never affects any other resource.
4. **A settlement earns nothing at all on a short resource** under the two-or-more-players case; it does not
   earn a reduced amount.
5. Bank contents never exceed 19 per resource; a discarded, spent, stolen or traded card moves between hands
   and the bank, so per-resource conservation (bank + all hands = 19) always holds (PRD-v1 FR-6.9).
6. The bank has no role in building: pieces come from the player's own supply (§4.7).

**Citation.**
19 of each resource: S1 p.3 "COMPONENTS" — "95 resource cards … 19x brick, 19x wood, 19x wool, 19x wheat,
19x ore"; S6 p.3 — "95 Rohstoffkarten … 19 x Lehm, 19 x Holz, 19 x Wolle, 19 x Getreide, 19 x Erz"; S4
§2.0.7 — "all players should verify that … there are … 19 of each resource card". The shortfall rule: S1
p.6 — "If there are not enough resource cards in the supply to fulfill everyone's production, then no one
receives any of that resource. However, if only one player is affected, give that player as many of those
resource cards as remain in the supply." The 5th edition is wordier and identical in effect — S2 Almanac
p.10 "Resource Production": "If there are not enough resource cards to give every player all the production
they earn, then no player receives any of that resource that turn. Exception: If the shortage of resource
cards only affects a single player, give that player as many of these resources as are left in the supply,
and any extras are lost. In either case, production of other types of resources is not affected." S5
confirms both branches: "In case not enough Resource Cards of a certain type are available, does a player get
nothing even if he is the only one to receive this resource? No. In this case, he receives all available
Resource Cards of this type" and "In what order are the Resource Cards distributed if there are not enough
cards of a certain type to supply all players? … If the number of cards of this type is indeed insufficient,
then none of the players receives this resource on this turn." S4 §3.0.11 restates it as a tournament
clarification and therefore takes precedence over any contrary reading.

**Ambiguity resolved.** This is ambiguity **A-5**; the full entry is in §5.5.

* *PRD divergence — FR-10.4.* See §6.2 (D-2).

---

### 4.7 Building and pieces

**Rule as implemented.**

**Costs** (paid from the player's hand to the bank, atomically):

| Build | Cost |
|---|---|
| Road | 1 brick, 1 wood |
| Settlement | 1 brick, 1 wood, 1 wool, 1 wheat |
| City (upgrade of an owned settlement) | 2 wheat, 3 ore |
| Development card (purchase) | 1 wool, 1 wheat, 1 ore |

**Piece supplies.** Each player begins with **15 roads, 5 settlements, 4 cities**. These are the only pieces
that player will ever have; pieces are never transferred between players and never leave the game except by
being spent from the player's own supply onto the board (and a settlement returns to its owner's supply when
upgraded to a city).

**Roads.**

1. A road is placed on an empty edge.
2. After setup, a road MUST connect to the placing player's own network: the edge MUST be incident to a
   vertex carrying the player's own road, settlement, or city.
3. A road MUST NOT be built "on the other side of" another player's settlement or city: an edge incident to a
   vertex occupied by an opponent's building is legal only if it is **also** incident to a vertex of the
   placing player's own network. An opponent's building is never itself a connection point.
4. A road costs 1 brick + 1 wood and is worth 0 victory points.

**Settlements.**

1. A settlement is placed on an empty vertex.
2. **Distance rule.** At the moment of placement, **none of the three vertices adjacent to the target vertex
   by a single edge may hold any settlement or city — the placing player's own included.**
3. **Connectivity.** After setup, the target vertex MUST be incident to at least one edge carrying one of the
   placing player's own roads.
4. A settlement is worth 1 victory point. It produces 1 resource card from each adjacent hex whose number is
   rolled.

**Cities.**

1. A city is created only by **upgrading a settlement the player already owns on the board**: the vertex is
   unchanged, the settlement piece returns to the owner's supply, and a city piece is placed there.
2. A city MUST NOT be placed on an empty vertex, ever, for any price (S5: paying a city's cost does not
   permit building a city on an empty intersection).
3. A city is worth 2 victory points and produces 2 resource cards from each adjacent hex whose number is
   rolled.
4. A settlement may be upgraded to a city in the same turn it was built.

**Piece exhaustion.** If a build would require a piece the player no longer has, the corresponding action is
**not offered** and, if attempted, is rejected with `NO_PIECES_REMAINING`. A player at their road limit
simply cannot build roads; a player with all 5 settlements on the board cannot build a settlement until one
is upgraded (S2 Almanac p.11 "Settlements": "If you have built all 5 of your settlements, you must upgrade
1 of your settlements to a city before you can build another settlement").

**Citation.**
Costs: S1 p.9 "BUILDING COSTS" panel and the printed Building Costs card; S6 "Straße — Baukosten: 1 x Lehm +
1 x Holz", "Siedlung — Baukosten: 1 x Lehm + 1 x Holz + 1 x Wolle + 1 x Getreide", "Stadt — Baukosten:
2 x Getreide + 3 x Erz", "Entwicklungskarten — Kosten: 1 x Wolle + 1 x Getreide + 1 x Erz" (the German
manual states the same values in running text, which is why it is cited for the numbers); S2 Almanac p.6
"Building Costs Cards". Piece counts: S1 p.3 "COMPONENTS" — "60 roads (15x each color), 20 settlements (5x
each color), 16 cities (4x each color)"; S2 p.2 "Game Components" — "16 cities (4 of each color), 20
settlements (5 of each color), 60 roads (15 of each color)"; S4 §2.0.6 — "5 settlements, 4 cities, 15
roads". Road connectivity and the opponent's-building rule: S1 p.7 "ROADS" — "A new road must connect to one
of your existing roads or buildings. You may not build a road starting on the other side of an opponent's
building"; S2 Almanac p.11 "Roads"; S5 "Roads — May the roads I build 'go through' other players'
settlements and cities? No." Distance rule: S1 p.7 "SETTLEMENTS" — "When placing a settlement, stay at least
two edges away from all other buildings!"; S2 Almanac p.7 "Distance Rule" — "You may only build a settlement
on an unoccupied intersection and only if none of the 3 adjacent intersections contains a settlement or
city"; S5 "Settlements and Cities — What exactly does the 'distance rule' say? It says that at any time
during the game, each settlement and each city must be surrounded by three intersections that neither are
occupied by one's own nor by another player's settlement or city." Settlement connectivity: S2 Almanac p.11
"Settlements" — "(1) Your settlement must always connect to 1 or more of your own roads"; S5 "Settlements and
Cities — Over the course of the game, may I build further settlements and roads somewhere on the game board
that don't connect to my already existing settlements and roads? No. This is only possible during the set-up
phase." Cities: S1 p.7 "CITIES" — "Cities always replace settlements. To build a city, remove one of your
settlements from the board, return it to your player area, and place your city where the settlement was
located"; S2 Almanac p.6 "Cities" — "You cannot build a city directly. You can only upgrade an existing
settlement to a city"; S4 §3.0.5 — "Players are allowed to upgrade a settlement to a city in the same turn
it is built." Upgrade returns the settlement to supply: S2 Almanac p.6 "Build (Building)" — "If you build a
city, return the settlement to your supply."

**Ambiguity resolved.**

* *Distance rule at "exactly two edges".* S1 says "at least two edges away"; S2 says "none of the 3 adjacent
  intersections contains a settlement or city". These are the same rule expressed topologically. **Chosen:
  the target vertex must have no occupied vertex at graph distance 1**, which is equivalent to a minimum
  graph distance of 2 between any two buildings. Alternative considered: implement it as a geometric
  distance of two hex-widths. Rejected: it is the same thing on this lattice, and the graph formulation is
  exact and testable (PRD-v1 FR-11.4).
* *Does the distance rule block the player's own buildings?* **Chosen: yes.** S5 spells out "neither are
  occupied by one's own nor by another player's settlement or city". Alternative considered: only opponents'
  buildings block (a common house rule). Rejected as explicitly wrong.
* *May a player build a road that touches an opponent's building on one end if the other end joins their own
  network?* **Chosen: yes** — S1's prohibition is on building *starting on the other side of* an opponent's
  building, i.e. on an edge whose only connection to the player runs through that building. Rule 3 states
  exactly this: an edge is legal iff it is incident to a vertex of the player's own network. Alternative
  considered: forbid any edge incident to an opponent's building. Rejected: it would forbid the legal case of
  a coastal road passing an opponent's coastal settlement while the player's own road runs the other way.
* *Is a road along the coast legal?* Yes (S2 Almanac p.6 "Coast": "You can build a road along a coast").
* *May a player build on a vertex/edge occupied by a port?* Ports occupy edges and are not pieces; a port
  edge is not buildable (roads go on empty edges), but the port's two endpoint vertices are ordinary
  settlement sites (S5 "Settlements and Cities — May I build a settlement at a harbor during the set-up
  phase? Yes").

---

### 4.8 Development cards

**Rule as implemented.**

**Deck composition.** 25 cards. Card identities are distinct within a type (`knight#0` …
`knight#13`, `victory_point#0` … `victory_point#4`, `road_building#0/1`,
`year_of_plenty#0/1`, `monopoly#0/1`) so that the shuffle draw D5 has a well-defined value and
the deck order is hashable.

| Card | Count |
|---|---|
| `knight` | 14 |
| `victory_point` | 5 |
| `road_building` | 2 |
| `year_of_plenty` (6th edition name: *Invention*) | 2 |
| `monopoly` | 2 |
| **Total** | **25** |

**Setup.** The deck is shuffled exactly once, at game start, by draw **D5** (`shuffle` over the 25
canonical ids). This is the only randomness the deck ever consumes.

**Purchase.**

1. `buy_dev_card` costs 1 wool, 1 wheat, 1 ore, paid to the bank.
2. The purchase **removes the front card** of the deck and adds it to the buyer's private hand. **No random
   draw is performed** (the order was fixed by D5).
3. A purchased card is hidden from all other players and is **never** counted as a resource card for the
   hand limit or for the robber (S1 p.9: "They do not count toward the number of cards in your hand when a
   7 is rolled, and the robber may not steal them").
4. If the deck is empty, `buy_dev_card` is **not offered** and is rejected with
   `NO_DEV_CARDS_REMAINING` (S1 p.9: "Development cards never go back into the supply. If the supply
   runs out, you may not build any more cards"; S2 Almanac p.5: "you cannot buy development cards if the
   supply is empty").
5. There is no reshuffle, at any time, ever. There are exactly 25 development cards in a game.

**Timing — general.**

1. At most **one** development card may be played per turn (S1 p.9: "You may play 1 development card during
   your turn"; S2 Almanac p.7: "You may only play 1 development card during your turn—either 1 knight card
   or 1 progress card"), except that **any number of `victory_point` cards may be revealed at the
   moment of winning** (§4.13), including ones bought this turn.
2. A card bought this turn MUST NOT be played this turn (S1 p.9: "It may not be a card you built this
   turn"; S2 Almanac p.5: "You may not, however, play a card that you bought during the same turn"), with
   the single `victory_point` exception of rule 1.
3. A playable card may be played **at exactly two windows**: (a) as the very first action of the production
   phase, before the roll; (b) at any point in the action phase, provided nothing was played before the roll.
   There is no third window, and in particular a card may **not** be played between the roll and the
   resolution of the roll (S4 §3.0.2).
4. Played pieces stay face up in front of the player. Played `knight` cards remain in play forever and
   count for Largest Army. Played `year_of_plenty`, `monopoly` and `road_building` cards
   are removed from the game (S5 "Where do I place the Development Cards I played? … Place your Invention,
   Monopoly, and Road Building cards on a discard pile to remove them from the game"). Development cards are
   never traded or given away (S1 p.9).

**Timing and effect, per card type.**

| Card | Window | Effect as implemented |
|---|---|---|
| `knight` | before the roll, or in the action phase | Moves the robber (§4.9). It **does not** trigger the discard phase (A-2; S5: "When a Knight Card is played, do players with more than seven Resource Cards also have to discard half of them? No. This only applies when a '7' is rolled"). The card is placed face up and counts toward Largest Army (§4.11). |
| `year_of_plenty` | before the roll, or in the action phase | Take **exactly 2 resource cards** from the bank and add them to hand. The two cards **may be the same resource or two different resources** (A-4). The take is limited by bank contents: the player takes at most `bank[r]` of each named resource, and no draw is involved. |
| `monopoly` | before the roll, or in the action phase | The player announces exactly one resource. **Every other player gives all of that resource from their hand**, added to the player's hand, in one atomic event. A player holding none gives nothing. Nothing is taken from the bank. |
| `road_building` | before the roll, or in the action phase | The player places up to **2 roads at no resource cost**, subject to the normal road legality rules (§4.7), the player's remaining road supply, and — because the action is not complete while roads are being placed — S4 §3.0.8's rule that the placement is final once the next action begins. The two placements are two sequential `place_free_road` decisions. Supply shortfall is A-6. |
| `victory_point` | the winning moment only | Worth 1 victory point, counted in the owner's **true** total from the moment of purchase. It is never "played" as an action; it is revealed only when it contributes to reaching the winning total on its owner's turn, and it is excluded from every other player's view of that player's public score (PRD-v1 FR-13.8, FR-16.4). |

**Citation.**
Deck composition: S1 p.3 "COMPONENTS" — "25 development cards … 5x Victory Point, 2x Monopoly, 2x Road
Building, 2x Invention, 14x Knight"; S2 p.2 "Game Components" — "25 development cards (14 knight cards,
6 progress cards, 5 victory point cards)"; S2 Almanac p.10 "Progress Cards" — "There are 2 each of 3
varieties"; S4 §2.0.7 — "25 development cards (14 knight cards, 6 progress cards, 5 victory point cards)";
S6 p.3 — "5 x Siegpunkt, 2 x Monopol, 2 x Straßenbau, 2 x Erfindung, 14 x Ritter". Purchase: S1 p.9
"Development Cards"; S2 Almanac p.7 "Development Cards". Timing: S1 p.9 — "You may play 1 development card
during your turn… It may not be a card you built this turn. You may play a development card before rolling
dice or at any time during the Action phase"; S2 Almanac p.7 — "You may only play 1 development card during
your turn—either 1 knight card or 1 progress card. You can play the card at any time, even before you roll
the dice. You may not, however, play a card that you bought during the same turn." S5 — "How many
Development Cards may I buy on my turn? As many as you can pay for. You may play only one Development Card
per turn, but not during the same turn you bought it" and "May I play Development Cards before rolling the
dice? Yes. Note that you may play only one Development Card per turn: if you have played this card before
rolling the dice, you are not allowed to play another one afterwards." Knight: S1 p.9 "KNIGHT — When you play
a Knight card, you must 'Activate the Robber'"; S2 Almanac p.8 "Knight Cards". Invention / Year of Plenty:
S1 p.9 — "take any 2 resource cards from the supply. Add them to your hand. They may be 2 of the same
resource or 2 different resources"; S2 Almanac p.10 "Progress Cards" — "You may use these cards to build in
the same turn." Monopoly: S1 p.9 — "Announce one type of resource. Each player must give you all their
resource cards of that type. You may only request one type of resource when you play this card, regardless
of how many cards you receive"; S2 Almanac p.10 — "If an opponent does not have a resource card of the
specified type, he does not have to give you anything." Road Building: S1 p.9 — "build 2 roads at no cost
(i.e., without spending any resource cards)"; S2 Almanac p.10 — "place 2 free roads on the board (according
to normal building rules)". Victory Point: S1 p.9 — "Play any number of Victory Point cards (even on the
turn you build them) to win the game. Reveal all your Victory Point cards, including any built this turn, if
you can reach the number of VPs needed to win. Otherwise, you must keep Victory Point cards hidden in your
player area"; S5 — "Does the restriction that only one Development Card may be revealed during one's turn
also apply to Victory Point Cards? No. If, on your turn, you have reached the victory points (including your
Victory Point Cards) required to win, you may reveal all your Victory Point Cards at once." Action
completion: S4 §3.0.8.

**Ambiguity resolved.** Per-card timing is **A-2** (§5.2). The Year of Plenty duplicate-resource question is
**A-4** (§5.4) and is *not* ambiguous: the rulebook answers it. The Road Building supply shortfall is **A-6**
(§5.6). Additional pins:

* *Does playing a `knight` during the production phase use up the turn's card?* **Chosen: yes.** S5:
  "May I play Development Cards before rolling the dice? Yes. Note that you may play only one Development
  Card per turn: if you have played this card before rolling the dice, you are not allowed to play another
  one afterwards."
* *May the same player move the robber twice in one turn (7, then a knight)?* Yes — S5 "May I move the robber
  twice during my turn – the first time by rolling a '7' and the second time by playing a Knight Card? Yes.
  Playing a Development Card is independent from the dice roll result."
* *Is `year_of_plenty` limited by the bank?* **Chosen: yes** — the cards come "from the supply" (S1),
  and a player may not take a card the bank does not have. Alternative considered: allow the take and drive
  the bank negative. Rejected: it breaks the resource-conservation invariant (PRD-v1 FR-6.9). Flagged
  **NO PRIMARY SOURCE** for the shortage case.
* *PRD divergence — FR-10.1.* See §6.2 (D-4).

---

### 4.9 Robber movement and stealing

**Rule as implemented.**

1. The robber starts the game on the desert hex and is active from the first turn — there is no grace period
   and no "friendly robber" (S4 §3.0.16).
2. The robber moves in exactly two situations: after a 7 is rolled, and when a `knight` card is played.
   Nothing else moves it.
3. A hex occupied by the robber produces nothing when its number is rolled. The robber does **not** block
   building, and it does not close a port whose edge touches its hex (S5 "Does the robber block the players
   from building roads, settlements, and cities? No." and "If a harbor hex is blocked by the robber, does it
   mean that the harbor is blocked too? No.").
4. **Movement.** The moving player MUST place the robber on a **different** hex from the one it currently
   occupies. The desert is a legal destination. There is no option to leave the robber in place.
5. **Victim selection.** After the robber has moved, the candidates are all players **other than the mover**
   who have at least one settlement or city on a vertex adjacent to the robber's new hex. The mover chooses
   one. If there is exactly one candidate, the engine does not open a decision: that candidate is the victim.
6. **Steal.** If the chosen victim holds at least one resource card, **one card is taken uniformly at random
   from that player's hand** by draw **D8**, and is added to the mover's hand. If the victim holds no resource
   cards, nothing is taken and the turn proceeds. The steal is **mandatory**: the mover may not decline to
   name a victim, but may deliberately name a victim who holds no cards.
7. **No discards from a knight.** Playing a `knight` moves the robber and steals but never opens the
   `discard` phase (A-2; S5).
8. **Asymmetric reveal.** The identity of the stolen card is revealed to the thief only. The victim learns
   only that one card of a particular type left their hand. The thief's gain is visible to everyone else only
   as a hand-size change (PRD-v1 FR-12.5 and the projection table in §8.16).
9. Development cards are never stolen (S1 p.9).

**Citation.**
Robber origin and effect: S2 Almanac p.11 "Robber" — "The robber begins the game in the desert. It is moved
only by rolling a '7' or playing a Knight card"; S1 p.6 — "Important: A hex with the robber does not produce
resources when its number is rolled." Movement: S1 p.6 "ACTIVATE THE ROBBER — You must move the robber to a
new hex"; S2 Almanac p.11 — "The robber must be moved. You may not choose to leave the robber on the same
hex"; S5 "Do I have to place the robber on a different hex after a '7' was rolled, or may I briefly remove
him from the hex he was occupying and then return him to the same hex? You must place the robber on a
different hex." Victim selection: S1 p.6 — "Steal 1 random resource card from a player who has a building on
that hex. If multiple players have buildings on the new hex, you choose one player to rob"; S2 Almanac p.11
"Rolling a '7' and Activating the Robber" — "If there are 2 or more players with buildings there, you may
choose from which one to steal." Empty-handed victim: S2 Almanac p.8 "Knight Cards" — "If he has no cards,
you get nothing!"; S5 "What happens if I place the robber next to a player who doesn't have a card? Bad
luck: You won't be able to draw a card from this player." Desert steal: S5 "If I move the robber to the
desert, do I draw a card from the owner of an adjacent settlement or city? If you move the robber to the
desert because you rolled a '7' or played a Knight Card: yes." No voluntary surrender: S5 "May I voluntarily
give a card to an opponent, instead of letting him draw it? No." Knights do not force discards: S5
"Development Cards – Knights — When a Knight Card is played, do players with more than seven Resource Cards
also have to discard half of them? No. This only applies when a '7' is rolled." No friendly robber: S4
§3.0.16.

**Ambiguity resolved.**

* *Is the steal mandatory — **NO PRIMARY SOURCE**?* **Chosen: yes.** The mover must choose a victim when at
  least one candidate exists. Alternatives: (a) make the steal optional (a widespread house rule and what
  some digital implementations do); (b) require the mover to choose a victim who actually holds a card.
  Rejected (a): S4 §3.0.2 requires the roll to be *resolved* — "the robber must be placed and a card stolen"
  — before any other action, so declining is not a legal resolution. Rejected (b): S2 Almanac p.8 and S5 both
  contemplate the mover picking a card-less victim and getting nothing, which would be unreachable if such a
  victim were not a candidate.
* *Do dev cards count toward the 7-card limit, or are they stealable?* No to both (S1 p.9). Recorded because
  implementations get this wrong.
* *Is the victim's card chosen uniformly?* The rulebook says "random". **Chosen: uniform over the victim's
  entire hand**, materialised in canonical resource order and chosen by one `choice` draw (D8), so a
  player holding 3 wood and 1 ore loses wood with probability 3/4. Alternative considered: choose the
  resource type uniformly, then a card of it. Rejected: it is not what "1 random resource card" means
  physically (the cards are a physical hand) and it distorts the value of holding many of one resource.
* *If the robber moves to the desert after a 7, is a card still stolen?* Yes (S5).

---

### 4.10 Longest Road

**Rule as implemented.**

1. The Longest Road special card is worth **2 victory points**. It is held by a player, not owned by the
   board.
2. **Definition.** A player's *continuous road* is a set of that player's roads forming either (a) a
   **simple path** — a sequence of distinct vertices joined by that player's roads, no vertex repeated — or
   (b) a **simple cycle** — a closed loop of that player's roads returning to its start without repeating a
   vertex. Its **length** is its number of roads.
3. **Opponent buildings interrupt.** A vertex occupied by another player's settlement or city may be an
   **endpoint** of a continuous road but never an **interior** vertex. Equivalently, the player's road graph
   is split at every vertex occupied by an opponent's building. A player's **own** settlements and cities do
   **not** interrupt it, and other players' roads do not interrupt it.
4. **Length of a player's road** = the maximum length over all continuous roads of that player, i.e. the
   maximum over simple paths **and** simple cycles, computed by **exhaustive enumeration**. No greedy,
   heuristic or approximate computation is permitted (PRD-v1 FR-13.10).
5. **Requirements for the award** are met by a player iff that player's road length is at least **5** and is
   (one of) the greatest road length among all players, "greatest" being computed over players whose length
   is at least 5.
6. **Award computation** runs after **every** state transition:
   * Let `M` = the greatest road length among all players, `C` = the set of players whose length
     equals `M`.
   * If `M < 5` or `|C| = 0`: the card is **unheld**.
   * If `|C| = 1`: that player holds the card.
   * If `|C| >= 2`: the card is held by the incumbent if the incumbent is in `C`; otherwise the
     card is **unheld**.
7. The card is awarded and revoked **automatically**, at the moment the conditions change, with no claim
   action, and can change hands during a turn other than the holder's.
8. **Losing it.** A build by another player that breaks the incumbent's road can take the card away, return
   it to the board, or — if the incumbent remains tied for longest — leave it with the incumbent.
9. **Re-acquisition.** A player re-acquires the card the moment rule 6 yields a single candidate for that
   player. There is no memory of previous holders, no priority, and no waiting period.

**Citation.**
Threshold and value: S1 p.5 "LONGEST ROUTE — The first player to have 5 continuous roads in play receives
this tile… The Longest Route tile is worth 2 VPs"; S2 p.5 "LONGEST ROAD"; S3 Almanac p.13 "Longest Road" —
"If you are the first player to build a continuous road of at least 5 individual road pieces, you take this
special card… This card is worth 2 victory points." Transfer: S1 p.5 — "If another player has more continuous
roads in play, they immediately receive this tile"; S2 Almanac p.9 — "If you hold the 'Longest Road' card and
another player builds a longer road, he immediately acquires your 'Longest Road' card. He also acquires the
2 bonus victory points." Definition: S5 "What is the Longest Road? The Longest Road is a continuous road
connecting two intersections, which consists of at least five individual road pieces and is not interrupted
by game pieces belonging to other players. It has more individual road pieces than any other connecting road
of this type." Interruption by a settlement: S2 Almanac p.9 — "You can break an opponent's road by building
a settlement on an unoccupied intersection along his road!"; S5 "How can I interrupt an opponent's Longest
Road? By building a settlement on an intersection of the Longest Road." Own settlements do not interrupt:
S5 "Do my own settlements interrupt my continuous road? No." Branching: S2 Almanac p.9 — "If your road
network branches, you may only count the single longest branch for purposes of the longest road"; S1 p.5 —
the example reads "breaking Red's route into a four-segment route and a three-segment route." Cycles count
fully: S5 "Can a continuous road be circular? In principle, yes; but on Catan the circle is a hexagon. When
counting the individual road pieces, it doesn't matter whether or not they are built in a more or less
straight line - what matters is that they establish an uninterrupted connection between two intersections.
This is why six road pieces connected in a hexagonal fashion still count as six road pieces." Automatic
award: S4 §3.0.4 — "The 'Longest Route' and 'Largest Army' tiles automatically transfer to a player as soon
as they meet the conditions to earn that tile."

**Ambiguity resolved.** The tie/vacate/re-acquire question is **A-8** (§5.8). Two further pins:

* *Longest simple path, or longest trail?* **Chosen: maximum over simple paths and simple cycles.**
  Alternative considered: longest **trail** (no repeated edge, vertices may repeat). Rejected: it
  catastrophically overcounts branches — four branches of five roads meeting at one junction would score 15
  instead of 10 — and the rulebook counts "the single longest branch" (S2 Almanac p.9). Alternative
  considered: longest **simple path only**. Rejected: it undercounts a closed loop, contradicting S5's
  six-roads-in-a-hexagon example, since a 6-cycle contains no 6-edge simple path, only a 5-edge one.
  PRD-v1 FR-13.10's phrase "exhaustive simple-path search" is read as a *method* requirement (exhaustive,
  not greedy) and is satisfied; the cycle case is enumerated by the same exhaustive search.
* *Does an opponent's road break a road?* No. Only settlements and cities do (S5 "not interrupted by game
  pieces belonging to other players"; every worked example uses a settlement).
* *Does a road that meets an opponent's road at a vertex continue?* Yes. Roads are pieces on edges; the only
  blocking pieces are buildings on vertices.
* *Is the "at least 5" threshold evaluated on the player's longest path only, or on every branch?* Only on
  the longest continuous road (rule 4).

---

### 4.11 Largest Army

**Rule as implemented.**

1. The Largest Army special card is worth **2 victory points**.
2. A player's knight count `K(p)` is the number of **face-up `knight` development cards that
   player has played**, i.e. the number of knights they have played over the whole game. Unplayed knights in
   hand never count, and a knight bought this turn (which cannot be played this turn) never counts.
3. A player **meets the requirements** iff `K(p) >= 3`.
4. **Award computation** runs after every state transition, by the same algorithm as Longest Road
   (§4.10 rule 6) applied to `K`$: the greatest `K` among players with `K >= 3`; a single
   maximum holder takes the card; a tie leaves it with the incumbent if the incumbent is among the tied
   players, otherwise unheld.
5. Because played knights can never leave play, the "unheld after a tie" branch of rule 4 is **not reachable**
   for Largest Army: once a player holds the card they have at least 3 played knights, and any player who
   overtakes them must have strictly more. The branch is nevertheless implemented, identically to Longest
   Road, so that the two awards share one tested code path.

**Citation.**
Threshold and value: S1 p.5 "LARGEST ARMY — The first player to have 3 Knight cards in play receives this
tile. If another player has more Knight cards in play, they immediately receive this tile… The Largest Army
tile is worth 2 VPs"; S2 p.5 "Largest Army — The first player to play 3 Knight cards gets this card. Another
player who plays more Knight cards takes this card"; S3 Almanac p.12 "Largest Army" — "If you are the first
player to play 3 knight cards, you receive this special card, which is worth 2 victory points… If another
player plays more knight cards than you have, they immediately take the special card. The 2 victory points
likewise count for the new owner." Unplayed knights do not count: S5 "Do my unplayed Knight Cards also count
for claiming the Largest Army? No. A Knight Card that hasn't been revealed is like a lottery slip where you
marked six winning numbers but then didn't submit it to enter the drawing: it's useless!" Transfer is
compulsory: S5 "Do I have to hand over the Largest Army card and subtract the 2 victory points from my score
if another player has more Knight Cards? Yes." Automatic transfer: S4 §3.0.4.

**Ambiguity resolved.**

* *Tie for Largest Army.* **Chosen: the incumbent keeps the card** (rule 4, mirroring §4.10 and S5's Longest
  Road tie answer). Alternative considered: a tie could be read as leaving the card unheld; rejected because
  the rulebook's transfer trigger is "more Knight cards", which is strictly greater, so a tie never
  transfers and the card cannot leave the incumbent by that route. Note this differs from Longest Road, where
  a score can *fall*; a knight count can only *rise*.
* *Playing a knight to reach 10 victory points outside the normal window.* A player may not play a knight and
  immediately win at the moment of buying a card: S4 §3.0.5 — "Players are not allowed to immediately play a
  knight card, even if this means that the player would get the largest army and win the game. The player
  must wait until their next turn before playing the knight card."
* *Does a knight bought this turn count if revealed?* It cannot be played at all this turn (§4.8 rule 2), so
  the question does not arise.

---

### 4.12 Trading

#### 4.12.1 Maritime trade (with the bank)

**Rule as implemented.**

1. `maritime_trade{give_resource, give_count, want_resource}` exchanges exactly `give_count`
   cards of one resource type for exactly **1** card of another resource type.
2. **`give_resource != want_resource`.** Trading like resources is forbidden even at 4:1.
3. **The ratio** is the best ratio available to the player for `give_resource`: `4` by default;
   `3` if the player has a settlement or city on a vertex of a generic 3:1 port edge; `2` if the
   player has a settlement or city on a vertex of a 2:1 port edge **whose resource is
   `give_resource`**. The ratio is the minimum of the applicable terms. A 2:1 port never improves any
   resource other than the one printed on it, not even to 3:1.
4. Maritime trade is available only on the current player's turn, and only in the action phase (i.e., after
   the roll is fully resolved).
5. The bank must hold the requested resource (A-7).
6. No random draw is involved. The exchange is one atomic event.

**Citation.**
4:1 general rate: S1 p.7 "GENERAL TRADE WITH THE SUPPLY (4:1) — put 4 of the same resource cards into the
supply and take 1 card of a different resource from the supply"; S2 p.4 "Maritime Trade" — "The 4:1 trade is
always possible, even if you do not have a settlement on a harbor." 3:1 and 2:1 port rates: S1 p.7 "PORT
TRADE WITH THE SUPPLY (3:1 OR 2:1)"; S2 Almanac p.9 "Maritime Trade" — "Generic Harbor (3:1)… Special
Harbor (2:1): There is only 1 special harbor for each type of resource… A special harbor does not permit you
to trade any other resource type at a more favorable rate (not even 3:1)!" Port ownership: S2 Almanac p.8
"Harbors" — "In order to control a harbor, you must build a settlement on a coastal intersection which
borders the harbor"; S5 "May I trade via a harbor where an opponent has a settlement? No." Same resource
forbidden: S1 p.7 — "you may not give away cards in any way, which includes trading matching resource cards
(for example, trying to trade 3 ore for 1 ore is not allowed)"; S2 Almanac p.14 "Trade" — "You may not trade
like resources (e.g., 2 wool for 1 wool)." Harbour usable the turn it is built: S4 §3.0.10 — "A harbor may
be used the same turn that a player builds on it"; S5 "May I trade via a harbor right after building it? …
In a game without separation between trade and build phase: yes." Not on another player's turn: S2 Almanac
p.14 "Trade" — "You may not trade with the bank during another player's turn."

#### 4.12.2 Player-to-player trade

**Rule as implemented.**

1. The protocol is structured and closed: `offer_trade{give: {resource: count}, want: {resource:
   count}}`, then one `respond_trade{accept|decline}` per eligible responder, then either partner
   selection by the offerer or cancellation. There is **no free-text negotiation** in any LBGB run
   (`ARCHITECTURE.md` §3; PRD-v1 FR-14.9).
2. **Only the current player may open an offer** (PRD-v1 FR-14.3). A player who is not the current player
   cannot propose, accept, or execute a trade with another non-current player.
3. **Validation before broadcast.** An offer is rejected before any request is opened if:
   * it names resources the offerer does not hold (for each resource `r`,
     `give[r] <= hand[offerer][r]`) — rejected `OFFER_NOT_BACKED`;
   * it is empty, i.e. gives nothing or wants nothing — rejected `BAD_PARAMS`;
   * it gives and wants nothing but the same resource type in the same quantity — rejected
     `SAME_RESOURCE_TRADE` (a player may not give away cards);
   * another offer is already open — rejected `TRADE_ALREADY_OPEN`.
4. **Responders.** Every player other than the offerer who holds **at least one resource card** receives a
   `respond_trade` request (PRD-v1 FR-14.4). Responders answer concurrently (§4.4 rule 3). An
   `accept` from a player who does not hold the full `want` set is validated at resolution and
   rejected with `INSUFFICIENT_RESOURCES`; such a responder is offered the request but can never
   complete the trade.
5. **Resolution.** When all responders have answered:
   * zero accepts → the offer closes, no cards move, the offerer may open another offer;
   * one accept → the trade executes;
   * two or more accepts → the **offerer chooses the partner** (PRD-v1 FR-14.5); the engine never picks.
     Until the offerer chooses, the offer stays open and the accepting players have no further decision.
6. **Cancellation.** The offerer may `cancel_trade` at any time while the offer is open and before a
   partner has been selected; the open response requests are withdrawn and no cards move (PRD-v1 FR-14.6).
7. **Execution.** A completed trade transfers both sides of the exchange **atomically in a single event**,
   with no intermediate legal state (PRD-v1 FR-14.8). The transferred quantities are public (they were
   announced); hand contents remain private.
8. **A player may not give away cards.** Every trade must exchange at least one card for at least one card.
9. Only the current player may trade with other players; two non-current players may never exchange cards.

**Citation.**
The turn restriction: S1 p.7 "TRADE" — "You may trade freely with other players and the supply to get the
resources you need to build. During your turn, other players may only trade with you, not with each other or
with the supply"; S2 Almanac p.11 "Resource Trade" — "The other players may not trade among themselves, only
with the player whose turn it is"; S2 Almanac p.14 "Trade" — "If you decide not to trade during your turn,
no one can trade." Offer-and-response structure: S1 p.7 — "To trade with other players, announce which
resource(s) you want and which resource(s) you are willing to trade. Other players may accept your proposal,
make counteroffers, or make their own proposals." No gifts: S1 p.7 — "you may not give away cards in any
way"; S2 Almanac p.7 "Domestic Trade" — "you cannot give away cards, or trade matching resources"; S5 "May I
give away resources or buy services with them, for example, to avoid being bothered by the robber? No. On
Catan, a trade always involves giving and taking resources." No secret trades: S5 "May I secretly trade with
an opponent, so that the other players won't know what we traded? No." No triangular trade: S5 "Is a
'triangular trade' permitted? … No."

**Ambiguity resolved.**

* *Maritime trade when the bank lacks the resource — **NO PRIMARY SOURCE**.* See **A-7** (§5.7).
* *May a player trade with the bank for the same resource type?* **Chosen: forbidden at every ratio.** S1
  requires "1 card of a different resource"; S5 states the special port means "you have to pay two in order
  to receive one different resource". A 1:1 same-resource exchange is never legal.
* *Must an offer be backed by cards the offerer actually holds?* **NO PRIMARY SOURCE.** **Chosen: yes,
  validated before broadcast** (PRD-v1 FR-14.7). Alternative considered: broadcast the offer and reject at
  resolution. Rejected: it sends other players a decision they can act on but which can never complete,
  wasting decision budget and creating a rejection path indistinguishable from a model error.
* *Do responders see each other's answers?* **Chosen: no** (§4.4 rule 3). Alternative considered:
  sequential response in seat order with public answers. Rejected: it lets a later responder free-ride on an
  earlier acceptance, which is not the physical game and would make the record depend on arrival order.
* *May a non-current player initiate an offer?* No (item 2). S4 §3.0.7 permits an inactive player to *talk*
  about a future trade in a tournament setting, but that is unstructured negotiation, which
  `ARCHITECTURE.md` §3 excludes from LBGB entirely. Alternative considered: model it as a
  non-binding proposal action. Rejected as out of scope for v1.
* *Are counter-offers supported?* **Not in v1.** A player may decline and, when it is their own turn, open
  their own offer. PRD-v1 Q7 leaves the question open; this document pins the v1 answer as decline-only
  (`interaction_protocol: decline_only`, PRD-v1 §10.2). Adding counter-offers is a
  `rules_version`-bumping change.
* *Who picks among multiple acceptors — **NO PRIMARY SOURCE**?* The rulebook says only "Other players may
  accept your proposal". **Chosen: the offerer picks** (PRD-v1 FR-14.5). Alternative considered: the engine
  picks the lowest seat. Rejected: it removes a decision from the offerer and makes the engine an agent.

---

### 4.13 Victory and termination

**Rule as implemented.**

1. **Victory points.** Settlement 1, city 2, `victory_point` development card 1, Longest Road card 2,
   Largest Army card 2.
2. A player's **true total** is the sum over all five terms, counting every `victory_point` card in
   their hand, revealed or not.
3. A player's **public total** (what other players can compute) excludes all unrevealed
   `victory_point` cards. Revealing them is not an action; it happens only as a consequence of
   winning.
4. **Win condition.** The first player to reach **10 or more** victory points **during their own turn** wins.
5. **Win timing.** The condition is tested after **every** state transition and at **turn start**, applied to
   the player whose turn it is:
   * at the transition into a player's turn, before the roll: if that player's true total is 10 or more, the
     game ends immediately, that player wins, and no dice are rolled;
   * after every action within that player's turn.
6. **Off-turn points do not win immediately.** If a player's true total reaches 10 or more while another
   player's turn is in progress — which can only happen if the Longest Road card transfers to them when an
   opponent's settlement breaks the incumbent's road (§4.10 rule 7) — the game continues and that player
   wins at the start of their own next turn.
7. **No claim action exists.** The engine detects the win; it does not require and does not accept a
   `claim_victory` action. A player who has reached 10 points is the winner whether or not they
   noticed.
8. **Termination.** On a win, the engine enters the terminal state immediately. No further state transition
   is possible: any action after termination is rejected with `GAME_OVER` (PRD-v1 FR-15.5). There is no
   "finish the round" behaviour.
9. `is_terminal` and `outcome` are pure and perform no random draw (PRD-v1 FR-15.3).
10. The **outcome** reports each player's true final victory points, the winner, the number of turns, and the
    total number of actions attempted (PRD-v1 FR-15.4).
11. All players begin with 2 victory points (their two setup settlements), so 8 further points are needed to
    win.

**Citation.**
Objective: S1 p.4 "OBJECTIVE — The first player to reach 10 victory points (VPs) on their turn wins"; S1
p.10 "WINNING THE GAME — If you have 10 or more VPs at any point during your turn, the game ends immediately
and you are the winner! Turn over any number of Victory Point cards, including ones built this turn, to show
that you have reached 10 VPs." S2 p.5 "Ending the Game" — "If you have 10 or more victory points during your
turn, the game ends and you are the winner! If you reach 10 points when it is not your turn, the game
continues until any player (including you) has 10 points on his turn." S2 Almanac p.7 "Ending the Game" —
"You can only win during your turn. If somehow you find you have 10 victory points during another player's
turn, you must wait until your next turn to claim victory." VP values: S2 Almanac p.14 "Victory Points" —
"1 settlement = 1 VP; 1 city = 2 VPs; Longest Road special card = 2 VPs; Largest Army special card = 2 VPs;
Victory point (VP) card = 1 VP… Since each player begins with 2 settlements, each player begins the game with
2 victory points." No roll needed when already at 10: S5 "If upon starting my turn I already have the number
of victory points required for a win, do I still have to roll the dice? No." No claim required: S5 "What if
someone has reached the required number of victory points for a win but is unaware of it? Did this player win
anyway? Yes. The game ends as soon as a player has reached the required number of victory points on his
turn." VP card revealed on purchase when it is the tenth: S4 §3.0.5 — "If a player buys a development card
with a victory point on it, they may immediately reveal it if it is their tenth victory point to win the
game." No continued scoring: S5 "May I continue scoring points after having reached the number of victory
points required for a win? … You have won as soon as you have reached the required number of victory points
on your turn – and then the game is over." Only on your own turn: S5 "Can I win during the special building
phase? No. You can only win during your own turn."

**Ambiguity resolved.** The win-timing question is **A-3** (§5.3). Additional pins:

* *Is there an explicit claim action?* **Chosen: no.** Alternative considered: require the winning player to
  emit `claim_victory`, with the engine terminating only on that action. Rejected: S5 states the game
  ends as soon as the points are reached and that an unaware player still wins; S4 §3.0.15's waiting rule
  ("If a player does not notice that they have 10 points and fails to claim victory in their turn, the player
  must wait until their next turn before winning the game") is a dispute-recovery rule for tabletop play, not
  a legal move. A claim action would also let a model with 10 points keep playing, which the rules forbid.
* *Does the engine terminate mid-turn the instant a VP card is bought?* Yes: the purchase is a state
  transition during the buyer's turn and the condition is tested after every transition. This matches S4
  §3.0.5 and S1 p.10's "at any point during your turn".
* *Are unrevealed `victory_point` cards counted in the winner's total?* Yes (item 2) — that is exactly
  the mechanism by which purchasing the tenth point wins.
* *PRD alignment.* FR-15.1 (values), FR-15.2 (timing pinned here), FR-15.3 (purity), FR-15.4 (outcome
  contents) and FR-15.5 (`GAME_OVER`) are satisfied with no divergence.

---

## 5. The eight ambiguities, in full

Each entry states the **Chosen interpretation**, the **Alternative(s) considered**, and the **Reason**. All
eight are also listed in the summary table in §5.9.

### 5.1 A-1 — Board number-token placement procedure

*PRD-v1 §11 item 1. The rulebook admits this ambiguity twice over.*

**Chosen interpretation.**

1. `spiral` — the tokens are placed on the 18 non-desert hexes in the fixed sequence
   `T = (5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11)` along a counterclockwise spiral
   walk that starts at a corner hex of the outer ring and works inward, ring by ring, to the centre, skipping
   the desert hex wherever it lies. The starting corner is chosen by recorded draw D2.
2. `random` — the same 18 hexes receive `T` in an order produced by recorded draw D3.
3. In both modes the four 6/8 tokens MUST NOT end up on mutually adjacent hexes; if they do, a documented
   deterministic repair swap is applied (no draw). The algorithm is §4.2 item 7.
4. The v1 default for benchmark runs is `spiral_no_adjacent_red` (PRD-v1 §10.2): mode 1 plus the check.

**Alternative considered.**

* *The physical tokens' letter → number mapping.* The official tokens carry letters A…R on their backs and the
  rule is stated as "place the number discs in A-B-C order". If the mapping were known, "place in
  alphabetical order" would be a complete procedure. **It could not be established from any retrieved
  primary source** — no retrieved rulebook, FAQ entry or tournament rule documents which number is printed on
  the front of token "A". Substituting a remembered mapping would be exactly the "rule implemented from
  memory" failure PRD-v1 §2 exists to prevent, so it was rejected in favour of an explicitly project-owned
  sequence.
* *Rejected partly on evidence:* with an **ascending** numeric sequence (2, 3, 3, 4, … 12) along the same
  spiral, an exhaustive check places 6 and 8 on adjacent hexes in **all 114** configurations (6 starting
  corners × 19 desert positions), with 2–3 adjacent red pairs each time. A descending sequence behaves
  identically. Sequence `T` was selected because it produces **zero** adjacent red pairs in all 114
  configurations, i.e. the official constraint holds without the repair step ever firing on the standard
  board.

**Reason.** The rulebook fixes the *procedure* but not the *mapping*; the project must own the mapping
explicitly and verifiably rather than guess it. Pinning one sequence makes fixed boards reproducible, makes
the "no adjacent red numbers" constraint checkable, and gives M3 an exact test: for every fixed board and
every starting corner, no two of the four 6/8 tokens are adjacent, and the walk order is contiguous (every
consecutive pair of hexes is adjacent).

**Determinism.** Draw D2 (`choice`, `board_number_corner`) or draw D3 (`shuffle`,
`board_number_shuffle`). The repair consumes no draw. A fixed board file may declare the corner and the
full token layout, in which case no draw is taken.

---

### 5.2 A-2 — Development-card timing relative to the roll, per card type

*PRD-v1 §11 item 2.*

**Chosen interpretation.** There are exactly **three windows**, and the window is the same for every card
type; what differs per type is the effect, not the timing.

| Window | What is legal |
|---|---|
| **W1 — start of the production phase, before the roll** | Play **one** development card of any type the player holds and may legally play: `knight`, `year_of_plenty`, `monopoly` or `road_building`. Nothing else may happen before the roll — not trading, not building, not buying. |
| **W2 — action phase, after the roll is fully resolved** | Play **one** development card of any of those four types, but only if none was played in W1. |
| **W3 — the winning moment** | Reveal **any number** of `victory_point` cards, including ones bought this turn. This is not a "play" and does not interact with the one-card limit. |

Cross-cutting rules:

* A card bought this turn MUST NOT be played this turn, except a `victory_point` card, which is not
  played but revealed at the winning moment.
* At most one card per turn from {knight, year_of_plenty, monopoly, road_building}.
* "After the roll is fully resolved" means: on a non-7, production has been distributed; on a 7, the discard
  phase has completed, the robber has moved, and the steal has been resolved.
* `road_building`'s two placements are part of playing the card: they must be completed before any
  other action begins (S4 §3.0.8).
* `knight` moves the robber and steals but never opens the discard phase.

**Alternative considered.**

* *"Any time during the turn"* — the 5th-edition phrasing "You can play the card at any time, even before you
  roll the dice" (S2 Almanac p.7) read literally would permit playing a card *between* the dice landing and
  production being distributed, or *between* the discard phase and the robber move. **Rejected**: S4 §3.0.1
  and §3.0.2 close both windows — "No other actions may occur prior to the rolling of the dice" and the roll
  "must be resolved … before any other actions may be taken".
* *A second card after the roll if one was played before it* — **rejected**: S5 is explicit ("if you have
  played this card before rolling the dice, you are not allowed to play another one afterwards"); the
  one-card limit is per turn, not per window.
* *Interleaving `road_building`'s two roads with other actions* — **rejected**: S4 §3.0.8 defines when
  a road-building action is complete and permits re-positioning only inside it.
* *Allowing `monopoly` or `year_of_plenty` only in the action phase* — a common misreading, since
  the first phase is named after production. **Rejected**: S1 p.9 and S4 §3.0.1 both say *any* development
  card.

**Reason.** The three-window model is what the current edition and the tournament clarifications jointly
describe; it removes all timing discretion from the engine; and it makes the "development card that is
unplayable until the turn after purchase" requirement (PRD-v1 §2.1) a stateless function of the turn on which
the card was bought.

---

### 5.3 A-3 — Win condition timing: victory only on the player's own turn

*PRD-v1 §11 item 3.*

**Chosen interpretation.** A player wins at the **first moment during their own turn** at which their true
victory-point total is **10 or more**. The condition is evaluated after every state transition of that turn
and again at the instant the turn begins, before the roll. Reaching 10 or more during another player's turn
does **not** end the game; such a player wins at the start of their own next turn, without rolling and
without any claim action. The exact rule is §4.13.

**Alternative considered.**

* *"Reaching 10 wins immediately, whenever it happens."* **Rejected**: S2 Almanac p.7 "Ending the Game" —
  "You can only win during your turn. If somehow you find you have 10 victory points during another player's
  turn, you must wait until your next turn to claim victory"; S2 p.5 restates it. This reading is also
  reachable in practice under this ruleset: when an opponent's settlement breaks the incumbent's road, the
  Longest Road card (2 VP) can move to a third player during the opponent's turn (§4.10 rule 7, S4 §3.0.4),
  so off-turn point acquisition is a real event, not a theoretical one.
* *"Require a claim action."* **Rejected**: S5 — "Yes. The game ends as soon as a player has reached the
  required number of victory points on his turn. If he's unaware of it, you should tell him, because you
  can't take an already gained victory away from him." An engine that waits for a claim action would drift
  from the rules whenever a model fails to claim.
* *"End the game at the end of the round rather than immediately."* **Rejected**: S1 p.10 — "the game ends
  immediately"; and S4 §3.0.15's "wait until their next turn" is a dispute-recovery concession for a tabletop
  player who failed to notice, not a design for an engine that never fails to notice.

**Reason.** The reading is supported by both rulebooks, the official FAQ and the tournament rules; it is
deterministic; it removes a whole class of operator judgement; and it makes the terminal transition a pure
function of state.

**Determinism.** No random draw. `is_terminal` and `outcome` are pure (PRD-v1 FR-15.3).

---

### 5.4 A-4 — Whether Year of Plenty permits two of the same resource

*PRD-v1 §11 item 4.*

**Chosen interpretation.** **Yes.** `year_of_plenty` takes exactly 2 resource cards from the bank, and
the two may be the same resource or two different resources. The take is limited by bank contents: a player
may not take more of a resource than the bank holds, and may not take fewer than 2 cards unless the bank
cannot supply 2 more of anything they name. The two cards are taken in one atomic event and may be spent in
the same turn.

**Alternative considered.** *"Two different resources only."* This is a persistent house rule and appears in
some regional summaries. **Rejected on a direct citation**: the rulebook prints the answer on the card and in
the rules text — S1 p.9: "take any 2 resource cards from the supply. Add them to your hand. They may be 2 of
the same resource or 2 different resources"; S2 Almanac p.10 "Progress Cards" carries the same sentence on
the card face: "Take any 2 resources from the bank. Add them to your hand. They can be 2 of the same resource
or 2 different resources."

**Reason.** This is the one entry among the eight where the primary source is not merely adequate but
explicit. It is recorded here so that no implementer re-derives it, and so that the residual judgement — what
happens when the bank is short — is pinned rather than left to code. **The residual bank-shortfall question
has no primary source**; the chosen answer (never take more than the bank holds; the effect does not force
the bank negative) is what preserves resource conservation (PRD-v1 FR-6.9).

---

### 5.5 A-5 — Bank exhaustion during production

*PRD-v1 §11 item 5.*

**Chosen interpretation.** Distribution is decided **per resource, independently, after the full demand for
that resource has been computed**:

* `bank[r] >= demand[r]` → everyone gets exactly what they earned.
* `bank[r] < demand[r]` and **exactly one** player earns a positive amount of `r` → that player
  receives all `bank[r]` cards; the rest of their entitlement is lost.
* `bank[r] < demand[r]` and **two or more** players earn a positive amount of `r` → **no one
  receives any `r`**; the cards stay in the bank.
* Other resources are unaffected in every case.

**Alternative considered.**

* *Pro-rata distribution* (everyone receives `floor(earned * bank / demand)`). **Rejected**: no source
  supports it, and it creates a partial-credit rule the players cannot verify at the table.
* *Seat-order priority* (the current player and then ascending seats take what they can). **Rejected**: S5 —
  "If the number of cards of this type is indeed insufficient, then none of the players receives this
  resource on this turn."
* *Sequential application in seat order with the single-player exception evaluated on who is left.*
  **Rejected**: it produces order-dependent outcomes, violating `ARCHITECTURE.md` §6.
* *The PRD's FR-10.4 as written* ("a partial distribution MUST be deterministic"). **Rejected as a general
  rule** — partial distribution is the *exception*, not the rule. See §6.2 (D-2).

**Reason.** The rulebook states both cases and the exception almost verbatim, the 5th-edition Almanac expands
it, and the official FAQ answers both branches. It is fully deterministic and preserves resource
conservation.

**Determinism.** No random draw. The demand table is computed once from the roll and the board, then applied.

---

### 5.6 A-6 — Road Building when fewer than two roads remain in supply

*PRD-v1 §11 item 6.*

**Chosen interpretation.**

1. `road_building` may be played whenever the player has (a) at least one road remaining in their
   personal supply and (b) at least one legal road edge available to them (§4.7). Both conditions are checked
   at the moment of the play.
2. The card opens a `road_building` sub-phase with up to two sequential `place_free_road`
   decisions. The player places free roads one at a time, stopping when any of the following happens:
   * two roads have been placed;
   * the player's road supply is exhausted;
   * the player has no legal road edge left.
3. Roads that cannot be placed are **lost**. The card is still consumed and still counts as this turn's
   development card.
4. If the first free placement is legal but the second is not — for example, the first road dead-ends — only
   one road is placed.
5. If neither condition of item 1 holds, `play_dev_card{road_building}` is not offered, and if
   attempted is rejected with `CARD_NOT_PLAYABLE`. The card stays in hand.
6. Placement legality is evaluated against the board **as it is after the previous free placement**, so a
   free road may open the edge for the next one.
7. Each placement is final once the next action begins (S4 §3.0.8). There is no undo and no repositioning in
   this engine; the record is event-sourced and a placement is an event.

**Alternative considered.**

* *"The card is unplayable unless two roads can both be placed."* **Rejected** for three reasons: it is
  stated nowhere; it makes the card a dead card in the endgame, where road supply is exhausted precisely
  because the player has been building; and the rulebook's own piece-supply rule is a *gate on building*
  ("To continue building more settlements, you must first upgrade one to a city", S1 p.7) rather than a
  prohibition on effects.
* *"The player may place a road beyond their supply by borrowing another player's pieces."* **Rejected**:
  pieces belong to their owner and are never transferred (S2 Almanac p.6 "Build (Building)": "Each player has
  a supply of 15 roads, 5 settlements, and 4 cities").
* *"Place as many as possible, including zero, and keep the card."* **Rejected**: it allows a loop of
  zero-effect plays and contradicts "build 2 roads at no cost" (S1 p.9).
* *"Substitute other builds for unplaced roads."* **Rejected**: the card is specific.

**Reason.** **NO PRIMARY SOURCE — this pin is a project decision.** No retrieved rulebook, FAQ entry or
tournament rule addresses the shortfall. The chosen rule is the minimal reading of the card text ("build
2 roads at no cost" — free of *resource* cost, not free of *piece* limits), it keeps the piece-conservation
invariant intact, it never dead-locks a player holding the card with a full board, and it is testable
(PRD-v1 FR-13.5 requires exactly this to be pinned and tested).

**Determinism.** No random draw.

---

### 5.7 A-7 — Trading with the bank below the required port ratio when the bank lacks the resource

*PRD-v1 §11 item 7.*

**Chosen interpretation.** **The ratio is never reduced, and the trade is never downgraded.**
`maritime_trade` requires the bank to hold at least one card of `want_resource`. If it does not,
the action is not offered and, if attempted, is rejected with `BANK_LACKS_RESOURCE`. The player pays
exactly the applicable ratio (4, 3 or 2) of one resource type and receives exactly 1 card of a **different**
type.

Corollaries: no partial exchange (paying 3 of a 4:1 price for 1 card is impossible); no credit against a
future replenishment; no substitution of the wanted resource.

**Alternative considered.**

* *"Pay what you have and take what remains."* **Rejected**: the rulebook's exchange is fixed — "put 4 of the
  same resource cards into the supply and **take 1 card** of a different resource from the supply" (S1 p.7).
  There is no shortfall clause in any trade paragraph, unlike production, where the rulebook went out of its
  way to write one (§4.6). The absence of a shortfall clause in a rulebook that writes one wherever it is
  needed is itself evidence.
* *"Reduce the ratio when the bank is short"* (paying 3 for the last card when the 4:1 price applies).
  **Rejected**: no source, and it creates a bank-price mechanism the players cannot verify.
* *"Allow the trade and let the bank go negative."* **Rejected**: it violates resource conservation, a
  declared invariant (PRD-v1 FR-6.9).
* *"Allow the player to take the resource from another player's hand."* **Rejected**: the bank is the only
  counterparty for maritime trade; taking from a hand is the robber's or a monopoly's mechanism.

**Reason.** **NO PRIMARY SOURCE — this pin is a project decision**, recorded here rather than left to code
per `ARCHITECTURE.md` §7.9. It follows the rulebook's text ("take 1 card … from the supply"), matches
the physical game (a card that is not in the bank cannot be taken), keeps the invariant intact, and turns a
silent impossibility into an explicit, declared rejection code (PRD-v1 FR-6.8, SC-13).

**Determinism.** No random draw.

---

### 5.8 A-8 — Award vacating on a tie, and re-acquisition afterwards

*PRD-v1 §11 item 8.*

**Chosen interpretation.** One shared algorithm, evaluated after **every** state transition, applied
independently to each award. For award `A` with a per-player score `s(p)` (road length for Longest
Road; played-knight count for Largest Army) and a threshold `t` (5; 3):

1. `M = max_p s(p)`; `C = { p : s(p) = M }`.
2. If `M < t` or `C` is empty → the card is **unheld** and returns to the board.
3. Else if `|C| = 1` → that player holds the card, transferring it from anyone else immediately.
4. Else (`|C| >= 2`, a tie) → the **incumbent keeps the card** if the incumbent is in `C`;
   otherwise the card is **unheld**.
5. **Re-acquisition is automatic.** There is no memory of past holders, no priority, no waiting period. The
   moment rules 1–4 yield a single holder, that player has the card and its 2 victory points. A player who
   lost the card can take it straight back by rebuilding.

Per-award notes:

* **Longest Road** can go unheld (rule 4, second branch) — for example, the incumbent's road is broken below 5
  while two other players tie at 6.
* **Largest Army** cannot go unheld once a player has 3 played knights: played knights never leave play, so
  the incumbent is always in `C` when `M >= 3`. The branch is implemented anyway so both awards
  share one code path.
* A tie for the *maximum* never takes the card away from a holder who is part of the tie.

**Citation.** S2 Almanac p.9 "Longest Road" — "Special Case: If your longest road is broken and you are tied
for longest road, you still keep the 'Longest Road' card. However, if you no longer have the longest road but
two or more players tie for the new longest road, set the 'Longest Road' card aside. Do the same if no one has
a 5+ segment road. The 'Longest Road' card comes into play again when only 1 player has the longest road (of
at least 5 road pieces)." S5 "What happens if a player builds a continuous road that has the same length as
the road belonging to the owner of the Longest Road card? The card stays with its current owner." S5 "What
happens if the Longest Road is interrupted? … If the player who up to this point had the Longest Road still
meets the requirements for the Longest Road (either alone or together with another player), he keeps the
card. If another player now meets the requirements for the Longest Road, he receives the card. If none of the
players - or more than one player - meets the requirements for the Longest Road, none of the players receives
the card." S1 p.5 — "If, when a player's route is broken, they no longer meet the requirements for the
Longest Route, the tile is returned to the supply. It remains in the supply until a single player has the
longest continuous route of at least 5 roads. That player immediately receives the bonus tile and the 2 VPs."
S4 §3.0.4 — automatic transfer.

**Alternative considered.**

* *"A tie always vacates."* Some digital implementations drop the award whenever the maximum is shared.
  **Rejected**: the Almanac and the FAQ both say the incumbent keeps it while tied.
* *"The award always stays with the incumbent until strictly overtaken, even below the threshold."*
  **Rejected**: the Almanac is explicit that below 5 — or with a shared new maximum and the former holder no
  longer among the leaders — the card goes back to the board.
* *"Re-acquisition requires a fresh claim or a full turn."* **Rejected**: S1 p.5 — "That player immediately
  receives the bonus tile and the 2 VPs"; S4 §3.0.4 — automatic.
* *"First to have held it wins ties forever."* **Rejected**: no source, and it would make the award
  history-dependent, conflicting with `ARCHITECTURE.md` §5.5 and with PRD-v1 §2.1's requirement that
  the awards be derived state recomputed on every transition.

**Reason.** The rulebooks, the Almanac and the official FAQ agree on all three cases, so this ambiguity is
resolved by citation rather than by choice. What the project adds is a single algorithm, shared by both
awards, applied identically after every transition — which is what makes the awards a pure function of state
and therefore replayable.

**Determinism.** No random draw. Both awards must be recomputed by an exhaustive road search (§4.10) with no
heuristic (PRD-v1 FR-13.10; SC-11 requires 100% coverage of `longest_road.py`).

---

### 5.9 Summary table of the eight ambiguities

| ID | Ambiguity (PRD-v1 §11 wording) | Chosen interpretation, in one line | Authority | Section |
|---|---|---|---|---|
| **A-1** | Board number-token placement procedure | Tokens are placed in the fixed sequence `T = (5,2,6,3,8,10,9,12,11,4,8,10,9,4,5,6,3,11)` along a counterclockwise inward spiral from a corner hex, skipping the desert, with a mandatory no-adjacent-6/8 check and a deterministic repair. | S1 p.11; S2 Almanac p.12; S4 §2.0.1 for the name; **the sequence is a project constant (no primary source for the letter→number mapping)** | §4.2, §5.1 |
| **A-2** | Development-card timing relative to the roll, per card type | Three windows — before the roll, in the action phase after the roll is fully resolved, and the winning reveal — identical for all four playable types; at most one per turn; VP cards are revealed, not played. | S1 p.9; S2 Almanac p.7; S4 §3.0.1, §3.0.2, §3.0.8; S5 | §4.8, §5.2 |
| **A-3** | Win condition timing | A player wins at the first moment their true VP total reaches 10 during **their own** turn, including at turn start before the roll; off-turn points wait for their next turn; no claim action. | S1 p.4/p.10; S2 p.5 and Almanac p.7; S4 §3.0.15; S5 | §4.13, §5.3 |
| **A-4** | Year of Plenty duplicates | Two of the same resource, or two different — the rulebook answers this explicitly; the only residual pin is that the take is limited by bank contents. | S1 p.9; S2 Almanac p.10; **bank-limit residual: no primary source** | §4.8, §5.4 |
| **A-5** | Bank exhaustion during production | Per resource: full payment if the bank suffices; all-or-nothing if two or more players are affected; if exactly one player is affected, that player takes everything left and loses the rest. | S1 p.6; S2 Almanac p.10; S4 §3.0.11; S5 | §4.6, §5.5 |
| **A-6** | Road Building with fewer than two roads in supply | The card is playable if at least one road is in supply and one legal edge exists; place free roads one at a time up to 2, stopping at supply or legality; unplaced roads are lost; otherwise the card is not playable. | **No primary source** — project decision (PRD-v1 FR-13.5 requires it to be pinned) | §4.8, §5.6 |
| **A-7** | Trading with the bank below the port ratio when the bank lacks the resource | The ratio is never reduced: maritime trade is unavailable, and rejected with `BANK_LACKS_RESOURCE`, if the bank holds none of the requested resource. | **No primary source** — project decision, grounded in S1 p.7 ("take 1 card … from the supply") | §4.12.1, §5.7 |
| **A-8** | Award vacating on a tie, and re-acquisition | One algorithm: unheld below threshold; a sole maximum holder takes it; on a tie the incumbent keeps it if tied, otherwise unheld; re-acquisition is automatic on the next transition. | S1 p.5; S2 Almanac p.9; S4 §3.0.4; S5 (two FAQ entries) | §4.10, §4.11, §5.8 |

### 5.10 Additional interpretations pinned by this document

These are not among the eight, but they are pinned so that later cards do not have to re-derive them.

| # | Question | Pinned answer | Section | Primary source? |
|---|---|---|---|---|
| B-1 | First player selection in a benchmark run | From `RunConfig.first_player`, default seat 0; no draw | §4.3 | S5 (the procedure is optional) |
| B-2 | Do round-1 setup settlements grant resources? | No; only the second settlement, in the order seats 3, 2, 1, 0 | §4.3 | S1 p.11; S2 Almanac p.12 |
| B-3 | Setup endowment under bank shortage | Satisfied in placement order; shortfall lost | §4.3 | No |
| B-4 | Which coastal edges carry ports | Curated board data (nine edges; four 3:1, five 2:1) | §4.1, §4.12.1 | No (frame geometry, shown only as a diagram) |
| B-5 | Port *types* on the nine port edges | Recorded shuffle (draw D4) for random boards; declared for fixed boards | §4.1, §4.12.1 | S2 Almanac p.12 step 2 |
| B-6 | Discard composition visibility | Count public, identities private | §4.4 | S4 §3.0.12; S5 (hands only) |
| B-7 | Robber steal mandatory? | Yes, when at least one candidate exists | §4.9 | S4 §3.0.2 (indirect) |
| B-8 | Robber victim holding no cards | Legal to choose; nothing is taken | §4.9 | S2 Almanac p.8; S5 |
| B-9 | Do dev cards count toward the 7-card hand limit, or get stolen? | No to both | §4.9 | S1 p.9 |
| B-10 | Offer must be backed by held cards | Yes, validated before broadcast | §4.12.2 | No (PRD-v1 FR-14.7) |
| B-11 | Who picks among multiple acceptors | The offerer | §4.12.2 | No (PRD-v1 FR-14.5) |
| B-12 | Counter-offers | Not supported in v1 (`decline_only`) | §4.12.2 | S4 §3.0.7 (unstructured; excluded by architecture) |
| B-13 | Responders who cannot complete the trade | Still receive a request; their accept is rejected at resolution | §4.12.2 | No (PRD-v1 FR-14.4) |
| B-14 | Longest-road search shape | Maximum over simple paths **and** simple cycles, exhaustive | §4.10 | S5 (hexagon = 6 example) |
| B-15 | Road building and undo/repositioning | No undo; each placement is final once the next action begins | §5.6 | S4 §3.0.8 |
| B-16 | Deck exhausted | `buy_dev_card` unavailable; no reshuffle, ever | §4.8 | S1 p.9; S2 Almanac p.5 |
| B-17 | Played progress cards | Removed from the game; played knights stay face up forever | §4.8 | S5 |
| B-18 | Victory Point cards counted before reveal | Yes, in the owner's true total; excluded from everyone else's public total | §4.13 | S1 p.10; S5; PRD-v1 FR-13.8 |
| B-19 | `is_terminal` / `outcome` purity | No draws, no side effects | §4.13 | PRD-v1 FR-15.3 |
| B-20 | Same-resource bank or port trade | Forbidden at every ratio | §4.12.1 | S1 p.7; S5 |
| B-21 | Year of Plenty limited by bank contents | Yes; the effect never drives the bank negative | §4.8 | No |
| B-22 | Robber active from turn one | Yes; no grace period, no friendly robber | §4.9 | S4 §3.0.16 |

---

## 6. Appendix A — confirmation table

Every value PRD-v1 Appendix A lists, checked against the rulebook **as retrieved**, not copied from the PRD.
"Confirmed" means the retrieved rulebook states the value. "Derived" means the rulebook states something from
which the value follows but does not state the value itself. "Differs" would mean the rulebook states a
different value; **no row differs.**

| # | Item | PRD-v1 Appendix A value | Status | Citation |
|---|---|---|---|---|
| A1 | Terrain | 4 forest (wood), 4 pasture (sheep), 4 field (wheat), 3 hills (brick), 3 mountains (ore), 1 desert | **Confirmed** (note: S1 calls the pasture resource **wool**, not sheep) | S1 p.3 "COMPONENTS": "3x hills, 4x forests, 4x pastures, 4x fields, 3x mountains, 1x desert" |
| A2 | Number tokens | 2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12 (18 tokens, no 7) | **Confirmed** | S2 Almanac p.10 "Number Tokens" (18 tokens, one 2, one 12, no 7) plus "Resource Production" ("Each number appears twice—except for '2' and '12,' which only appear once") |
| A3 | Structure | 19 hexes, 54 vertices, 72 edges | **19 hexes confirmed; 54 and 72 are DERIVED, not stated by any retrieved rulebook** | S1 p.2/p.3 ("19 terrain hexes"); derivation in §4.1, asserted by the structural self-check of PRD-v1 SC-7 / FR-6.10 |
| A4 | Ports | 9 total: 4 × 3:1 generic, 5 × 2:1 specific (one per resource) | **Confirmed** (the 4/5 split follows from 9 harbour pieces and one 2:1 per resource) | S2 p.2 "Game Components": "9 harbor pieces"; S2 Almanac p.9 "Maritime Trade": "Generic Harbor (3:1) … Special Harbor (2:1): There is only 1 special harbor for each type of resource" |
| A5 | Bank | 19 of each resource | **Confirmed** | S1 p.3 "COMPONENTS": "95 resource cards … 19x brick, 19x wood, 19x wool, 19x wheat, 19x ore"; S4 §2.0.7; S6 p.3 |
| A6 | Player pieces | 15 roads, 5 settlements, 4 cities | **Confirmed** | S1 p.3 "COMPONENTS": "60 roads (15x each color), 20 settlements (5x each color), 16 cities (4x each color)"; S2 p.2 "Game Components"; S4 §2.0.6 |
| A7 | Road cost | 1 wood, 1 brick | **Confirmed** | S1 p.9 "BUILDING COSTS" panel and the Building Costs card; S6 "Straße — Baukosten: 1 x Lehm + 1 x Holz" |
| A8 | Settlement cost | 1 wood, 1 brick, 1 sheep, 1 wheat | **Confirmed** (S1's card is **wool**) | S1 p.9 "BUILDING COSTS"; S6 "Siedlung — Baukosten: 1 x Lehm + 1 x Holz + 1 x Wolle + 1 x Getreide" |
| A9 | City cost | 2 wheat, 3 ore | **Confirmed** | S1 p.9 "BUILDING COSTS"; S6 "Stadt — Baukosten: 2 x Getreide + 3 x Erz" |
| A10 | Development card cost | 1 sheep, 1 wheat, 1 ore | **Confirmed** (wool, wheat, ore) | S1 p.9 "BUILDING COSTS"; S6 "Entwicklungskarten — Kosten: 1 x Wolle + 1 x Getreide + 1 x Erz" |
| A11 | Development deck | 25 cards: 14 knight, 5 victory point, 2 road building, 2 year of plenty, 2 monopoly | **Confirmed** (the 6th edition prints "Invention" where older editions print "Year of Plenty": same card, same count) | S1 p.3 "COMPONENTS": "25 development cards … 5x Victory Point, 2x Monopoly, 2x Road Building, 2x Invention, 14x Knight"; S2 p.2 "Game Components": "25 development cards (14 knight cards, 6 progress cards, 5 victory point cards)"; S2 Almanac p.10 "Progress Cards": "There are 2 each of 3 varieties"; S4 §2.0.7; S6 p.3 |
| A12 | Victory points | settlement 1, city 2, VP card 1, Longest Road 2, Largest Army 2 | **Confirmed** | S2 Almanac p.14 "Victory Points"; S1 p.5 player-aid panel (Road 0 VP, Settlement 1 VP, City 2 VPs, Longest Route = 2 VPs, Largest Army = 2 VPs, Development Card ? VPs, Victory Point card 1 VP) |
| A13 | Largest Army threshold | 3 played knights | **Confirmed** | S1 p.5 — "The first player to have 3 Knight cards in play receives this tile"; S2 p.5 "Largest Army"; S5 (unplayed knights do not count) |
| A14 | Longest Road threshold | 5 continuous roads | **Confirmed** | S1 p.5 — "The first player to have 5 continuous roads in play receives this tile"; S2 Almanac p.9 "Longest Road" — "a continuous road of at least 5 individual road pieces"; S5 "What is the Longest Road?" |
| A15 | Win condition | 10 victory points | **Confirmed** | S1 p.4 "OBJECTIVE" — "The first player to reach 10 victory points (VPs) on their turn wins"; S2 p.5 "Ending the Game"; S2 Almanac p.14 "Victory Points" |
| A16 | Discard on a 7 | `floor(hand / 2)` from every player holding more than 7 cards | **Confirmed** | S1 p.6 "RESOLVE A 7": "Each player who has more than 7 resource cards must choose half (rounded down) of their resource cards and return them to the supply"; S2 Almanac p.11 "Rolling a '7' and Activating the Robber": "Any player with more than 7 resource cards (i.e., 8 or more) must choose and discard half of them … If you hold an odd number of cards, round down (e.g., if you have 9 resource cards, you discard 4)" |

### 6.1 Additional values confirmed while building this table

| Item | Value | Citation |
|---|---|---|
| Total resource cards in the box | 95 (5 × 19) | S1 p.3 "COMPONENTS" |
| Board edges that are coastal | 30 of 72 | derived, §4.1 |
| Robber's starting hex | the desert | S2 Almanac p.11 "Robber"; S1 p.11 step 4 |
| Development cards that are "progress cards" | 6 (2 + 2 + 2) | S2 p.2; S2 Almanac p.10 "Progress Cards" |
| Starting victory points per player | 2 (two setup settlements) | S2 Almanac p.14 "Victory Points" |
| VP cards revealed for the win | any number at once, including this turn's purchase | S1 p.9; S5 |

### 6.2 Disagreements and corrections to PRD-v1

**No Appendix A value disagrees with the rulebook.** Four PRD statements nonetheless need correction or
clarification before implementation.

| ID | PRD-v1 statement | What the rulebook says | Resolution |
|---|---|---|---|
| **D-1** | Appendix A: "Structure 19 hexes, **54 vertices, 72 edges**" | No retrieved rulebook states 54 or 72 | The two counts are **derived, not confirmed**. The derivation is reproduced in §4.1 and is asserted by the structural self-check (PRD-v1 SC-7, FR-6.10). The requirement is unchanged; its *status* changes: it is a derived value that a test must protect. |
| **D-2** | FR-10.4: "Production MUST be limited by bank supply; a partial distribution MUST be deterministic and documented in RULES.md" | The general rule is **all-or-nothing per resource**; a partial grant applies **only** when exactly one player is affected (S1 p.6; S2 Almanac p.10; S4 §3.0.11; S5) | The rulebook rule is implemented (§4.6, A-5). The test for FR-10.4 must assert **both** branches, not only the partial one. |
| **D-3** | FR-8.4: "The second settlement MUST grant **one of each resource** from adjacent non-desert hexes" | One resource card **per adjacent hex**, of that hex's type: two forest hexes grant two wood (S1 p.11; S2 Almanac p.12) | The rulebook rule is implemented (§4.3 rule 6). PRD-v1's wording is shorthand and must not be read as "one of each of the five resources". |
| **D-4** | FR-10.1: the turn begins with a decision offering "§roll_dice§ or a legal §play_dev_card§ (knight)" | **Any** playable development card may be played before the roll (S1 p.9; S4 §3.0.1) | The broader rulebook rule is implemented (§4.8, A-2); "(knight)" in FR-10.1 is treated as an example. |

Two further notes on wording, which are **not** disagreements:

* PRD-v1, `ARCHITECTURE.md` and this document say "Longest Road"; the 6th-edition rulebook now prints
  **"Longest Route"**. Same card, same threshold, same value. Code identifiers keep `longest_road`.
* PRD-v1 Appendix A says "sheep"; the resource card is **wool** and the terrain is **pasture**. Code
  identifiers use `wool` and `pasture`.

---

## 7. Rules-code mapping

Each rule module named in `ARCHITECTURE.md` §4.1, and the sections of this document it implements.
Later cards cite `RULES.md` through this table.

| Module | Implements | Notes |
|---|---|---|
| `lgbg/games/catan/rules/setup.py` | §4.3 (setup and snake draft), §4.2 (token placement via board generation), §3.1 draws D1–D4 and D9, §5.10 B-1, B-2, B-3 | Opening placement, distance rule and connectivity during setup, starting endowment and its shortage rule. |
| `lgbg/games/catan/rules/production.py` | §4.5 (production and dice), §4.6 (bank supply limits), §3.1 draws D6 and D7, §5.5 A-5, §6.2 D-2 | Dice, per-hex yields, the per-resource all-or-nothing and single-player shortfall rule, conservation. |
| `lgbg/games/catan/rules/building.py` | §4.7 (building and pieces), §4.1 items 3–5 (vertex and edge legality), §5.10 B-15, §6.2 D-3 | Costs, piece supplies, road connectivity, distance rule, city upgrade. |
| `lgbg/games/catan/rules/longest_road.py` | §4.10 (longest road), §5.8 A-8 (the shared award algorithm applied to roads), §5.10 B-14 | Exhaustive simple-path **and** simple-cycle search; opponent buildings are path barriers. PRD-v1 SC-11 requires 100% coverage. |
| `lgbg/games/catan/rules/trading.py` | §4.12.1 (maritime ratios and ports), §4.12.2 (player-to-player offers and responses), §5.7 A-7, §5.10 B-10, B-11, B-12, B-13, B-20 | Ratio lookup from port access, offer validation, concurrent responses, atomic execution, bank-availability rejection. |
| `lgbg/games/catan/rules/devcards.py` | §4.8 (deck, purchase, timing, all five card effects), §3.1 draw D5, §5.2 A-2, §5.4 A-4, §5.6 A-6, §5.10 B-16, B-17, B-21 | Canonical deck order, single startup shuffle, purchase with no draw, windows W1/W2/W3, per-card effects. |
| `lgbg/games/catan/rules/robber.py` | §4.9 (robber movement and stealing), §3.1 draw D8, §4.4 (the concurrent discard phase), §5.10 B-6, B-7, B-8, B-9, B-22 | Forced-discard phase, blocking, movement to a different hex, victim selection, uniform random steal. |
| `lgbg/games/catan/rules/victory.py` | §4.13 (victory and termination), §4.11 (largest army), §5.8 A-8 (the shared award algorithm applied to knights), §5.3 A-3, §5.10 B-18, B-19, §6 values A12–A15 | Scoring, the shared award computation, win detection and timing, terminality, outcome. |
| `lgbg/games/catan/board/topology.py` (supporting) | §4.1 items 1–5, §6.2 D-1 | Derived adjacency, structural self-check (19/54/72, 24-12-18, 42-30, symmetric adjacency, coast classification). |
| `lgbg/games/catan/board/generation.py` (supporting) | §4.1 items 6–7, §4.2 in full, §3.1 draws D1–D4 | Fixed and seeded-random arrangements, token placement modes, the adjacency check and repair, port assignment. |
| `lgbg/games/catan/phases.py` (supporting) | §4.4 in full, §4.3 item 1 | The phase machine and decision-request construction, including the concurrent discard and trade-response phases and the seat-order resolution rule. |

**Reading order for an implementer:** §3 (conventions and draws) → the §4 subsection for the module → the
matching §5 entry for anything that looks under-specified → §6 before touching any numeric constant.

---

*End of document. Document revision 1; plugin `rules_version` `catan-rules-1`.*
