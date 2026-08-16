from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="LAVA Inventory Desk",
    page_icon=":material/price_change:",
    layout="wide",
    initial_sidebar_state="expanded",
)


REQUIRED_COLUMNS = [
    "TCGplayer Id",
    "Product Name",
    "Rarity",
    "Condition",
    "TCG Low Price With Shipping",
    "TCG Low Price",
    "Total Quantity",
    "TCG Marketplace Price",
]

MANUAL_DEFAULTS = ["Enchanted", "Iconic", "Epic", "Promo"]

LORCANA_SET_NAMES = {
    "1": "The First Chapter",
    "2": "Rise of the Floodborn",
    "3": "Into the Inklands",
    "4": "Ursula's Return",
    "5": "Shimmering Skies",
    "6": "Azurite Sea",
    "7": "Archazia's Island",
    "8": "Reign of Jafar",
    "9": "Fabled",
    "10": "Whispers in the Well",
    "11": "Winterspell",
    "12": "Wilds Unknown",
    "13": "Attack of the Vine!",
}

NUMERIC_COLUMNS = [
    "TCG Market Price",
    "TCG Direct Low",
    "TCG Low Price With Shipping",
    "TCG Low Price",
    "Total Quantity",
    "Add to Quantity",
    "TCG Marketplace Price",
]

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=DM+Serif+Display&display=swap');

    :root {
        --paper: #f4efe3;
        --ink: #202824;
        --forest: #17483a;
        --coral: #d65f3c;
        --line: rgba(32, 40, 36, .15);
    }

    html, body, [class*="css"] {
        font-family: "DM Sans", sans-serif;
    }

    h1, h2, h3 {
        font-family: "DM Serif Display", Georgia, serif !important;
        font-weight: 400 !important;
        letter-spacing: -.025em;
    }

    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 88% 2%, rgba(214,95,60,.13), transparent 26rem),
            linear-gradient(90deg, rgba(32,40,36,.025) 1px, transparent 1px),
            var(--paper);
        background-size: auto, 42px 42px, auto;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid var(--line);
        background: #fffdf8;
    }

    [data-testid="stMetric"] {
        min-height: 128px;
        padding: 18px 20px;
        border: 1px solid var(--line);
        border-radius: 14px;
        background: rgba(255,253,248,.92);
        box-shadow: 0 10px 30px rgba(54,44,28,.06);
    }

    [data-testid="stMetricLabel"] {
        color: #57615a;
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .06em;
        text-transform: uppercase;
    }

    [data-testid="stMetricValue"] {
        font-family: "DM Serif Display", Georgia, serif;
        color: var(--ink);
    }

    .lava-kicker {
        margin: 0 0 .35rem;
        color: var(--coral);
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .16em;
        text-transform: uppercase;
    }

    .lava-lede {
        max-width: 760px;
        margin: -.4rem 0 1.4rem;
        color: #57615a;
    }

    .privacy-pill {
        display: inline-block;
        margin-bottom: 1.1rem;
        padding: .42rem .7rem;
        border: 1px solid var(--line);
        border-radius: 999px;
        color: #57615a;
        background: rgba(255,253,248,.75);
        font-size: .72rem;
        font-weight: 700;
    }

    .privacy-pill::before {
        display: inline-block;
        width: 7px;
        height: 7px;
        margin-right: 7px;
        border-radius: 50%;
        background: #1f6d55;
        content: "";
    }

    .rule-card {
        margin: .75rem 0;
        padding: .8rem .9rem;
        border-left: 3px solid var(--coral);
        border-radius: 0 8px 8px 0;
        background: rgba(214,95,60,.07);
        color: #57615a;
        font-size: .78rem;
        line-height: 1.45;
    }

    .export-note {
        padding: .8rem 1rem;
        border-radius: 9px;
        color: #fffdf8;
        background: var(--ink);
        font-size: .76rem;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: hidden;
    }

    .stButton button, .stDownloadButton button {
        border-radius: 8px;
        font-weight: 700;
    }
