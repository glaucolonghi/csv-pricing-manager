# LAVA Inventory Desk

A Streamlit workspace for adjusting TCGplayer prices and quantities from one
shared catalog export.

## Run locally

```sh
cd "/Users/glaucolonghi/Documents/Lorcana Portfolio and Inventory/csv-pricing-manager"
streamlit run streamlit_app.py
```

Streamlit opens the app at `http://localhost:8501`.

## Deploy

The folder is ready for Streamlit Community Cloud:

1. Push the project to a GitHub repository.
2. Create a Streamlit app from `csv-pricing-manager/streamlit_app.py`.
3. No secrets or environment variables are required.

## Workflow

1. Load a TCGplayer `My Pricing` or `Custom Export` CSV.
2. In **Add Inventory (optional)**, upload scanner files before pricing when you
   have new cards. Matched quantities are projected into the catalog first.
3. In **Pricing**, choose Match Low, Match Market, or Do not match. Match Low uses the
   configurable shipping threshold and remains the default.
4. Use **Ignore sets** to keep selected sets at their current prices and exclude
   them from price updates. Deep Trouble is ignored by default when present.
5. Use **Sets with custom floors** to assign selected sets to a second normal
   and foil floor profile. Every unselected set continues to use the default
   profile, while ignored sets remain unchanged. Sets 1-8 are selected by
   default.
6. Keep the default Low-price safety guard or adjust its warning percentage.
   Suspicious Match Low rows are held at their current price and excluded from
   the update CSV for manual review. The default $5 minimum Market Price avoids
   false alerts caused by normal shipping gaps on penny cards.
7. Adjust the default normal floors (`$0.07` Common, `$0.09` Uncommon,
   `$0.12` Rare, `$0.15` Super Rare) and foil floors (`$0.20` Common,
   `$0.30` Uncommon, `$0.40` Rare, `$0.50` Super Rare). The selected-set
   profile starts at `$0.05`/`$0.08`/`$0.10`/`$0.13` for normal cards and
   `$0.20`/`$0.25`/`$0.30`/`$0.35` for foils.
8. Optionally apply configurable premiums to cards with 4+ or 15+ projected copies.
   The 15+ tier overrides the 4+ tier, and premiums can be capped at Market.
9. Final export prices use the complete rule-calculated price as their baseline.
   The optional offset is disabled by default; with it disabled or set to `0%`,
   final price equals `Before offset`. Positive or negative values adjust that
   approved price immediately before export. Matching, floors, quantity tiers,
   safety checks, rarity filters, manual reviews, and ignored sets retain their
   original behavior.
10. Pricing rules evaluate the entire catalog, including rows with zero quantity.
11. Review inventory metrics, value distribution, and every proposed change.
12. Use the manual price override panel to approve an exact price for a
   safety-flagged row with current or incoming inventory.
13. Scanner CSV files may use `Set Number`,
   `Card Number`, `Variant`, and `Count`.
14. Review matched cards, combined duplicate scans, current quantities, additions,
   resulting quantities, and unmatched scanner rows.
15. In **Review & Export**, inspect every price and quantity change together,
   then download one TCGplayer-ready CSV.

The combined export supports price-only, quantity-only, and mixed updates.
`Total Quantity` is always cleared, `Add to Quantity` contains only scanner
additions, and only rows with an approved price or quantity change are exported.
Price changes are exported only when the row already has stock or receives a
scanner quantity addition.

Uploaded data is held only in the active Streamlit session. The app does not
save inventory files to disk or send them to any external service.
