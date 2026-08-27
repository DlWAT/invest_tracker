"""Descriptive analytics + plots for the listings database.

Reads the SQLite database produced by the collector and renders a set of
charts describing the data (volumes, prices, types, locations).

Usage:
    python analyze.py                  # open an interactive figure
    python analyze.py --db data/listings.db
    python analyze.py --save plots.png # save instead of showing
    python analyze.py --no-show        # save without opening a window
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

# Use a backend that does not require a display when --no-show is passed.
matplotlib.use("TkAgg", force=False)


def load_dataframe(db_path: str | Path) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query("SELECT * FROM listings", conn)
    conn.close()
    return df


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Parse JSON columns stored as TEXT.
    for col in ("amenities", "images"):
        df[col + "_n"] = df[col].map(lambda v: len(json.loads(v)) if v else 0)
    # Human-readable zone / province fallback.
    df["zone_label"] = df["zone_id"].fillna("(hors zone cible)")
    df["province_label"] = df["province"].fillna("inconnu")
    df["type_label"] = df["property_type"].fillna("autre")
    # PHP -> million PHP for readability.
    df["price_m"] = df["price_php"] / 1_000_000
    return df


def plot_dashboard(df: pd.DataFrame) -> plt.Figure:
    df = _prep(df)
    fig = plt.figure(figsize=(18, 22))
    fig.suptitle("Description de la base listings — Philippine Airbnb Scanner",
                 fontsize=18, fontweight="bold", y=0.995)

    # --- 1. Volume by province -------------------------------------------------
    ax1 = fig.add_subplot(4, 3, 1)
    df["province_label"].value_counts().plot(kind="bar", ax=ax1, color="#4C72B0")
    ax1.set_title("Annonces par province")
    ax1.set_ylabel("Nombre")
    ax1.tick_params(axis="x", rotation=0)

    # --- 2. Volume by property type -------------------------------------------
    ax2 = fig.add_subplot(4, 3, 2)
    df["type_label"].value_counts().plot(kind="bar", ax=ax2, color="#DD8452")
    ax2.set_title("Annonces par type de bien")
    ax2.set_ylabel("Nombre")
    ax2.tick_params(axis="x", rotation=45)

    # --- 3. Zone cible vs hors cible ------------------------------------------
    ax3 = fig.add_subplot(4, 3, 3)
    df["zone_label"].value_counts().plot(kind="bar", ax=ax3, color="#55A868")
    ax3.set_title("Dans la zone cible ?")
    ax3.set_ylabel("Nombre")
    ax3.tick_params(axis="x", rotation=45)

    # --- 4. Price distribution ------------------------------------------------
    ax4 = fig.add_subplot(4, 3, 4)
    df["price_m"].plot(kind="hist", bins=40, ax=ax4, color="#C44E52", edgecolor="white")
    ax4.set_title("Distribution des prix (M PHP)")
    ax4.set_xlabel("Prix (millions PHP)")

    # --- 5. Price boxplot by type ---------------------------------------------
    ax5 = fig.add_subplot(4, 3, 5)
    df.boxplot(column="price_php", by="type_label", ax=ax5, grid=False)
    ax5.set_title("Prix par type de bien")
    ax5.set_ylabel("Prix (PHP)")
    ax5.set_yscale("log")
    ax5.tick_params(axis="x", rotation=45)
    fig.suptitle("")  # avoid pandas boxplot overriding the main title

    # --- 6. Price per sqm -----------------------------------------------------
    ax6 = fig.add_subplot(4, 3, 6)
    df["price_per_sqm"].dropna().plot(kind="hist", bins=40, ax=ax6,
                                      color="#8172B3", edgecolor="white")
    ax6.set_title("Distribution prix au m² (PHP/m²)")
    ax6.set_xlabel("PHP / m²")

    # --- 7. Area distribution -------------------------------------------------
    ax7 = fig.add_subplot(4, 3, 7)
    df["area_sqm"].dropna().plot(kind="hist", bins=40, ax=ax7,
                                 color="#64B5CD", edgecolor="white")
    ax7.set_title("Distribution de la surface (m²)")
    ax7.set_xlabel("Surface (m²)")

    # --- 8. Price vs area (scatter, colored by type) --------------------------
    ax8 = fig.add_subplot(4, 3, 8)
    types = df["type_label"].unique()
    for t in types:
        sub = df[df["type_label"] == t]
        ax8.scatter(sub["area_sqm"], sub["price_m"], s=12, alpha=0.6, label=t)
    ax8.set_xlabel("Surface (m²)")
    ax8.set_ylabel("Prix (M PHP)")
    ax8.set_title("Prix vs surface")
    ax8.set_xscale("log")
    ax8.set_yscale("log")
    ax8.legend(markerscale=2, fontsize=8)

    # --- 9. Top micro-locations ------------------------------------------------
    ax9 = fig.add_subplot(4, 3, 9)
    top = df["location_text"].value_counts().head(15)
    top.sort_values().plot(kind="barh", ax=ax9, color="#F4A582")
    ax9.set_title("Top 15 localisations")
    ax9.set_xlabel("Nombre")

    # --- 10. Average price by province ----------------------------------------
    ax10 = fig.add_subplot(4, 3, 10)
    df.groupby("province_label")["price_m"].mean().sort_values().plot(
        kind="barh", ax=ax10, color="#64B5CD")
    ax10.set_title("Prix moyen par province (M PHP)")
    ax10.set_xlabel("Prix moyen (M PHP)")

    # --- 11. Beds distribution -------------------------------------------------
    ax11 = fig.add_subplot(4, 3, 11)
    df["beds"].value_counts().sort_index().plot(kind="bar", ax=ax11, color="#55A868")
    ax11.set_title("Distribution des chambres")
    ax11.set_xlabel("Chambres")

    # --- 12. Average price/sqm by zone ----------------------------------------
    ax12 = fig.add_subplot(4, 3, 12)
    df.groupby("zone_label")["price_per_sqm"].mean().sort_values().plot(
        kind="barh", ax=ax12, color="#DD8452")
    ax12.set_title("Prix moyen au m² par zone")
    ax12.set_xlabel("PHP / m²")

    fig.tight_layout(rect=[0, 0, 1, 0.98])
    return fig


def print_summary(df: pd.DataFrame) -> None:
    d = _prep(df)
    print("=== Aperçu de la base ===")
    print(f"Annonces totales : {len(d)}")
    print(f"Prix min / max / moyen : "
          f"₱{d['price_php'].min():,.0f} / ₱{d['price_php'].max():,.0f} / "
          f"₱{d['price_php'].mean():,.0f}")
    print(f"Surface moyenne : {d['area_sqm'].mean():,.0f} m²")
    print()
    print("Par province :")
    print(d["province_label"].value_counts().to_string())
    print()
    print("Par type :")
    print(d["type_label"].value_counts().to_string())
    print()
    print("Par zone cible :")
    print(d["zone_label"].value_counts().to_string())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot listings database")
    parser.add_argument("--db", default="data/listings.db")
    parser.add_argument("--save", default=None, help="Save figure to PNG")
    parser.add_argument("--no-show", action="store_true", help="Do not open a window")
    args = parser.parse_args(argv)

    df = load_dataframe(args.db)
    if df.empty:
        print("Base vide : lancez d'abord `python main.py` pour collecter.")
        return 1

    print_summary(df)
    fig = plot_dashboard(df)

    if args.save:
        fig.savefig(args.save, dpi=150, bbox_inches="tight")
        print(f"\nFigure enregistrée : {args.save}")

    if not args.no_show:
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
