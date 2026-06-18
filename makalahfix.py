import time
import random

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
EASY_THRESHOLD   = 100.0
MEDIUM_THRESHOLD = 250.0

SLOT_NAMES = [
    "Flower of Life", "Plume of Death", "Sands of Eon",
    "Goblet of Eonothem", "Circlet of Logos"
]

# ─────────────────────────────────────────────
#  ARTIFACT
# ─────────────────────────────────────────────
class Artifact:
    def __init__(self, id_num, slot_index, set_name, main_stat, substats):
        self.id          = id_num
        self.slot_index  = slot_index   # 0–4
        self.set_name    = set_name
        self.main_stat   = main_stat
        self.substats    = substats

        def _get(key):
            return substats.get(key, 0.0) + main_stat.get(key, 0.0)

        self.atk_pct    = _get("ATK%")
        self.flat_atk   = _get("Flat ATK")
        self.cr         = _get("Crit Rate")
        self.cdm        = _get("Crit DMG")
        self.em         = _get("EM")
        self.pyro_bonus = main_stat.get("Pyro DMG", 0.0)

        self.hp_pct     = _get("HP%")
        self.def_pct    = _get("DEF%")
        self.er_pct     = _get("ER%")
        self.flat_hp    = _get("Flat HP")
        self.flat_def   = substats.get("Flat DEF", 0.0)

        self.rarity_score = self._calculate_rarity_score()

    def _calculate_rarity_score(self):
        score  = self.cr  * 3.0
        score += self.cdm * 1.5
        score += self.pyro_bonus * 2.0
        score += self.atk_pct   * 0.5
        score += self.em        * 0.05
        score += (self.er_pct + self.hp_pct + self.def_pct) * 0.3
        score += (self.flat_atk + self.flat_def)            * 0.03
        score += self.flat_hp                               * 0.003
        penalty = 0.0
        if self.def_pct > 0: penalty += 5.0
        if self.flat_hp > 0: penalty += 3.0
        if self.flat_def > 0: penalty += 3.0
        
        final_score = score - penalty
        return round(final_score, 1)


# ─────────────────────────────────────────────
#  DAMAGE CALCULATION  (from aggregated stats)
# ─────────────────────────────────────────────
def _compute_damage_from_stats(
    total_atk_pct, total_flat_atk, total_cr, total_cdm,
    total_em, total_pyro_bonus, obsidian_count, witch_count
):
    base_atk   = 346 + 741
    base_cr    = 5.0 + 11.0
    base_cdm   = 50.0 + 38.4 + 35.0

    obsidian_cr_bonus = 40.0 if obsidian_count >= 4 else 0.0
    obsidian2_piece_bonus = 15.0 if obsidian_count >= 2 else 0.0
    witch_melt_bonus = 0.15 if witch_count >= 4 else 0.0
    if witch_count >= 2:
        witch_pyro_bonus = 15.0
    elif witch_count >= 4:
        witch_pyro_bonus = 22.5
    else:
        witch_pyro_bonus = 0.0

    bennett_flat_atk_buff   = 1200
    bennett_noblesse   = 20
    bennett_c6   = 15
    xilonen_dmg_bonus_pct   = 40.0
    citlali_em_buff         = 200
    citlali_res         = 0.2

    total_atk = (
        (base_atk * (1.0 + 0.49 + ((bennett_noblesse + total_atk_pct) / 100.0)))
        + total_flat_atk + bennett_flat_atk_buff
    )
    total_em  = total_em + citlali_em_buff

    final_cr  = min((base_cr + total_cr + obsidian_cr_bonus) / 100.0, 1.0)
    final_cdm = (base_cdm + total_cdm) / 100.0

    melt_dmg_bonus  = (2.78 * total_em) / (total_em + 1400)
    reaction_mult   = 2.0 * (1.0 + melt_dmg_bonus + witch_melt_bonus)
    pyro_multiplier = 1.0 + (total_pyro_bonus / 100.0) + (xilonen_dmg_bonus_pct / 100.0) + (bennett_c6 / 100) + (witch_pyro_bonus / 100.0)

    enemy_def  = 0.5
    enemy_res  = 1.15 + citlali_res
    global_mult      = enemy_def * enemy_res * pyro_multiplier * reaction_mult * (1.0 + obsidian2_piece_bonus/100)
    crit_expectation = 1.0 + (final_cr * final_cdm)

    burst_mult = 7.5616 + (0.0272 * 200)
    ca_mult    = 1.81 + (0.0095 * 200)
    na_mult    = 1.20 + (0.0047 * 200)
    basedmg_burst = (total_atk * burst_mult)
    basedmg_ca = (total_atk * ca_mult)
    basedmg_na = (total_atk * na_mult)
    avg_burst = basedmg_burst * global_mult * crit_expectation
    avg_ca    = basedmg_ca    * global_mult * crit_expectation
    avg_na    = basedmg_na    * global_mult * crit_expectation
    return avg_burst, avg_ca, avg_na