</style>
"""


@dataclass(frozen=True)
class PricingRules:
    matching_mode: str
    threshold: float
    normal_floors: dict[str, float]
    foil_floors: dict[str, float]
    specific_floor_sets: frozenset[str]
    specific_normal_floors: dict[str, float]
    specific_foil_floors: dict[str, float]
    manual_rarities: frozenset[str]
    excluded_sets: frozenset[str] = frozenset()
    low_safety_enabled: bool = True
    low_market_gap_threshold: float = 0.20
    low_safety_market_minimum: float = 5.00
    quantity_tiers_enabled: bool = False
    four_plus_markup: float = 0.05
    fifteen_plus_markup: float = 0.10
    cap_quantity_markup_at_market: bool = True
    final_offset_enabled: bool = False
    final_price_offset: float = 0.0


def money(value: float) -> str:
    return f"${value:,.2f}"


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[$,]", "", regex=True),
        errors="coerce",
    ).fillna(0.0)


def read_inventory(uploaded_file) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            uploaded_file,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except Exception as exc:
        raise ValueError(f"Unable to read this CSV: {exc}") from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "This is not a compatible TCGplayer export. Missing columns: "
            + ", ".join(missing)
        )

    for column in NUMERIC_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    return frame


def normalize_card_number(value: object) -> str:
    text = str(value).strip().split("/", 1)[0]
    try:
        return str(int(float(text)))
    except ValueError:
        return text.lower()


def normalize_text(value: object) -> str:
    return " ".join(str(value).strip().lower().split())


def finish_from_value(value: object) -> str:
    text = normalize_text(value)
    return "Foil" if "foil" in text and "non-foil" not in text else "Normal"


def read_scan_file(uploaded_file) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            uploaded_file,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except Exception as exc:
        raise ValueError(f"Unable to read {uploaded_file.name}: {exc}") from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    source_name = uploaded_file.name
    standardized = pd.DataFrame(index=frame.index)
    standardized["Source File"] = source_name
    standardized["Scan Row"] = frame.index + 2

    if {"Set Number", "Card Number", "Variant", "Count"}.issubset(frame.columns):
        standardized["Set Number"] = frame["Set Number"].astype(str).str.strip()
        standardized["Set Name"] = standardized["Set Number"].map(LORCANA_SET_NAMES).fillna("")
        standardized["Card Number"] = frame["Card Number"].map(normalize_card_number)
        standardized["Product Name"] = ""
        standardized["Variant"] = frame["Variant"]
        standardized["TCGplayer Id"] = ""
        standardized["Scan Quantity"] = safe_numeric(frame["Count"]).astype(int)
        return standardized

    quantity_column = next(
        (
            column
            for column in ["Count", "Quantity", "Add to Quantity", "Total Quantity"]
            if column in frame.columns
        ),
        None,
    )
    if quantity_column is None:
        raise ValueError(
            f"{source_name} does not include a supported quantity column."
        )
    if "TCGplayer Id" not in frame.columns and not (
        {"Set Name", "Number"}.issubset(frame.columns)
        or {"Set Name", "Product Name"}.issubset(frame.columns)
    ):
        raise ValueError(
            f"{source_name} needs TCGplayer Id, or Set Name with Number/Product Name."
        )

    standardized["Set Number"] = ""
    standardized["Set Name"] = frame.get("Set Name", "")
    standardized["Card Number"] = frame.get("Number", "").map(normalize_card_number) if "Number" in frame else ""
    standardized["Product Name"] = frame.get("Product Name", "")
    standardized["Variant"] = frame.get("Condition", frame.get("Printing", "Normal"))
    standardized["TCGplayer Id"] = frame.get("TCGplayer Id", "")
    standardized["Scan Quantity"] = safe_numeric(frame[quantity_column]).astype(int)
    return standardized


def match_scans_to_catalog(
    scans: pd.DataFrame, source: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    catalog = source.copy()
    catalog["_catalog_index"] = catalog.index
    catalog["_id_key"] = catalog["TCGplayer Id"].astype(str).str.strip()
    catalog["_set_key"] = catalog["Set Name"].map(normalize_text)
    catalog["_number_key"] = catalog["Number"].map(normalize_card_number)
    catalog["_name_key"] = catalog["Product Name"].map(normalize_text)
    catalog["_finish_key"] = catalog["Condition"].map(finish_from_value)

    matched_records: list[dict[str, object]] = []
    unmatched_records: list[dict[str, object]] = []

    for _, scan in scans.iterrows():
        quantity = int(scan["Scan Quantity"])
        scan_record = scan.to_dict()
        if quantity <= 0:
            scan_record["Reason"] = "Quantity must be greater than zero"
            unmatched_records.append(scan_record)
            continue

        candidates = catalog.iloc[0:0]
        tcg_id = str(scan.get("TCGplayer Id", "")).strip()
        if tcg_id:
            candidates = catalog.loc[catalog["_id_key"] == tcg_id]
        else:
            set_name = str(scan.get("Set Name", "")).strip()
            card_number = normalize_card_number(scan.get("Card Number", ""))
            product_name = normalize_text(scan.get("Product Name", ""))
            finish = finish_from_value(scan.get("Variant", "Normal"))

            if set_name and card_number:
                candidates = catalog.loc[
                    (catalog["_set_key"] == normalize_text(set_name))
                    & (catalog["_number_key"] == card_number)
                    & (catalog["_finish_key"] == finish)
                ]
            if candidates.empty and set_name and product_name:
                candidates = catalog.loc[
                    (catalog["_set_key"] == normalize_text(set_name))
                    & (catalog["_name_key"] == product_name)
                    & (catalog["_finish_key"] == finish)
                ]

        if len(candidates) != 1:
            scan_record["Reason"] = (
                "No catalog match" if candidates.empty else "Multiple catalog matches"
            )
            unmatched_records.append(scan_record)
            continue

        catalog_row = candidates.iloc[0]
        matched_records.append(
            {
                "_catalog_index": int(catalog_row["_catalog_index"]),
                "Source File": scan["Source File"],
                "Scan Quantity": quantity,
            }
        )

    unmatched = pd.DataFrame(unmatched_records)
    if not matched_records:
        return pd.DataFrame(), unmatched

    matched_lines = pd.DataFrame(matched_records)
    grouped = (
        matched_lines.groupby("_catalog_index", as_index=False)
        .agg(
            **{
                "Quantity to Add": ("Scan Quantity", "sum"),
                "Source Files": (
                    "Source File",
                    lambda values: ", ".join(sorted(set(values))),
                ),
            }
        )
    )
    catalog_details = catalog[
        [
            "_catalog_index",
            "TCGplayer Id",
            "Product Name",
            "Set Name",
            "Number",
            "Rarity",
            "Condition",
            "Total Quantity",
            "TCG Marketplace Price",
            "TCG Low Price",
            "TCG Market Price",
        ]
    ].copy()
    matched = grouped.merge(catalog_details, on="_catalog_index", how="left")
    matched["Current Quantity"] = safe_numeric(matched["Total Quantity"]).astype(int)
    matched["Resulting Quantity"] = (
        matched["Current Quantity"] + matched["Quantity to Add"]
    )
    matched["Current Price"] = safe_numeric(matched["TCG Marketplace Price"])
    matched["TCG Low"] = safe_numeric(matched["TCG Low Price"])
    matched["TCG Market"] = safe_numeric(matched["TCG Market Price"])
    matched["Finish"] = matched["Condition"].map(finish_from_value)
    return matched.sort_values(["Set Name", "Product Name", "Finish"]), unmatched


def inventory_update_csv(
    matched: pd.DataFrame, source: pd.DataFrame, headers: Iterable[str]
) -> bytes:
    quantity_by_index = matched.set_index("_catalog_index")["Quantity to Add"]
    export = source.loc[quantity_by_index.index, list(headers)].copy()
    export["Total Quantity"] = ""
    export["Add to Quantity"] = export.index.map(quantity_by_index).astype(int).astype(str)
    export["Photo URL"] = ""
    return export.to_csv(index=False, quoting=1, lineterminator="\r\n").encode("utf-8")


def apply_quantity_additions(
    source: pd.DataFrame, matched: pd.DataFrame
) -> pd.DataFrame:
    projected = source.copy()
    if matched.empty:
        return projected

    additions = matched.set_index("_catalog_index")["Quantity to Add"]
    current = safe_numeric(projected["Total Quantity"]).clip(lower=0)
    projected["Total Quantity"] = current + projected.index.to_series().map(
        additions
    ).fillna(0)
    return projected


def build_combined_review(
    calculated: pd.DataFrame,
    source: pd.DataFrame,
    matched: pd.DataFrame,
    include_price_updates: bool = True,
    include_quantity_updates: bool = True,
) -> pd.DataFrame:
    combined = calculated.copy()
    additions = (
        matched.set_index("_catalog_index")["Quantity to Add"]
        if not matched.empty
        else pd.Series(dtype=float)
    )
    source_files = (
        matched.set_index("_catalog_index")["Source Files"]
        if not matched.empty
        else pd.Series(dtype=str)
    )
    current_quantity = safe_numeric(source["Total Quantity"]).clip(lower=0).astype(int)
    combined["Current Quantity"] = current_quantity
    combined["Quantity to Add"] = (
        combined.index.to_series().map(additions).fillna(0).astype(int)
    )
    combined["Resulting Quantity"] = (
        combined["Current Quantity"] + combined["Quantity to Add"]
    )
    combined["Quantity Changed"] = combined["Quantity to Add"] > 0
    combined["Source Files"] = (
        combined.index.to_series().map(source_files).fillna("")
    )
    combined["Price Export Eligible"] = (
        (combined["Current Quantity"] > 0)
        | (combined["Quantity to Add"] > 0)
    )
    combined["Price Included"] = (
        combined["Price Changed"]
        & combined["Price Export Eligible"]
        & include_price_updates
    )
    combined["Quantity Included"] = (
        combined["Quantity Changed"] & include_quantity_updates
    )
    combined["Update Included"] = (
        combined["Price Included"] | combined["Quantity Included"]
    )
    return combined


def combined_update_csv(
    combined: pd.DataFrame, source: pd.DataFrame, headers: Iterable[str]
) -> bytes:
    changed = combined.loc[combined["Update Included"]].copy()
    export = source.loc[changed.index, list(headers)].copy()
    export["Total Quantity"] = ""
    exported_additions = changed["Quantity to Add"].where(
        changed["Quantity Included"], 0
    )
    export["Add to Quantity"] = exported_additions.astype(int).astype(str)
    price_updates = changed["Proposed Price"].map(lambda value: f"{value:.4f}")
    export["TCG Marketplace Price"] = export["TCG Marketplace Price"].where(
        ~changed["Price Included"], price_updates
    )
    export["Photo URL"] = ""
    return export.to_csv(index=False, quoting=1, lineterminator="\r\n").encode("utf-8")


def is_foil(condition: pd.Series) -> pd.Series:
    return condition.str.contains("foil", case=False, na=False)


def proposed_price_for_row(row: pd.Series, rules: PricingRules) -> pd.Series:
    rarity = row["Rarity"]
    foil = row["_is_foil"]
    low = row["_low"]
    low_with_shipping = row["_low_shipping"]
    current = row["_current_price"]
    market = row["_market"]

    ignored_set = row["Set Name"] in rules.excluded_sets
    manual = rarity in rules.manual_rarities
    low_market_gap = (market - low) / market if market > 0 and low > 0 else 0.0
    safety_alert = (
        not ignored_set
        and
        rules.low_safety_enabled
        and low > 0
        and market >= rules.low_safety_market_minimum
        and low_market_gap >= rules.low_market_gap_threshold
    )
    safety_hold = safety_alert and rules.matching_mode == "Match Low"

    if rules.matching_mode == "Match Market":
        match_price = market if market > 0 else current
        decision = "Match Market" if market > 0 else "Market unavailable"
    elif rules.matching_mode == "Do not match":
        match_price = current
        decision = "Keep current price"
    else:
        match_price = low
        decision = "Match TCG Low"
        if low >= rules.threshold:
            if low_with_shipping > 0:
                match_price = low_with_shipping
                decision = "Match Low + shipping"
            else:
                decision = "Shipping Low unavailable"

    uses_specific_floors = row["Set Name"] in rules.specific_floor_sets
    if uses_specific_floors:
        floors = (
            rules.specific_foil_floors
            if foil
            else rules.specific_normal_floors
        )
        floor_group = "Selected sets"
    else:
        floors = rules.foil_floors if foil else rules.normal_floors
        floor_group = "Default"
    floor = floors.get(rarity, 0.0)
    proposed = max(match_price, floor)
    quantity_tier = ""
    quantity_markup = 0.0

    if floor > match_price:
        if uses_specific_floors:
            decision = "Selected-set foil floor" if foil else "Selected-set rarity floor"
        else:
            decision = "Foil floor" if foil else "Rarity floor"
    if ignored_set:
        proposed = current
        decision = "Ignored set"
    elif manual:
        proposed = current
        decision = "Manual review"
    elif safety_hold:
        proposed = current
        decision = "Safety hold: Low vs Market"
    elif rules.quantity_tiers_enabled:
        quantity = row["_quantity"]
        if quantity >= 15:
            quantity_tier = "15+ copies"
            quantity_markup = rules.fifteen_plus_markup
        elif quantity >= 4:
            quantity_tier = "4+ copies"
            quantity_markup = rules.four_plus_markup

        if quantity_markup > 0:
            marked_up = proposed * (1 + quantity_markup)
            if rules.cap_quantity_markup_at_market and market > 0:
                marked_up = min(marked_up, market)
            marked_up = max(proposed, marked_up)
            if marked_up > proposed + 0.004:
                proposed = marked_up
                decision = f"{quantity_tier} premium"

    return pd.Series(
        {
            "Proposed Price": round(proposed + 1e-9, 2),
            "Base Pricing": rules.matching_mode,
            "Pricing Decision": decision,
            "Applied Floor": floor,
            "Floor Group": floor_group,
            "Manual Review": (manual or safety_hold) and not ignored_set,
            "Manual Override": False,
            "Ignored Set": ignored_set,
            "Safety Alert": safety_alert,
            "Low vs Market Gap": low_market_gap,
            "Quantity Tier": quantity_tier,
            "Quantity Markup": quantity_markup,
        }
    )


def calculate_inventory(source: pd.DataFrame, rules: PricingRules) -> pd.DataFrame:
    frame = source.copy()
    frame["_quantity"] = safe_numeric(frame["Total Quantity"]).clip(lower=0).astype(int)
    frame["_low"] = safe_numeric(frame["TCG Low Price"])
    frame["_low_shipping"] = safe_numeric(frame["TCG Low Price With Shipping"])
    frame["_current_price"] = safe_numeric(frame["TCG Marketplace Price"])
    frame["_market"] = safe_numeric(frame["TCG Market Price"])
    frame["_is_foil"] = is_foil(frame["Condition"])
    frame["_override_key"] = (
        frame["TCGplayer Id"].astype(str)
        + "|"
        + frame["Condition"].astype(str)
        + "|"
        + frame["Product Name"].astype(str)
    )

    decisions = frame.apply(proposed_price_for_row, axis=1, rules=rules)
    frame = pd.concat([frame, decisions], axis=1)
    frame["Current Value"] = frame["_quantity"] * frame["_current_price"]
    frame["Proposed Value"] = frame["_quantity"] * frame["Proposed Price"]
    frame["Value Delta"] = frame["Proposed Value"] - frame["Current Value"]
    frame["Price Changed"] = (
        ~frame["Manual Review"]
        & ((frame["Proposed Price"] - frame["_current_price"]).abs() >= 0.005)
    )
    frame["Finish"] = frame["_is_foil"].map({True: "Foil", False: "Normal"})
    return frame


def apply_manual_overrides(
    calculated: pd.DataFrame, overrides: dict[str, float]
) -> pd.DataFrame:
    frame = calculated.copy()
    for override_key, override_price in overrides.items():
        mask = (
            (frame["_override_key"] == override_key)
            & ~frame["Ignored Set"]
        )
        if not mask.any():
            continue
        frame.loc[mask, "Proposed Price"] = round(float(override_price), 2)
        frame.loc[mask, "Pricing Decision"] = "Manual override"
        frame.loc[mask, "Manual Review"] = False
        frame.loc[mask, "Manual Override"] = True

    frame["Proposed Value"] = frame["_quantity"] * frame["Proposed Price"]
    frame["Value Delta"] = frame["Proposed Value"] - frame["Current Value"]
    frame["Price Changed"] = (
        ~frame["Manual Review"]
        & ((frame["Proposed Price"] - frame["_current_price"]).abs() >= 0.005)
    )
    return frame


def apply_final_price_offset(
    calculated: pd.DataFrame, rules: PricingRules
) -> pd.DataFrame:
    frame = calculated.copy()
    frame["Rule Price"] = frame["Proposed Price"]
    frame["Final Offset"] = 0.0
    frame["Offset Applied"] = False

    if not rules.final_offset_enabled:
        return frame

    eligible = ~frame["Manual Review"] & ~frame["Ignored Set"]
    adjusted = frame.loc[eligible, "Proposed Price"] * (
        1 + rules.final_price_offset
    )
    adjusted = adjusted.where(
        frame.loc[eligible, "Proposed Price"] <= 0,
        adjusted.clip(lower=0.01),
    )
    frame.loc[eligible, "Proposed Price"] = (adjusted + 1e-9).round(2)
    frame.loc[eligible, "Final Offset"] = rules.final_price_offset
    frame.loc[eligible, "Offset Applied"] = True

    offset_label = f"final export offset ({rules.final_price_offset:+.0%})"
    frame.loc[eligible, "Pricing Decision"] = (
        frame.loc[eligible, "Pricing Decision"].astype(str)
        + "; "
        + offset_label
    )
    frame["Proposed Value"] = frame["_quantity"] * frame["Proposed Price"]
    frame["Value Delta"] = frame["Proposed Value"] - frame["Current Value"]
    frame["Price Changed"] = (
        ~frame["Manual Review"]
        & ~frame["Ignored Set"]
        & ((frame["Proposed Price"] - frame["_current_price"]).abs() >= 0.005)
    )
    return frame


def tcgplayer_update_csv(calculated: pd.DataFrame, headers: Iterable[str]) -> bytes:
    changed = calculated.loc[calculated["Price Changed"]].copy()
    export = changed.loc[:, list(headers)].copy()
    export["Total Quantity"] = ""
    export["Add to Quantity"] = "0"
    export["TCG Marketplace Price"] = changed["Proposed Price"].map(
        lambda value: f"{value:.4f}"
    )
    export["Photo URL"] = ""
    return export.to_csv(index=False, quoting=1, lineterminator="\r\n").encode("utf-8")


def analysis_csv(calculated: pd.DataFrame, headers: Iterable[str]) -> bytes:
    analysis_columns = [
        "Rule Price",
        "Proposed Price",
        "Final Offset",
        "Offset Applied",
        "Base Pricing",
        "Pricing Decision",
        "Applied Floor",
        "Floor Group",
        "Current Value",
        "Proposed Value",
        "Value Delta",
        "Price Changed",
        "Manual Review",
        "Manual Override",
        "Ignored Set",
        "Safety Alert",
        "Low vs Market Gap",
        "Finish",
        "Quantity Tier",
        "Quantity Markup",
    ]
    export = calculated.loc[:, [*headers, *analysis_columns]].copy()
    return export.to_csv(index=False, quoting=1, lineterminator="\r\n").encode("utf-8")


def rules_sidebar(set_options: Iterable[str] = ()) -> PricingRules:
    with st.sidebar:
        st.markdown('<p class="lava-kicker">02 / Pricing logic</p>', unsafe_allow_html=True)
        st.header("Build the rule")
        matching_mode = st.radio(
            "Base pricing",
            options=["Match Low", "Match Market", "Do not match"],
            index=0,
            help=(
                "Choose the reference price before floors and optional quantity "
                "premiums are applied."
            ),
        )
        threshold = st.number_input(
            "Shipping threshold",
            min_value=0.0,
            value=5.0,
            step=0.25,
            format="%.2f",
            disabled=matching_mode != "Match Low",
            help="Below this value use TCG Low. At or above it use Low + Shipping.",
        )
        if matching_mode == "Match Low":
            rule_summary = (
                "<strong>Below threshold:</strong> TCG Low<br>"
                "<strong>At or above threshold:</strong> TCG Low + Shipping"
            )
        elif matching_mode == "Match Market":
            rule_summary = (
                "<strong>Reference:</strong> TCG Market Price<br>"
                "<strong>Fallback:</strong> Current store price"
            )
        else:
            rule_summary = (
                "<strong>Reference:</strong> Current store price<br>"
                "<strong>Matching:</strong> Disabled"
            )
        st.markdown(
            f'<div class="rule-card">{rule_summary}</div>',
            unsafe_allow_html=True,
        )

        st.subheader("Set scope")
        available_sets = sorted(
            {
                str(set_name).strip()
                for set_name in set_options
                if str(set_name).strip()
            }
        )
        default_ignored = [
            set_name
            for set_name in available_sets
            if "deep trouble" in set_name.lower()
        ]
        if "ignored_sets" not in st.session_state:
            st.session_state["ignored_sets"] = default_ignored
        else:
            st.session_state["ignored_sets"] = [
                set_name
                for set_name in st.session_state["ignored_sets"]
                if set_name in available_sets
            ]
        excluded_sets = st.multiselect(
            "Ignore sets",
            options=available_sets,
            key="ignored_sets",
            placeholder="Choose sets to exclude",
            help=(
                "Ignored sets keep their current store prices and are excluded "
                "from price updates."
            ),
        )
        if excluded_sets:
            st.markdown(
                '<div class="rule-card"><strong>Excluded from pricing:</strong> '
                + ", ".join(excluded_sets)
                + "</div>",
                unsafe_allow_html=True,
            )

        default_specific_floor_sets = [
            LORCANA_SET_NAMES[str(set_number)]
            for set_number in range(1, 9)
            if LORCANA_SET_NAMES[str(set_number)] in available_sets
        ]
        try:
            selected_specific_sets = st.session_state["specific_floor_sets"]
        except KeyError:
            selected_specific_sets = default_specific_floor_sets
        st.session_state["specific_floor_sets"] = [
            set_name
            for set_name in selected_specific_sets
            if set_name in available_sets
        ]
        specific_floor_sets = st.multiselect(
            "Sets with custom floors",
            options=available_sets,
            key="specific_floor_sets",
            placeholder="Choose sets for the second floor group",
            help=(
                "Selected sets use the custom floor profile below. All other "
                "sets use the default profile. Ignored sets remain unchanged."
            ),
        )
        if specific_floor_sets:
            st.markdown(
                '<div class="rule-card"><strong>Custom floor profile:</strong> '
                + ", ".join(specific_floor_sets)
                + "</div>",
                unsafe_allow_html=True,
            )

        st.subheader("Low-price safety")
        low_safety_enabled = st.toggle(
            "Protect suspicious Low prices",
            value=True,
            help=(
                "Flag and exclude Match Low rows when TCG Low is unusually far "
                "below Market Price."
            ),
        )
        low_market_gap_threshold = (
            st.number_input(
                "Warning gap (%)",
                min_value=1.0,
                max_value=90.0,
                value=20.0,
                step=1.0,
                format="%.0f",
                disabled=not low_safety_enabled,
                help="A 20% setting flags Low prices that are 20% or more below Market.",
            )
            / 100
        )
        low_safety_market_minimum = st.number_input(
            "Minimum Market Price",
            min_value=0.0,
            value=5.0,
            step=0.50,
            format="%.2f",
            disabled=not low_safety_enabled,
            help=(
                "Only run the gap check on cards at or above this Market Price, "
                "avoiding normal penny-card shipping gaps."
            ),
        )
        st.markdown(
            '<div class="rule-card"><strong>Safety action:</strong> hold the current '
            "store price and require manual review before export.<br>"
            "<strong>Default scope:</strong> Market Price of $5 or more.</div>",
            unsafe_allow_html=True,
        )

        st.subheader("Default floor profile")
        st.caption("Applies to every set not selected for custom floors.")
        st.markdown("**Normal floors**")
        normal_left, normal_right = st.columns(2)
        normal_floors = {
            "Common": normal_left.number_input(
                "Common", 0.0, value=0.07, step=0.01, format="%.2f", key="normal_common_v3"
            ),
            "Uncommon": normal_right.number_input(
                "Uncommon", 0.0, value=0.09, step=0.01, format="%.2f", key="normal_uncommon_v3"
            ),
            "Rare": normal_left.number_input(
                "Rare", 0.0, value=0.12, step=0.01, format="%.2f", key="normal_rare_v3"
            ),
            "Super Rare": normal_right.number_input(
                "Super Rare", 0.0, value=0.15, step=0.01, format="%.2f", key="normal_super_v3"
            ),
        }

        st.markdown("**Foil floors**")
        foil_left, foil_right = st.columns(2)
        foil_floors = {
            "Common": foil_left.number_input(
                "Common foil", 0.0, value=0.20, step=0.01, format="%.2f", key="foil_common_v4"
            ),
            "Uncommon": foil_right.number_input(
                "Uncommon foil",
                0.0,
                value=0.30,
                step=0.01,
                format="%.2f",
                key="foil_uncommon_v4",
            ),
            "Rare": foil_left.number_input(
                "Rare foil", 0.0, value=0.40, step=0.01, format="%.2f", key="foil_rare_v4"
            ),
            "Super Rare": foil_right.number_input(
                "Super Rare foil", 0.0, value=0.50, step=0.01, format="%.2f", key="foil_super_v4"
            ),
        }

        st.subheader("Selected-set floor profile")
        if specific_floor_sets:
            st.caption("Applies only to: " + ", ".join(specific_floor_sets))
        else:
            st.caption("Choose one or more sets above to activate this profile.")
        st.markdown("**Normal floors**")
        specific_normal_left, specific_normal_right = st.columns(2)
        specific_normal_floors = {
            "Common": specific_normal_left.number_input(
                "Selected Common",
                0.0,
                value=0.05,
                step=0.01,
                format="%.2f",
                key="specific_normal_common_v2",
                disabled=not specific_floor_sets,
            ),
            "Uncommon": specific_normal_right.number_input(
                "Selected Uncommon",
                0.0,
                value=0.08,
                step=0.01,
                format="%.2f",
                key="specific_normal_uncommon_v2",
                disabled=not specific_floor_sets,
            ),
            "Rare": specific_normal_left.number_input(
                "Selected Rare",
                0.0,
                value=0.10,
                step=0.01,
                format="%.2f",
                key="specific_normal_rare_v3",
                disabled=not specific_floor_sets,
            ),
            "Super Rare": specific_normal_right.number_input(
                "Selected Super Rare",
                0.0,
                value=0.13,
                step=0.01,
                format="%.2f",
                key="specific_normal_super_v3",
                disabled=not specific_floor_sets,
            ),
        }

        st.markdown("**Foil floors**")
        specific_foil_left, specific_foil_right = st.columns(2)
        specific_foil_floors = {
            "Common": specific_foil_left.number_input(
                "Selected Common foil",
                0.0,
                value=0.20,
                step=0.01,
                format="%.2f",
                key="specific_foil_common_v2",
                disabled=not specific_floor_sets,
            ),
            "Uncommon": specific_foil_right.number_input(
                "Selected Uncommon foil",
                0.0,
                value=0.25,
                step=0.01,
                format="%.2f",
                key="specific_foil_uncommon_v2",
                disabled=not specific_floor_sets,
            ),
            "Rare": specific_foil_left.number_input(
                "Selected Rare foil",
                0.0,
                value=0.30,
                step=0.01,
                format="%.2f",
                key="specific_foil_rare_v2",
                disabled=not specific_floor_sets,
            ),
            "Super Rare": specific_foil_right.number_input(
                "Selected Super Rare foil",
                0.0,
                value=0.35,
                step=0.01,
                format="%.2f",
                key="specific_foil_super_v2",
                disabled=not specific_floor_sets,
            ),
        }

        manual = st.multiselect(
            "Manual-pricing rarities",
            options=["Enchanted", "Iconic", "Epic", "Promo", "Legendary"],
            default=MANUAL_DEFAULTS,
            help=(
                "Manual rows keep their current store price and are excluded "
                "from updates until individually approved."
            ),
        )

        st.subheader("Quantity tiers")
        quantity_tiers_enabled = st.toggle(
            "Enable quantity premiums",
            value=False,
            help="Apply an optional premium when active quantity reaches a configured tier.",
        )
        tier_left, tier_right = st.columns(2)
        four_plus_markup = (
            tier_left.number_input(
                "4+ copies premium (%)",
                min_value=0.0,
                max_value=50.0,
                value=5.0,
                step=1.0,
                format="%.0f",
                disabled=not quantity_tiers_enabled,
                help="Percentage added to the base rule price.",
            )
            / 100
        )
        fifteen_plus_markup = (
            tier_right.number_input(
                "15+ copies premium (%)",
                min_value=0.0,
                max_value=50.0,
                value=10.0,
                step=1.0,
                format="%.0f",
                disabled=not quantity_tiers_enabled,
                help="Overrides the 4+ tier rather than stacking with it.",
            )
            / 100
        )
        cap_quantity_markup_at_market = st.checkbox(
            "Never exceed Market Price",
            value=True,
            disabled=not quantity_tiers_enabled,
        )
        st.markdown(
            '<div class="rule-card"><strong>Tier behavior:</strong> 15+ overrides '
            "4+; premiums never reduce the floor or matching price.</div>",
            unsafe_allow_html=True,
        )

        st.subheader("Final price offset")
        final_offset_enabled = st.toggle(
            "Apply final export offset",
            value=False,
            key="final_offset_enabled_v4",
            help=(
                "Optionally adjusts the price produced by all existing matching, "
                "floor, premium, and review rules."
            ),
        )
        final_price_offset = (
            st.number_input(
                "Final export adjustment (%)",
                min_value=-99.0,
                max_value=100.0,
                value=0.0,
                step=1.0,
                format="%.0f",
                disabled=not final_offset_enabled,
                help=(
                    "Applied to the fully calculated rule price immediately "
                    "before export. Negative values reduce that price."
                ),
            )
            / 100
        )
        st.markdown(
            '<div class="rule-card"><strong>Export baseline:</strong> Before '
            "offset, the complete rule-calculated price. With offset off or at "
            "0%, Final price equals Before offset. Safety-held rows and ignored "
            "sets remain protected.</div>",
            unsafe_allow_html=True,
        )
        st.caption("Rule controls recalculate the inventory instantly.")

    return PricingRules(
        matching_mode=matching_mode,
        threshold=threshold,
        normal_floors=normal_floors,
        foil_floors=foil_floors,
        specific_floor_sets=frozenset(specific_floor_sets),
        specific_normal_floors=specific_normal_floors,
        specific_foil_floors=specific_foil_floors,
        manual_rarities=frozenset(manual),
        excluded_sets=frozenset(excluded_sets),
        low_safety_enabled=low_safety_enabled,
        low_market_gap_threshold=low_market_gap_threshold,
        low_safety_market_minimum=low_safety_market_minimum,
        quantity_tiers_enabled=quantity_tiers_enabled,
        four_plus_markup=four_plus_markup,
        fifteen_plus_markup=fifteen_plus_markup,
        cap_quantity_markup_at_market=cap_quantity_markup_at_market,
        final_offset_enabled=final_offset_enabled,
        final_price_offset=final_price_offset,
    )


def render_value_breakdown(calculated: pd.DataFrame) -> None:
    active = calculated.loc[calculated["_quantity"] > 0].copy()
    breakdown = (
        active.groupby(["Rarity", "Finish"], dropna=False)
        .agg(
            Units=("_quantity", "sum"),
            Current_Value=("Current Value", "sum"),
            Proposed_Value=("Proposed Value", "sum"),
        )
        .reset_index()
    )
    breakdown["Delta"] = breakdown["Proposed_Value"] - breakdown["Current_Value"]
    st.dataframe(
        breakdown,
        width="stretch",
        hide_index=True,
        column_config={
            "Rarity": "Rarity",
            "Finish": "Finish",
            "Units": st.column_config.NumberColumn("Units", format="%d"),
            "Current_Value": st.column_config.NumberColumn("Current value", format="$%.2f"),
            "Proposed_Value": st.column_config.NumberColumn("Proposed value", format="$%.2f"),
            "Delta": st.column_config.NumberColumn("Delta", format="$%.2f"),
        },
    )


def render_manual_override_controls(calculated: pd.DataFrame) -> None:
    overrides = dict(st.session_state.get("price_overrides", {}))
    flagged = calculated.loc[
        calculated["Safety Alert"] & (calculated["_quantity"] > 0)
    ].copy()

    labels = {
        row["_override_key"]: (
            f'{row["Product Name"]} · {row["Set Name"]} · {row["Condition"]} '
            f'· current {money(row["_current_price"])}'
        )
        for _, row in flagged.iterrows()
    }
    option_keys = sorted(labels, key=lambda key: labels[key].lower())

    with st.expander("Manual price override", expanded=False):
        st.caption(
            "Only safety-flagged cards with current or incoming inventory appear "
            "here for review before export."
        )
        if flagged.empty:
            st.success("No catalog rows are currently flagged.")
            return

        selected_key = st.selectbox(
            "Card",
            options=option_keys,
            format_func=lambda key: labels[key],
        )
        selected_row = flagged.loc[
            flagged["_override_key"] == selected_key
        ].iloc[0]

        st.markdown("#### Card assessment")
        st.caption(
            f'{selected_row["Set Name"]} · {selected_row["Rarity"]} · '
            f'{selected_row["Condition"]} · '
            f'{int(selected_row["_quantity"]):,} projected copy/copies'
        )
        price_metrics = st.columns(4)
        price_metrics[0].metric(
            "Current store price", money(float(selected_row["_current_price"]))
        )
        price_metrics[1].metric("TCG Low", money(float(selected_row["_low"])))
        price_metrics[2].metric(
            "Low + shipping",
            (
                money(float(selected_row["_low_shipping"]))
                if selected_row["_low_shipping"] > 0
                else "Unavailable"
            ),
        )
        price_metrics[3].metric(
            "TCG Market", money(float(selected_row["_market"]))
        )
        assessment_metrics = st.columns(3)
        assessment_metrics[0].metric(
            "Low below Market",
            f'{float(selected_row["Low vs Market Gap"]):.1%}',
        )
        assessment_metrics[1].metric(
            "Rule price", money(float(selected_row["Proposed Price"]))
        )
        assessment_metrics[2].metric(
            "Current listing value",
            money(
                float(selected_row["_current_price"])
                * int(selected_row["_quantity"])
            ),
        )
        st.info(
            f'Current action: {selected_row["Pricing Decision"]}. '
            "Applying an override confirms that you reviewed this safety alert.",
            icon=":material/fact_check:",
        )

        default_override = float(selected_row["Proposed Price"])
        if default_override < 0.01:
            default_override = float(selected_row["_market"])
        starting_price = max(
            0.01,
            float(overrides.get(selected_key, default_override)),
        )
        override_price = st.number_input(
            "Exact override price",
            min_value=0.01,
            value=float(starting_price),
            step=0.01,
            format="%.2f",
            key=f"override_price_{abs(hash(selected_key))}",
        )
        apply_col, remove_col, clear_col = st.columns(3)
        if apply_col.button("Apply override", type="primary", width="stretch"):
            st.session_state["price_overrides"] = {
                **overrides,
                selected_key: round(float(override_price), 2),
            }
            st.rerun()
        if remove_col.button(
            "Remove selected",
            disabled=selected_key not in overrides,
            width="stretch",
        ):
            overrides.pop(selected_key, None)
            st.session_state["price_overrides"] = overrides
            st.rerun()
        if clear_col.button(
            "Clear all",
            disabled=not overrides,
            width="stretch",
        ):
            st.session_state["price_overrides"] = {}
            st.rerun()

        active_override_count = sum(key in labels for key in overrides)
        if active_override_count:
            st.success(
                f"{active_override_count:,} manual override(s) will be included "
                "in the calculations and export."
            )


def render_pricing_workspace() -> None:
    rules = rules_sidebar()

    st.markdown("### Pricing / Load inventory")
    uploaded = st.file_uploader(
        "TCGplayer My Pricing or Custom Export CSV",
        type=["csv"],
        help="The app validates the TCGplayer headers before calculating prices.",
    )

    if uploaded is None:
        st.info(
            "Choose a TCGplayer CSV to start. Your current rule settings are ready.",
            icon=":material/upload_file:",
        )
        return

    try:
        source = read_inventory(uploaded)
    except ValueError as exc:
        st.error(str(exc), icon=":material/error:")
        return

    calculated = calculate_inventory(source, rules)
    render_manual_override_controls(calculated)
    calculated = apply_manual_overrides(
        calculated, st.session_state.get("price_overrides", {})
    )
    calculated = apply_final_price_offset(calculated, rules)
    active = calculated.loc[calculated["_quantity"] > 0]
    active_units = int(active["_quantity"].sum())
    current_value = float(active["Current Value"].sum())
    proposed_value = float(active["Proposed Value"].sum())
    changed = calculated.loc[calculated["Price Changed"]]
    manual = active.loc[active["Manual Review"]]
    safety_alerts = active.loc[active["Safety Alert"]]
    safety_holds = safety_alerts.loc[safety_alerts["Manual Review"]]

    st.caption(f"{uploaded.name} · {len(source):,} source rows")
    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Active units",
        f"{active_units:,}",
        f"{len(active):,} active rows",
        delta_color="off",
    )
    metric_columns[1].metric("Current listing value", money(current_value))
    metric_columns[2].metric(
        "Proposed listing value",
        money(proposed_value),
        money(proposed_value - current_value),
    )
    metric_columns[3].metric(
        "Rows to update",
        f"{len(changed):,}",
        f"{len(manual):,} manual reviews",
        delta_color="off",
    )
    if not safety_alerts.empty:
        st.warning(
            f"{len(safety_alerts):,} active row(s) have a suspicious TCG Low price. "
            f"{len(safety_holds):,} remain held and excluded from the update CSV; "
            "a manual override releases a reviewed row.",
            icon=":material/shield:",
        )

    overview_tab, preview_tab, export_tab = st.tabs(
        ["Inventory overview", "Change review", "Export"]
    )

    with overview_tab:
        st.subheader("Value distribution")
        render_value_breakdown(calculated)

    with preview_tab:
        filter_columns = st.columns([2.4, 1, 1, 1])
        query = filter_columns[0].text_input(
            "Search",
            placeholder="Card, set, rarity, number...",
        )
        rarity_options = sorted(calculated["Rarity"].fillna("None").unique().tolist())
        rarity_filter = filter_columns[1].selectbox(
            "Rarity", ["All", *rarity_options]
        )
        finish_filter = filter_columns[2].selectbox(
            "Finish", ["All", "Normal", "Foil"]
        )
        changed_only = filter_columns[3].toggle("Changes only", value=True)

        view = calculated.copy()
        if changed_only:
            view = view.loc[view["Price Changed"] | view["Manual Override"]]
        if rarity_filter != "All":
            view = view.loc[view["Rarity"] == rarity_filter]
        if finish_filter != "All":
            view = view.loc[view["Finish"] == finish_filter]
        if query:
            search_columns = [
                "Product Name",
                "Set Name",
                "Rarity",
                "Condition",
                "Number",
            ]
            haystack = (
                view[search_columns]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
                .str.lower()
            )
            view = view.loc[haystack.str.contains(query.lower(), regex=False)]

        display = view[
            [
                "Product Name",
                "Set Name",
                "Rarity",
                "Finish",
                "Floor Group",
                "Applied Floor",
                "Total Quantity",
                "TCG Low Price",
                "TCG Low Price With Shipping",
                "TCG Marketplace Price",
                "Rule Price",
                "Proposed Price",
                "Final Offset",
                "Offset Applied",
                "Pricing Decision",
                "Manual Override",
                "Safety Alert",
                "Low vs Market Gap",
                "Quantity Tier",
                "Quantity Markup",
                "Value Delta",
            ]
        ].copy()
        for column in [
            "Total Quantity",
            "TCG Low Price",
            "TCG Low Price With Shipping",
            "TCG Marketplace Price",
        ]:
            display[column] = safe_numeric(display[column])

        st.dataframe(
            display,
            width="stretch",
            height=620,
            hide_index=True,
            column_config={
                "Product Name": "Card",
                "Set Name": "Set",
                "Total Quantity": st.column_config.NumberColumn("Qty", format="%d"),
                "TCG Low Price": st.column_config.NumberColumn("Low", format="$%.2f"),
                "TCG Low Price With Shipping": st.column_config.NumberColumn(
                    "Low + shipping", format="$%.2f"
                ),
                "TCG Marketplace Price": st.column_config.NumberColumn(
                    "Current", format="$%.2f"
                ),
                "Proposed Price": st.column_config.NumberColumn(
                    "Final price", format="$%.2f"
                ),
                "Rule Price": st.column_config.NumberColumn(
                    "Before offset", format="$%.2f"
                ),
                "Applied Floor": st.column_config.NumberColumn(
                    "Floor", format="$%.2f"
                ),
                "Value Delta": st.column_config.NumberColumn("Value delta", format="$%.2f"),
                "Safety Alert": st.column_config.CheckboxColumn("Safety alert"),
                "Manual Override": st.column_config.CheckboxColumn("Override"),
                "Low vs Market Gap": st.column_config.NumberColumn(
                    "Low below Market", format="percent"
                ),
                "Quantity Markup": st.column_config.NumberColumn(
                    "Tier markup", format="percent"
                ),
                "Final Offset": st.column_config.NumberColumn(
                    "Final offset", format="percent"
                ),
                "Offset Applied": st.column_config.CheckboxColumn(
                    "Offset applied"
                ),
            },
        )

    with export_tab:
        st.subheader("Download reviewed results")
        st.markdown(
            '<div class="export-note"><strong>Safe price update:</strong> changed '
            "active rows only. Total Quantity is cleared and Add to Quantity is set "
            "to zero, so the import cannot replace your inventory counts.</div>",
            unsafe_allow_html=True,
        )
        st.write("")
        export_columns = st.columns(2)
        file_stem = uploaded.name.rsplit(".", 1)[0]
        export_columns[0].download_button(
            "Download TCGplayer update CSV",
            data=tcgplayer_update_csv(calculated, source.columns),
            file_name=f"{file_stem}_price_updates.csv",
            mime="text/csv",
            disabled=changed.empty,
            type="primary",
            width="stretch",
        )
        export_columns[1].download_button(
            "Download full analysis CSV",
            data=analysis_csv(calculated, source.columns),
            file_name=f"{file_stem}_analysis.csv",
            mime="text/csv",
            width="stretch",
        )
        if changed.empty:
            st.success("No active prices need adjustment under the current rules.")
        else:
            st.caption(
                f"The TCGplayer update contains {len(changed):,} price changes. "
                f"{len(manual):,} active manual-pricing rows are excluded."
            )


def render_inventory_workspace() -> None:
    st.markdown("### Add Inventory / Load files")
    upload_columns = st.columns(2)
    catalog_file = upload_columns[0].file_uploader(
        "Current TCGplayer catalog CSV",
        type=["csv"],
        key="inventory_catalog_upload",
        help=(
            "Use a current My Pricing or Custom Export. It supplies TCGplayer IDs, "
            "existing quantities, and listing prices."
        ),
    )
    scan_files = upload_columns[1].file_uploader(
        "Scanner CSV files",
        type=["csv"],
        accept_multiple_files=True,
        key="inventory_scan_uploads",
        help=(
            "Upload one or more Dreamborn scanner exports. Duplicate cards across "
            "files are combined."
        ),
    )

    if catalog_file is None or not scan_files:
        st.info(
            "Choose the current TCGplayer catalog and at least one scanner CSV.",
            icon=":material/upload_file:",
        )
        return

    try:
        source = read_inventory(catalog_file)
    except ValueError as exc:
        st.error(str(exc), icon=":material/error:")
        return

    scan_frames: list[pd.DataFrame] = []
    scan_errors: list[str] = []
    for scan_file in scan_files:
        try:
            scan_frames.append(read_scan_file(scan_file))
        except ValueError as exc:
            scan_errors.append(str(exc))

    if scan_errors:
        for error in scan_errors:
            st.error(error, icon=":material/error:")
    if not scan_frames:
        return

    scans = pd.concat(scan_frames, ignore_index=True)
    matched, unmatched = match_scans_to_catalog(scans, source)
    matched_units = (
        int(matched["Quantity to Add"].sum()) if not matched.empty else 0
    )
    unmatched_units = (
        int(unmatched["Scan Quantity"].clip(lower=0).sum())
        if not unmatched.empty
        else 0
    )

    st.caption(
        f"{catalog_file.name} · {len(source):,} catalog rows · "
        f"{len(scan_files):,} scanner file(s)"
    )
    metric_columns = st.columns(4)
    metric_columns[0].metric("Scanned units", f"{matched_units + unmatched_units:,}")
    metric_columns[1].metric(
        "Matched units",
        f"{matched_units:,}",
        f"{len(matched):,} catalog rows",
        delta_color="off",
    )
    metric_columns[2].metric(
        "Unmatched units",
        f"{unmatched_units:,}",
        f"{len(unmatched):,} scan rows",
        delta_color="off",
    )
    metric_columns[3].metric(
        "Resulting matched qty",
        (
            f"{int(matched['Resulting Quantity'].sum()):,}"
            if not matched.empty
            else "0"
        ),
        "across matched rows",
        delta_color="off",
    )

    if not unmatched.empty:
        st.warning(
            f"{len(unmatched):,} scanner row(s) could not be matched and will be "
            "excluded from the export. Review them before importing.",
            icon=":material/warning:",
        )

    overview_tab, review_tab, export_tab = st.tabs(
        ["Inventory overview", "Change review", "Export"]
    )

    with overview_tab:
        st.subheader("Incoming inventory")
        if matched.empty:
            st.info("No scanned cards matched the current TCGplayer catalog.")
        else:
            set_summary = (
                matched.groupby(["Set Name", "Finish"], dropna=False)
                .agg(
                    Cards=("TCGplayer Id", "count"),
                    Units=("Quantity to Add", "sum"),
                )
                .reset_index()
                .sort_values(["Units", "Set Name"], ascending=[False, True])
            )
            st.dataframe(
                set_summary,
                width="stretch",
                hide_index=True,
                column_config={
                    "Cards": st.column_config.NumberColumn(
                        "Catalog rows", format="%d"
                    ),
                    "Units": st.column_config.NumberColumn(
                        "Units to add", format="%d"
                    ),
                },
            )

    with review_tab:
        st.subheader("Quantity changes")
        query = st.text_input(
            "Search scanned cards",
            placeholder="Card, set, rarity, number...",
            key="inventory_review_search",
        )
        review = matched.copy()
        if query and not review.empty:
            haystack = (
                review[
                    ["Product Name", "Set Name", "Rarity", "Condition", "Number"]
                ]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
                .str.lower()
            )
            review = review.loc[
                haystack.str.contains(query.lower(), regex=False)
            ]

        if review.empty:
            st.info("No matched quantity changes to review.")
        else:
            st.dataframe(
                review[
                    [
                        "Product Name",
                        "Set Name",
                        "Number",
                        "Rarity",
                        "Finish",
                        "Current Quantity",
                        "Quantity to Add",
                        "Resulting Quantity",
                        "Current Price",
                        "TCG Low",
                        "TCG Market",
                        "Source Files",
                    ]
                ],
                width="stretch",
                height=600,
                hide_index=True,
                column_config={
                    "Product Name": "Card",
                    "Set Name": "Set",
                    "Current Quantity": st.column_config.NumberColumn(
                        "Current qty", format="%d"
                    ),
                    "Quantity to Add": st.column_config.NumberColumn(
                        "Add", format="+%d"
                    ),
                    "Resulting Quantity": st.column_config.NumberColumn(
                        "Resulting qty", format="%d"
                    ),
                    "Current Price": st.column_config.NumberColumn(
                        "Store price", format="$%.2f"
                    ),
                    "TCG Low": st.column_config.NumberColumn(
                        "TCG Low", format="$%.2f"
                    ),
                    "TCG Market": st.column_config.NumberColumn(
                        "Market", format="$%.2f"
                    ),
                },
            )

        if not unmatched.empty:
            st.subheader("Unmatched scanner rows")
            unmatched_display = unmatched[
                [
                    "Source File",
                    "Scan Row",
                    "Set Number",
                    "Set Name",
                    "Card Number",
                    "Product Name",
                    "Variant",
                    "Scan Quantity",
                    "Reason",
                ]
            ].copy()
            st.dataframe(
                unmatched_display,
                width="stretch",
                hide_index=True,
                column_config={
                    "Scan Quantity": st.column_config.NumberColumn(
                        "Quantity", format="%d"
                    )
                },
            )

    with export_tab:
        st.subheader("Download reviewed inventory update")
        st.markdown(
            '<div class="export-note"><strong>Safe quantity update:</strong> matched '
            "rows only. Total Quantity is cleared and Add to Quantity contains the "
            "scanned count, so existing store inventory is not replaced.</div>",
            unsafe_allow_html=True,
        )
        st.write("")
        export_columns = st.columns(2)
        file_stem = catalog_file.name.rsplit(".", 1)[0]
        export_columns[0].download_button(
            "Download TCGplayer inventory CSV",
            data=(
                inventory_update_csv(matched, source, source.columns)
                if not matched.empty
                else b""
            ),
            file_name=f"{file_stem}_inventory_additions.csv",
            mime="text/csv",
            disabled=matched.empty,
            type="primary",
            width="stretch",
        )
        export_columns[1].download_button(
            "Download quantity analysis CSV",
            data=matched.to_csv(index=False).encode("utf-8"),
            file_name=f"{file_stem}_inventory_analysis.csv",
            mime="text/csv",
            disabled=matched.empty,
            width="stretch",
        )
        if not matched.empty:
            st.caption(
                f"The TCGplayer update contains {len(matched):,} catalog rows and "
                f"adds {matched_units:,} units. {len(unmatched):,} unmatched scan "
                "rows are excluded."
            )


def render_unified_workspace() -> None:
    st.markdown("### Load your current catalog")
    catalog_file = st.file_uploader(
        "TCGplayer My Pricing or Custom Export CSV",
        type=["csv"],
        key="shared_catalog_upload",
        help=(
            "Upload this once. Pricing changes and scanner additions both use "
            "the same source catalog."
        ),
    )
    if catalog_file is None:
        st.info(
            "Choose one current TCGplayer export to price listings, add inventory, "
            "or do both.",
            icon=":material/upload_file:",
        )
        return

    try:
        source = read_inventory(catalog_file)
    except ValueError as exc:
        st.error(str(exc), icon=":material/error:")
        return

    rules = rules_sidebar(source["Set Name"].unique())
    st.sidebar.caption(
        "Pricing rules and ignored sets affect price changes only. Scanner "
        "quantity additions remain independent."
    )

    st.caption(f"{catalog_file.name} · {len(source):,} catalog rows")
    inventory_tab, pricing_tab, review_tab = st.tabs(
        ["1. Add Inventory (optional)", "2. Pricing", "3. Review & Export"]
    )

    matched = pd.DataFrame()
    unmatched = pd.DataFrame()
    scan_files = []
    with inventory_tab:
        st.subheader("Add scanned inventory")
        st.caption(
            "Optional first step: matched additions are applied before every "
            "catalog row is evaluated by the pricing rules."
        )
        include_quantity_updates = st.toggle(
            "Include quantity additions in export",
            value=True,
            key="include_quantity_updates",
        )
        scan_files = st.file_uploader(
            "Scanner CSV files (optional)",
            type=["csv"],
            accept_multiple_files=True,
            key="shared_scan_uploads",
            help=(
                "Upload one or more Dreamborn scanner exports. Duplicate cards "
                "across files are combined."
            ),
        )
        if not scan_files:
            st.info(
                "Upload scanner files when you want to add quantities. You can "
                "still use this catalog for price-only changes."
            )
        else:
            scan_frames: list[pd.DataFrame] = []
            for scan_file in scan_files:
                try:
                    scan_frames.append(read_scan_file(scan_file))
                except ValueError as exc:
                    st.error(str(exc), icon=":material/error:")

            if scan_frames:
                scans = pd.concat(scan_frames, ignore_index=True)
                matched, unmatched = match_scans_to_catalog(scans, source)

            matched_units = (
                int(matched["Quantity to Add"].sum()) if not matched.empty else 0
            )
            unmatched_units = (
                int(unmatched["Scan Quantity"].clip(lower=0).sum())
                if not unmatched.empty
                else 0
            )
            metric_columns = st.columns(3)
            metric_columns[0].metric(
                "Scanned units", f"{matched_units + unmatched_units:,}"
            )
            metric_columns[1].metric(
                "Matched units",
                f"{matched_units:,}",
                f"{len(matched):,} catalog rows",
                delta_color="off",
            )
            metric_columns[2].metric(
                "Unmatched units",
                f"{unmatched_units:,}",
                f"{len(unmatched):,} scan rows",
                delta_color="off",
            )

            if not matched.empty:
                st.markdown("#### Quantity changes")
                st.dataframe(
                    matched[
                        [
                            "Product Name",
                            "Set Name",
                            "Number",
                            "Rarity",
                            "Finish",
                            "Current Quantity",
                            "Quantity to Add",
                            "Resulting Quantity",
                            "Source Files",
                        ]
                    ],
                    width="stretch",
                    height=500,
                    hide_index=True,
                    column_config={
                        "Product Name": "Card",
                        "Set Name": "Set",
                        "Current Quantity": st.column_config.NumberColumn(
                            "Current qty", format="%d"
                        ),
                        "Quantity to Add": st.column_config.NumberColumn(
                            "Add", format="+%d"
                        ),
                        "Resulting Quantity": st.column_config.NumberColumn(
                            "Resulting qty", format="%d"
                        ),
                    },
                )

            if not unmatched.empty:
                st.warning(
                    f"{len(unmatched):,} scanner row(s) could not be matched and "
                    "will be excluded from the export.",
                    icon=":material/warning:",
                )
                st.dataframe(
                    unmatched[
                        [
                            "Source File",
                            "Scan Row",
                            "Set Number",
                            "Set Name",
                            "Card Number",
                            "Product Name",
                            "Variant",
                            "Scan Quantity",
                            "Reason",
                        ]
                    ],
                    width="stretch",
                    hide_index=True,
                )

    projected_source = apply_quantity_additions(source, matched)
    calculated = calculate_inventory(projected_source, rules)
    calculated = apply_manual_overrides(
        calculated, st.session_state.get("price_overrides", {})
    )
    calculated = apply_final_price_offset(calculated, rules)

    with pricing_tab:
        st.subheader("Price listings")
        st.caption(
            "Pricing uses the projected quantities after scanner additions and "
            "evaluates every catalog row, including rows currently at zero quantity. "
            "Price exports require current stock or an incoming quantity addition."
        )
        include_price_updates = st.toggle(
            "Include price changes in export",
            value=True,
            key="include_price_updates",
        )
        render_manual_override_controls(calculated)
        active = calculated.loc[calculated["_quantity"] > 0]
        changed = calculated.loc[calculated["Price Changed"]]
        manual = calculated.loc[calculated["Manual Review"]]
        ignored = calculated.loc[calculated["Ignored Set"]]
        safety_alerts = calculated.loc[
            calculated["Safety Alert"] & (calculated["_quantity"] > 0)
        ]
        safety_holds = safety_alerts.loc[safety_alerts["Manual Review"]]
        current_value = float(active["Current Value"].sum())
        proposed_value = float(active["Proposed Value"].sum())

        metric_columns = st.columns(4)
        metric_columns[0].metric(
            "Projected units",
            f"{int(active['_quantity'].sum()):,}",
            f"{len(active):,} active rows",
            delta_color="off",
        )
        metric_columns[1].metric("Value at current prices", money(current_value))
        metric_columns[2].metric(
            "Value at proposed prices",
            money(proposed_value),
            money(proposed_value - current_value),
        )
        metric_columns[3].metric(
            "Price changes",
            f"{len(changed):,}",
            f"{len(manual):,} manual · {len(ignored):,} ignored",
            delta_color="off",
        )
        if not ignored.empty:
            ignored_names = ", ".join(sorted(ignored["Set Name"].unique()))
            st.info(
                f"{len(ignored):,} catalog row(s) from {ignored_names} are keeping "
                "their current prices and are excluded from price updates.",
                icon=":material/filter_alt_off:",
            )
        if not safety_alerts.empty:
            st.warning(
                f"{len(safety_alerts):,} catalog row(s) have a suspicious TCG Low "
                f"price. {len(safety_holds):,} remain held and excluded unless "
                "manually approved.",
                icon=":material/shield:",
            )

        st.markdown("#### Price change review")
        display = calculated.loc[
            calculated["Price Changed"] | calculated["Manual Review"],
            [
                "Product Name",
                "Set Name",
                "Rarity",
                "Finish",
                "Floor Group",
                "Applied Floor",
                "_quantity",
                "TCG Low Price",
                "TCG Market Price",
                "TCG Marketplace Price",
                "Rule Price",
                "Proposed Price",
                "Final Offset",
                "Offset Applied",
                "Pricing Decision",
                "Safety Alert",
            ],
        ].copy()
        for column in [
            "TCG Low Price",
            "TCG Market Price",
            "TCG Marketplace Price",
        ]:
            display[column] = safe_numeric(display[column])
        st.dataframe(
            display,
            width="stretch",
            height=560,
            hide_index=True,
            column_config={
                "Product Name": "Card",
                "Set Name": "Set",
                "_quantity": st.column_config.NumberColumn(
                    "Resulting qty", format="%d"
                ),
                "TCG Low Price": st.column_config.NumberColumn(
                    "TCG Low", format="$%.2f"
                ),
                "TCG Market Price": st.column_config.NumberColumn(
                    "Market", format="$%.2f"
                ),
                "TCG Marketplace Price": st.column_config.NumberColumn(
                    "Current", format="$%.2f"
                ),
                "Proposed Price": st.column_config.NumberColumn(
                    "Final price", format="$%.2f"
                ),
                "Rule Price": st.column_config.NumberColumn(
                    "Before offset", format="$%.2f"
                ),
                "Applied Floor": st.column_config.NumberColumn(
                    "Floor", format="$%.2f"
                ),
                "Safety Alert": st.column_config.CheckboxColumn("Safety alert"),
                "Final Offset": st.column_config.NumberColumn(
                    "Final offset", format="percent"
                ),
                "Offset Applied": st.column_config.CheckboxColumn(
                    "Offset applied"
                ),
            },
        )

    combined = build_combined_review(
        calculated,
        source,
        matched,
        include_price_updates=include_price_updates,
        include_quantity_updates=include_quantity_updates,
    )
    updates = combined.loc[combined["Update Included"]].copy()
    with review_tab:
        st.subheader("Combined changes")
        price_change_count = int(updates["Price Included"].sum())
        quantity_change_count = int(updates["Quantity Included"].sum())
        added_units = int(
            updates["Quantity to Add"].where(
                updates["Quantity Included"], 0
            ).sum()
        )
        metric_columns = st.columns(3)
        metric_columns[0].metric("Rows in export", f"{len(updates):,}")
        metric_columns[1].metric(
            "Price changes", f"{price_change_count:,}", delta_color="off"
        )
        metric_columns[2].metric(
            "Quantity additions",
            f"{added_units:,} units",
            f"{quantity_change_count:,} rows",
            delta_color="off",
        )

        if updates.empty:
            st.success(
                "No price or quantity changes are currently selected for export."
            )
        else:
            st.dataframe(
                updates[
                    [
                        "Product Name",
                        "Set Name",
                        "Number",
                        "Rarity",
                        "Finish",
                        "Floor Group",
                        "Applied Floor",
                        "Current Quantity",
                        "Quantity to Add",
                        "Resulting Quantity",
                        "TCG Marketplace Price",
                        "Rule Price",
                        "Proposed Price",
                        "Final Offset",
                        "Offset Applied",
                        "Pricing Decision",
                        "Price Included",
                        "Quantity Included",
                        "Source Files",
                    ]
                ],
                width="stretch",
                height=620,
                hide_index=True,
                column_config={
                    "Product Name": "Card",
                    "Set Name": "Set",
                    "Current Quantity": st.column_config.NumberColumn(
                        "Current qty", format="%d"
                    ),
                    "Quantity to Add": st.column_config.NumberColumn(
                        "Add", format="+%d"
                    ),
                    "Resulting Quantity": st.column_config.NumberColumn(
                        "Resulting qty", format="%d"
                    ),
                    "TCG Marketplace Price": st.column_config.NumberColumn(
                        "Current price", format="$%.2f"
                    ),
                    "Proposed Price": st.column_config.NumberColumn(
                        "Export price", format="$%.2f"
                    ),
                    "Rule Price": st.column_config.NumberColumn(
                        "Before offset", format="$%.2f"
                    ),
                    "Applied Floor": st.column_config.NumberColumn(
                        "Floor", format="$%.2f"
                    ),
                    "Price Included": st.column_config.CheckboxColumn(
                        "Export price"
                    ),
                    "Quantity Included": st.column_config.CheckboxColumn(
                        "Export qty"
                    ),
                    "Final Offset": st.column_config.NumberColumn(
                        "Final offset", format="percent"
                    ),
                    "Offset Applied": st.column_config.CheckboxColumn(
                        "Offset applied"
                    ),
                },
            )

        st.markdown(
            '<div class="export-note"><strong>One safe import:</strong> Total '
            "Quantity stays blank. Add to Quantity contains only scanner additions, "
            "and the file contains only approved changes. Price-only updates require "
            "current stock or a scanner addition.</div>",
            unsafe_allow_html=True,
        )
        st.write("")
        file_stem = catalog_file.name.rsplit(".", 1)[0]
        download_columns = st.columns(2)
        download_columns[0].download_button(
            "Download combined TCGplayer CSV",
            data=combined_update_csv(combined, source, source.columns),
            file_name=f"{file_stem}_updates.csv",
            mime="text/csv",
            disabled=updates.empty,
            type="primary",
            width="stretch",
        )
        download_columns[1].download_button(
            "Download combined review CSV",
            data=updates.to_csv(index=False).encode("utf-8"),
            file_name=f"{file_stem}_updates_review.csv",
            mime="text/csv",
            disabled=updates.empty,
            width="stretch",
        )


def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        '<p class="lava-kicker">LAVA Collectibles / Inventory workspace</p>',
        unsafe_allow_html=True,
    )
    st.title("Inventory Desk")
    st.markdown(
        '<p class="lava-lede">Use one TCGplayer catalog to adjust pricing, add '
        "scanned inventory, and export every reviewed change together.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span class="privacy-pill">Session-only inventory processing</span>',
        unsafe_allow_html=True,
    )

    render_unified_workspace()


if __name__ == "__main__":
    main()
