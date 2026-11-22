"""Who gets a label. Kept in one small function so every combination of settings is easy
to reason about and test.

Each paid order is decided exactly once, and either gets one label or none, so no
combination of settings can print two labels for one order.
"""

# The "Giveaways:" dropdown: what's shown, and what's saved in the settings.
GIVEAWAY_CHOICES = [("Always Print", "always"), ("Never Print", "never"),
                    ("Only if first label", "first")]


def giveaway_mode_from(cfg):
    """The saved "Giveaways:" choice. For settings saved before the dropdown existed, the
    nearest one to the old settings: giveaways turned off -> Never Print, the "Always Print
    Giveaways" checkbox -> Always Print (ticked) or Only if first label (unticked)."""
    rules = cfg.get("label_rules") or {}
    mode = rules.get("giveaways")
    if mode in ("always", "never", "first"):
        return mode
    if (cfg.get("detection") or {}).get("print_giveaways") is False:
        return "never"
    return "always" if rules.get("always_print_giveaways", True) else "first"


def should_print(is_giveaway, already_labeled, print_every_sale, giveaway_mode):
    """
    is_giveaway       -- this order is a giveaway win
    already_labeled   -- this buyer already got a label earlier this session
    print_every_sale  -- "Print Every Sale" checkbox: every sale prints
    giveaway_mode     -- the "Giveaways:" dropdown:
                           "always" every giveaway prints, even for repeat buyers
                           "never"  giveaways never print
                           "first"  a giveaway prints only if it's the buyer's first label
    """
    if is_giveaway:
        if giveaway_mode == "always":
            return True
        if giveaway_mode == "never":
            return False
        return not already_labeled
    if print_every_sale:
        return True                      # every sale prints
    return not already_labeled           # otherwise: only the buyer's first label