# ─────────────────────────────────────────────
#  DP STATE
# ─────────────────────────────────────────────
class DPState:
    __slots__ = (
        "atk_pct", "flat_atk", "cr", "cdm", "em",
        "pyro_bonus", "difficulty", "obsidian_count", "witch_count",
        "chosen",          # list[Artifact] — selected pieces so far
    )

    def __init__(self):
        self.atk_pct       = 0.0
        self.flat_atk      = 0.0
        self.cr            = 0.0
        self.cdm           = 0.0
        self.em            = 0.0
        self.pyro_bonus    = 0.0
        self.difficulty    = 0.0
        self.obsidian_count = 0
        self.witch_count    = 0
        self.chosen        = []

    def extend(self, art: Artifact) -> "DPState":
        ns = DPState()
        ns.atk_pct        = self.atk_pct    + art.atk_pct
        ns.flat_atk       = self.flat_atk   + art.flat_atk
        ns.cr             = self.cr         + art.cr
        ns.cdm            = self.cdm        + art.cdm
        ns.em             = self.em         + art.em
        ns.pyro_bonus     = self.pyro_bonus + art.pyro_bonus
        ns.difficulty     = self.difficulty + art.rarity_score
        ns.obsidian_count = self.obsidian_count + (1 if art.set_name == "Obsidian Codex" else 0)
        ns.witch_count    = self.witch_count + (1 if art.set_name == "Crimson Witch" else 0)
        ns.chosen         = self.chosen + [art]
        return ns

    def burst_damage(self) -> float:
        b, _, _ = _compute_damage_from_stats(
            self.atk_pct, self.flat_atk, self.cr, self.cdm,
            self.em, self.pyro_bonus, self.obsidian_count, self.witch_count
        )
        return b

    def all_damage(self):
        return _compute_damage_from_stats(
            self.atk_pct, self.flat_atk, self.cr, self.cdm,
            self.em, self.pyro_bonus, self.obsidian_count, self.witch_count
        )
    
    def get_total_stats(self):
        stats = {"ATK%": 0.0, "Flat ATK": 0.0, "Crit Rate": 0.0, "Crit DMG": 0.0, 
                 "EM": 0.0, "Pyro DMG": 0.0, "HP%": 0.0, "DEF%": 0.0, 
                 "ER%": 0.0, "Flat HP": 0.0, "Flat DEF": 0.0}
        for art in self.chosen:
            stats["ATK%"] += art.atk_pct
            stats["Flat ATK"] += art.flat_atk
            stats["Crit Rate"] += art.cr
            stats["Crit DMG"] += art.cdm
            stats["EM"] += art.em
            stats["Pyro DMG"] += art.pyro_bonus
            stats["HP%"] += art.hp_pct
            stats["DEF%"] += art.def_pct
            stats["ER%"] += art.er_pct
            stats["Flat HP"] += art.flat_hp
            stats["Flat DEF"] += art.flat_def
        return stats

    def get_summary_stats(self):
        raw = self.get_total_stats()
        total_atk = ((346 + 741) * (1.0 + 0.49 + raw["ATK%"] / 100.0)) + raw["Flat ATK"] + 700
        total_hp = (12000 * (1.0 + raw["HP%"] / 100.0)) + raw["Flat HP"]
        total_def = (800 * (1.0 + raw["DEF%"] / 100.0)) + raw["Flat DEF"]
        
        return {
            "Total ATK": total_atk,
            "Total HP": total_hp,
            "Total DEF": total_def,
            "Total EM": raw["EM"] + 200,
            "Total Crit Rate": 16.0 + raw["Crit Rate"] + (40.0 if self.obsidian_count >= 4 else 0.0),
            "Total Crit DMG": 85.0 + 35.0 + raw["Crit DMG"],
            "Pyro DMG Bonus": raw["Pyro DMG"] + 40.0 + 15.0 + (22.5 if self.witch_count >= 4 else 0.0),
        }

# ─────────────────────────────────────────────
#  CATEGORY HELPERS
# ─────────────────────────────────────────────
def _category(difficulty: float) -> str:
    if difficulty <= EASY_THRESHOLD:
        return "easy"
    elif difficulty <= MEDIUM_THRESHOLD:
        return "medium"
    return "god"

def _dominates(candidate: DPState, incumbent: DPState | None) -> bool:
    return (
        incumbent is None
        or candidate.burst_damage() > incumbent.burst_damage()
    )


# ─────────────────────────────────────────────────────────────────────────────
#  CORE DP  —  O(slots × N)  instead of O(N^5)
# ─────────────────────────────────────────────────────────────────────────────
def get_best_build_per_category_dp(inventory: list[Artifact]):
    slots = [[] for _ in range(5)]
    for art in inventory:
        slots[art.slot_index].append(art)

    dp = {"easy": {}, "medium": {}, "god": {}}

    active_states = [DPState()]

    for slot_arts in slots:
        new_states = []
        for prev_state in active_states:
            for art in slot_arts:
                ns = prev_state.extend(art)
                current_dmg = ns.burst_damage()
                cat = _category(ns.difficulty)
                existing = dp[cat].get(int(ns.difficulty))
                if existing is None or current_dmg > existing.burst_damage():
                    dp[cat][int(ns.difficulty)] = ns
                    new_states.append(ns)
        
        new_states.sort(key=lambda x: x.burst_damage(), reverse=True)
        active_states = new_states[:150] 

    best = {"easy": None, "medium": None, "god": None}
    for cat in ["easy", "medium", "god"]:
        for diff in dp[cat]:
            if _dominates(dp[cat][diff], best[cat]):
                best[cat] = dp[cat][diff]
                
    return best["easy"], best["medium"], best["god"]


# ─────────────────────────────────────────────
#  5-STAR MAIN STAT POOLS
# ─────────────────────────────────────────────
#
#  Slot 0 – Flower of Life   : always Flat HP
#  Slot 1 – Plume of Death   : always Flat ATK
#  Slot 2 – Sands of Eon     : HP% | ATK% | DEF% | EM | ER%
#  Slot 3 – Goblet of Eonothem: HP% | ATK% | DEF% | EM | Elemental DMG% | Physical DMG%
#  Slot 4 – Circlet of Logos : HP% | ATK% | DEF% | EM | Crit Rate | Crit DMG | Healing Bonus%

MAIN_STAT_POOLS: list[list[tuple[str, float]]] = [
    # Slot 0 – Flower (fixed)
    [("Flat HP", 4780.0)],

    # Slot 1 – Plume (fixed)
    [("Flat ATK", 311.0)],

    # Slot 2 – Sands
    [
        ("HP%",      46.6),
        ("ATK%",     46.6),
        ("DEF%",     58.3),
        ("EM",      186.5),
        ("ER%",      51.8),
    ],

    # Slot 3 – Goblet
    [
        ("HP%",        46.6),
        ("ATK%",       46.6),
        ("DEF%",       58.3),
        ("EM",        186.5),
        ("Pyro DMG",   46.6),   # Elemental DMG Bonus — Pyro for Mavuika
        ("Hydro DMG",  46.6),
        ("Cryo DMG",   46.6),
        ("Electro DMG",46.6),
        ("Anemo DMG",  46.6),
        ("Geo DMG",    46.6),
        ("Dendro DMG", 46.6),
        ("Physical DMG",58.3),
    ],

    # Slot 4 – Circlet
    [
        ("HP%",            46.6),
        ("ATK%",           46.6),
        ("DEF%",           58.3),
        ("EM",            186.5),
        ("Crit Rate",      31.1),
        ("Crit DMG",       62.2),
        ("Healing Bonus",  35.9),
    ],
]

# ─────────────────────────────────────────────────────────────────────────────
#  5-STAR SUBSTAT TIERS
# ─────────────────────────────────────────────────────────────────────────────
SUBSTAT_TIERS: dict[str, tuple[float, float, float, float]] = {
    #              T0      T1      T2      T3
    "Flat HP":   (209.13, 239.00, 268.88, 298.75),
    "Flat ATK":  ( 13.62,  15.56,  17.51,  19.45),
    "Flat DEF":  ( 16.20,  18.52,  20.83,  23.15),
    "HP%":       (  4.08,   4.66,   5.25,   5.83),
    "ATK%":      (  4.08,   4.66,   5.25,   5.83),
    "DEF%":      (  5.10,   5.83,   6.56,   7.29),
    "EM":        ( 16.32,  18.65,  20.98,  23.31),
    "ER%":       (  4.53,   5.18,   5.83,   6.48),
    "Crit Rate": (  2.72,   3.11,   3.50,   3.89),
    "Crit DMG":  (  5.44,   6.22,   6.99,   7.77),
}

SUBSTAT_WEIGHTS: list[tuple[str, float]] = [
    ("Flat HP",   1.50),
    ("Flat ATK",  1.50),
    ("Flat DEF",  1.50),
    ("HP%",       1.00),
    ("ATK%",      1.00),
    ("DEF%",      1.00),
    ("EM",        1.00),
    ("ER%",       1.00),
    ("Crit Rate", 0.75),
    ("Crit DMG",  0.75),
]


def _one_roll(key: str) -> float:
    return random.choice(SUBSTAT_TIERS[key])


def _weighted_sample_no_replace(pool_keys, pool_wts, n) -> list[str]:
    chosen = []
    keys = list(pool_keys)
    wts  = list(pool_wts)
    for _ in range(n):
        total = sum(wts)
        r = random.uniform(0, total)
        cumulative = 0.0
        for i, (k, w) in enumerate(zip(keys, wts)):
            cumulative += w
            if r <= cumulative:
                chosen.append(k)
                keys.pop(i)
                wts.pop(i)
                break
    return chosen


def _generate_substats(main_stat_key: str) -> dict[str, float]:
    eligible_kw = [(k, w) for k, w in SUBSTAT_WEIGHTS if k != main_stat_key]
    e_keys, e_wts = zip(*eligible_kw)
    base_count = random.choice([3, 4])
    total_lines = 4
    n_upgrades = 4 if base_count == 3 else 5

    all_lines = _weighted_sample_no_replace(e_keys, e_wts, total_lines)
    base_values = {key: _one_roll(key) for key in all_lines}
    roll_counts = [1] * total_lines
    for _ in range(n_upgrades):
        roll_counts[random.randint(0, 3)] += 1

    substats: dict[str, float] = {}
    for key, n_rolls in zip(all_lines, roll_counts):
        substats[key] = round(base_values[key] * n_rolls, 2)

    return substats


def generate_mock_inventory(size: int = 120) -> list[Artifact]:
    inventory: list[Artifact] = []
    random.seed(67)
    set_pool = ["Obsidian Codex", "Crimson Witch"]

    for idx in range(size):
        s_idx    = idx % 5
        set_name = random.choice(set_pool)

        main_key, main_val = random.choice(MAIN_STAT_POOLS[s_idx])
        main_stat = {main_key: main_val}

        substats = _generate_substats(main_key)

        inventory.append(Artifact(idx, s_idx, set_name, main_stat, substats))

    return inventory


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    mock_inventory = generate_mock_inventory(2400)
    print("Mengevaluasi kombinasi teroptimal dengan Dynamic Programming...")

    start = time.perf_counter()
    easy_build, med_build, god_build = get_best_build_per_category_dp(mock_inventory)
    end   = time.perf_counter()

    categories = [
        ("MUDAH (Low-Investment Profile)",   easy_build),
        ("MENENGAH (Mid-Investment Profile)", med_build),
        ("GOD ROLL (High-Investment Profile)", god_build),
    ]

    print("\n================== SIMULATION RESULTS (DYNAMIC PROGRAMMING) ==================")
    print(f"Waktu Analisis Komputasi Sistem: {(end - start)*1000:.2f} ms")
    print("===============================================================================")

    for title, state in categories:
        if state is None:
            print(f"\n[ KATEGORI: {title} ] -> Data Kosong (Sesuaikan threshold)")
            continue
        
        avg_burst, avg_ca, avg_na = state.all_damage()
        stats = state.get_summary_stats()
        print(f"\n[ KATEGORI: {title} ]")
        print(f" -> Ekspektasi Avg Burst DMG : {avg_burst:,.2f} Damage")
        print(f" -> Ekspektasi Avg Charged DMG: {avg_ca:,.2f} Damage")
        print(f" -> Total Nilai Poin Kesulitan Build: {state.difficulty:.1f} Poin")
        print(f" -> Total ATK      : {stats['Total ATK']:.0f}")
        print(f" -> Total HP       : {stats['Total HP']:.0f}")
        print(f" -> Total DEF      : {stats['Total DEF']:.0f}")
        print(f" -> Total EM       : {stats['Total EM']:.0f}")
        print(f" -> Crit Rate      : {stats['Total Crit Rate']:.1f}%")
        print(f" -> Crit DMG       : {stats['Total Crit DMG']:.1f}%")
        print(f" -> Pyro DMG Bonus : {stats['Pyro DMG Bonus']:.1f}%\n")

        for art in state.chosen:
            print(f"   * Slot [{SLOT_NAMES[art.slot_index]}] | Set: {art.set_name}")
            m = [f"{k}: +{v}" for k, v in art.main_stat.items() if v > 0]
            print(f"     Main Stat: {', '.join(m)}")
            s = [f"{k}: +{v}" for k, v in art.substats.items()]
            print(f"     Substats : {', '.join(s)} | (Skor Item: {art.rarity_score})\n")
        print("-" * 100)