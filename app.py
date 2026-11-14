"""ParkMatch prototype: preference form, top-3 matches, trail map, photo gallery.

Run with:  streamlit run app.py
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import sys

import folium
import streamlit as st
from streamlit_folium import st_folium


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from parkmatch.catalog import (  # noqa: E402
    DIFFICULTY_LEVELS,
    EASY_MAX_GAIN_FT,
    EASY_MAX_MILES,
    HARD_MIN_GAIN_FT,
    HARD_MIN_MILES,
    Catalog,
    load_catalog,
)
from parkmatch.geometry import METERS_PER_MILE, bounds, haversine_meters  # noqa: E402
from parkmatch.recommender import (  # noqa: E402
    SCENERY_LABELS,
    TIME_LABELS,
    Preferences,
    recommend,
)


PARK_CODE = "MORA"
START_CITIES = {  # (longitude, latitude)
    "Seattle": (-122.3321, 47.6062),
    "Tacoma": (-122.4443, 47.2529),
    "Olympia": (-122.9007, 47.0379),
}
LEVEL_COLORS = {"Easy": "#7cc15a", "Moderate": "#2d7aa8", "Hard": "#14361f"}
SUN = "#ffd84a"

CSS = """
<style>
:root {
  --forest: #14361f; --green: #2f7d3b; --leaf: #7cc15a;
  --sky: #2d7aa8; --sun: #ffd84a; --cream: #f6f5ee; --ink: #16301f;
}
header[data-testid="stHeader"], footer { display: none; }
.block-container { padding-top: 0; padding-bottom: 2rem; max-width: 1280px; }
.pm-hero {
  margin: 0 -1rem; padding: 5.5rem 3rem 2.2rem; color: #fff;
  background-size: cover; background-position: center 40%;
  border-radius: 0 0 14px 14px; position: relative;
}
.pm-brand {
  display: inline-block; background: var(--sun); color: var(--forest);
  font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
  padding: .25rem .7rem; border-radius: 4px; font-size: .85rem;
}
.pm-hero h1 { color: #fff; font-size: 3rem; margin: .6rem 0 .3rem; padding: 0; }
.pm-hero p { font-size: 1.15rem; max-width: 40rem; margin: 0; }
.pm-credit { position: absolute; right: 1rem; bottom: .5rem; font-size: .72rem; opacity: .85; }
.pm-strip {
  height: 8px; margin: 0 -1rem 1.4rem; border-radius: 0 0 6px 6px;
  background: linear-gradient(90deg, var(--sun), var(--leaf), var(--green), var(--forest), var(--sky));
}
.pm-section { margin: 2rem 0 .2rem; }
.pm-section h2 {
  color: var(--forest); font-size: 1.6rem; margin: 0; padding: 0 0 .2rem;
  border-bottom: 4px solid var(--sun); display: inline-block;
}
.pm-section p { color: #3d5646; margin: .4rem 0 0; }
.pm-card {
  background: #fff; border: 1px solid #d9e2d3; border-radius: 12px;
  overflow: hidden; box-shadow: 0 2px 8px rgba(20,54,31,.08); height: 100%;
}
.pm-card-img {
  height: 190px; background-size: cover; background-position: center;
  position: relative; background-color: #cfdccb;
}
.pm-card-img.small { height: 120px; }
.pm-noimg {
  display: flex; align-items: center; justify-content: center;
  color: #4d6655; font-size: .9rem;
}
.pm-badge {
  position: absolute; left: .7rem; top: .7rem; background: var(--sun);
  color: var(--forest); font-weight: 800; padding: .2rem .6rem;
  border-radius: 999px; font-size: .85rem;
}
.pm-rank {
  position: absolute; right: .7rem; top: .7rem; background: var(--forest);
  color: #fff; font-weight: 700; padding: .2rem .6rem; border-radius: 999px;
  font-size: .8rem;
}
.pm-photo-credit {
  position: absolute; right: .4rem; bottom: .3rem; color: #fff; font-size: .68rem;
  background: rgba(20,54,31,.6); padding: .05rem .4rem; border-radius: 4px;
}
.pm-card-body { padding: .8rem 1rem 1rem; }
.pm-area {
  color: var(--sky); font-size: .75rem; font-weight: 700;
  letter-spacing: .08em; text-transform: uppercase;
}
.pm-card-body h3 { color: var(--forest); font-size: 1.15rem; margin: .1rem 0 .5rem; padding: 0; }
.pm-card-body.small h3 { font-size: .95rem; margin-bottom: .3rem; }
.pm-chips { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: .5rem; }
.pm-chip {
  background: #e6f1dd; color: var(--forest); border-radius: 999px;
  padding: .12rem .6rem; font-size: .8rem; font-weight: 600;
}
.pm-chip.easy { background: var(--leaf); }
.pm-chip.moderate { background: var(--sky); color: #fff; }
.pm-chip.hard { background: var(--forest); color: #fff; }
.pm-chip.label { background: #fff3c2; }
.pm-why { min-height: 8.8rem; margin: .3rem 0 0; padding-left: 1.1rem; color: #2c4535; font-size: .88rem; }
.pm-why li { margin: .1rem 0; }
.pm-detail h3 { color: var(--forest); font-size: 1.5rem; margin: .2rem 0 .4rem; padding: 0; }
.pm-gallery-main {
  height: 250px; border-radius: 12px; background-size: cover;
  background-position: center; position: relative; background-color: #cfdccb;
}
.pm-thumbs { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: .5rem; }
.pm-thumbs .pm-gallery-main { height: 110px; border-radius: 8px; }
.pm-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; margin: .7rem 0; }
.pm-stat { background: #eef4e8; border-radius: 8px; padding: .5rem .7rem; }
.pm-stat span { display: block; font-size: .72rem; color: #4d6655; text-transform: uppercase; letter-spacing: .05em; }
.pm-stat b { color: var(--forest); font-size: 1.05rem; }
.pm-alert {
  background: #fff3c2; border-left: 6px solid var(--sun); color: #4a3d00;
  padding: .6rem .8rem; border-radius: 6px; margin: .6rem 0; font-size: .9rem;
}
.pm-note {
  background: #e3eef5; border-left: 6px solid var(--sky); color: #173f58;
  padding: .5rem .8rem; border-radius: 6px; margin: .5rem 0; font-size: .85rem;
}
.pm-legend { font-size: .82rem; color: #3d5646; margin-top: .3rem; }
.pm-dot { display: inline-block; width: .7rem; height: .7rem; border-radius: 50%; margin: 0 .25rem 0 .7rem; border: 1px solid var(--forest); }
.pm-park {
  background: var(--forest); color: #eaf3e4; border-radius: 14px;
  padding: 1.6rem 2rem; margin-top: 2rem;
}
.pm-park h2 { color: #fff; margin: 0 0 .4rem; padding: 0; font-size: 1.5rem; }
.pm-park a { color: var(--sun); font-weight: 700; }
.pm-park-photos { display: grid; grid-template-columns: repeat(3, 1fr); gap: .6rem; margin-top: 1rem; }
.pm-footer { color: #4d6655; font-size: .8rem; margin-top: 1.2rem; }
</style>
"""


def block(markup: str) -> None:
    """Render HTML; lines are joined so Markdown never sees indented code."""
    st.markdown(
        " ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True
    )


def bg(url: str) -> str:
    return f"background-image:url('{escape(url, quote=True)}')"


@st.cache_resource
def get_catalog() -> Catalog:
    return load_catalog(ROOT / "data" / "processed")


def chips(trail: dict) -> str:
    parts = []
    if trail["distance_miles"] is not None:
        parts.append(f"<span class='pm-chip'>{trail['distance_miles']:g} mi</span>")
    if trail["elevation_gain_ft"] is not None:
        parts.append(
            f"<span class='pm-chip'>{trail['elevation_gain_ft']:,.0f} ft gain</span>"
        )
    if trail["nps_duration_text"]:
        parts.append(
            f"<span class='pm-chip'>{escape(trail['nps_duration_text'].lower())}</span>"
        )
    if trail["difficulty"]:
        parts.append(
            f"<span class='pm-chip {trail['difficulty'].lower()}'>"
            f"{trail['difficulty']}</span>"
        )
    return "".join(parts)


def photo_tile(photo: dict | None, css: str = "pm-card-img", extra: str = "") -> str:
    if photo is None:
        return f"<div class='{css} pm-noimg'>No photo available yet{extra}</div>"
    return (
        f"<div class='{css}' style=\"{bg(photo['remote_url'])}\" role='img' "
        f"aria-label='{escape(photo['alt_text'], quote=True)}'>{extra}"
        f"<span class='pm-photo-credit'>{escape(photo['credit'])}</span></div>"
    )


def select_trail(trail_id: str) -> None:
    st.session_state.selected_trail = trail_id


def build_map(catalog: Catalog, selected_id: str, whole_park: bool) -> folium.Map:
    park = catalog.parks[PARK_CODE]
    selected = catalog.trail(selected_id)
    center, zoom = [park["latitude"], park["longitude"]], 10
    if not whole_park and selected_id in catalog.routes:
        west, south, east, north = bounds([catalog.routes[selected_id]])
        center, zoom = [(south + north) / 2, (west + east) / 2], 16
    elif not whole_park and selected["latitude"] is not None:
        center, zoom = [selected["latitude"], selected["longitude"]], 13
    trail_map = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    for trail_id, feature in catalog.routes.items():
        verified = feature["properties"].get("geometry_verified", False)
        folium.GeoJson(
            feature,
            style_function=lambda _f, verified=verified, chosen=trail_id == selected_id: {
                "color": "#d9480f" if chosen else "#2d7aa8",
                "weight": 5,
                "dashArray": None if verified else "8 8",
            },
            tooltip=catalog.trail(trail_id)["trail_name"],
        ).add_to(trail_map)

    for trail in catalog.trails:
        if trail["latitude"] is None or trail["longitude"] is None:
            continue
        chosen = trail["trail_id"] == selected_id
        folium.CircleMarker(
            location=[trail["latitude"], trail["longitude"]],
            radius=13 if chosen else 8,
            color="#14361f",
            weight=3 if chosen else 1.5,
            fill=True,
            fill_color=SUN if chosen else LEVEL_COLORS.get(trail["difficulty"], "#888"),
            fill_opacity=1.0,
            tooltip=trail["trail_name"],
        ).add_to(trail_map)

    return trail_map


def clicked_trail(catalog: Catalog, clicked: dict) -> str | None:
    """Map a click reported by the map back to a trail_id."""
    tooltip = clicked.get("last_object_clicked_tooltip")
    if tooltip:
        name = " ".join(tooltip.split())
        for trail in catalog.trails:
            if trail["trail_name"] == name:
                return trail["trail_id"]
    point = clicked.get("last_object_clicked")
    if point:
        for trail in catalog.trails:
            if (
                trail["latitude"] is not None
                and abs(trail["latitude"] - point["lat"]) < 1e-6
                and abs(trail["longitude"] - point["lng"]) < 1e-6
            ):
                return trail["trail_id"]
    return None


def render_detail(catalog: Catalog, trail: dict) -> None:
    park = catalog.parks[PARK_CODE]
    photos = catalog.showable_photos(trail["trail_id"])
    gallery = photo_tile(photos[0] if photos else None, "pm-gallery-main")
    if len(photos) > 1:
        gallery += "<div class='pm-thumbs'>" + "".join(
            photo_tile(photo, "pm-gallery-main") for photo in photos[1:]
        ) + "</div>"

    labels = ""
    if trail["designation"]:
        labels = (
            "<div class='pm-chips'><span class='pm-chip label'>"
            f"{escape(trail['designation'])}</span></div>"
        )
    scenery = "".join(
        f"<span class='pm-chip'>{SCENERY_LABELS[tag]}</span>"
        for tag in trail["scenery_tags"]
    )
    stats = [
        ("Distance", f"{trail['distance_miles']:g} mi" if trail["distance_miles"] else "Unknown"),
        ("Elevation gain", f"{trail['elevation_gain_ft']:,.0f} ft" if trail["elevation_gain_ft"] else "Unknown"),
        ("Hiking time", trail["nps_duration_text"] or "Unknown"),
        ("Difficulty", trail["difficulty"] or "Unknown"),
        ("Route type", trail["route_type"] or "Unknown"),
        ("Seasons", trail["seasons"].replace("|", ", ") or "Unknown"),
    ]
    stat_html = "".join(
        f"<div class='pm-stat'><span>{name}</span><b>{escape(str(value))}</b></div>"
        for name, value in stats
    )
    alert = (
        f"<div class='pm-alert'><b>NPS notice:</b> {escape(trail['alert'])}</div>"
        if trail["alert"]
        else ""
    )
    if trail["geometry_status"] == "none":
        geometry_note = (
            "The route line for this trail is not mapped yet. The marker shows "
            "the location NPS lists for this hike."
        )
    elif not trail["geometry_verified"]:
        geometry_note = (
            "The dashed route line is provisional: it has not been fully checked "
            "against the official route, and it may have gaps."
        )
    else:
        geometry_note = ""
    notes = "".join(
        f"<div class='pm-note'>{escape(text)}</div>"
        for text in (geometry_note, trail["attribute_note"])
        if text
    )

    block(
        f"""
        <div class='pm-detail'>
        {gallery}
        <div class='pm-area' style='margin-top:.7rem'>{escape(trail['area'])}</div>
        <h3>{escape(trail['trail_name'])}</h3>
        {labels}
        <div class='pm-chips'>{scenery}</div>
        <div class='pm-stats'>{stat_html}</div>
        {alert}
        <p>{escape(trail['summary'])}</p>
        {notes}
        </div>
        """
    )
    with st.expander("More about this trail (from NPS)"):
        st.write(trail["description"])
    left, right = st.columns(2)
    left.link_button(
        "Check current NPS conditions",
        park["conditions_url"],
        type="primary",
        use_container_width=True,
    )
    right.link_button(
        "Official NPS trail page", trail["source_url"], use_container_width=True
    )


def main() -> None:
    st.set_page_config(page_title="ParkMatch — Mount Rainier", page_icon="🏔️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    catalog = get_catalog()
    park = catalog.parks[PARK_CODE]
    trail_ids = [trail["trail_id"] for trail in catalog.trails]

    # A map click from the previous run is applied before any widget is drawn.
    pending = st.session_state.pop("pending_trail", None)
    if pending in trail_ids:
        st.session_state.selected_trail = pending

    # ---- Hero -----------------------------------------------------------
    hero = next(
        (p for p in catalog.park_photos if p["is_hero"] == "true" and p["license_type"] != "unknown"),
        None,
    )
    hero_style = (
        "background-image:linear-gradient(180deg, rgba(20,54,31,.15), rgba(20,54,31,.88)), "
        f"url('{escape(hero['remote_url'], quote=True)}')"
        if hero
        else "background:#14361f"
    )
    hero_credit = f"<span class='pm-credit'>Photo: {escape(hero['credit'])}</span>" if hero else ""
    block(
        f"""
        <div class='pm-hero' style="{hero_style}">
        <span class='pm-brand'>ParkMatch</span>
        <h1>Find your trail at Mount Rainier</h1>
        <p>Tell us how far you want to go and what you want to see.
        We match you with up to three hikes and show you what they look like.</p>
        {hero_credit}
        </div>
        <div class='pm-strip'></div>
        """
    )

    # ---- Preferences ----------------------------------------------------
    block("<div class='pm-section'><h2>1 · Plan your hike</h2></div>")
    with st.container(border=True):
        col_city, col_level, col_time, col_scenery = st.columns([1, 1.6, 2.3, 2.3])
        city = col_city.selectbox("Starting from", list(START_CITIES))
        level = col_level.segmented_control(
            "Hardest level you want", DIFFICULTY_LEVELS, default="Moderate"
        ) or "Moderate"
        time_key = col_time.segmented_control(
            "Time you have to hike",
            list(TIME_LABELS),
            format_func=TIME_LABELS.get,
            default="2_to_4",
        ) or "2_to_4"
        scenery = col_scenery.pills(
            "What you want to see",
            list(SCENERY_LABELS),
            format_func=SCENERY_LABELS.get,
            selection_mode="multi",
            default=["mountain_views"],
        )
        miles = haversine_meters(
            START_CITIES[city], (park["longitude"], park["latitude"])
        ) / METERS_PER_MILE
        st.caption(
            f"{city} is about {miles:.0f} miles from the park in a straight line "
            "(driving is longer). Every trail here is in the same park, so your "
            "starting city does not change the ranking."
        )

    preferences = Preferences(level, time_key, tuple(scenery))
    result = recommend(catalog.trails, preferences)

    if "selected_trail" not in st.session_state:
        st.session_state.selected_trail = (
            result.recommendations[0].trail_id if result.recommendations else trail_ids[0]
        )

    # ---- Matches --------------------------------------------------------
    block(
        "<div class='pm-section'><h2>2 · Your top matches</h2>"
        "<p>Trails that are too hard or too long for your choices are left out.</p></div>"
    )
    if not result.recommendations:
        st.warning(
            "No trail fits these choices. Try a harder level or more time."
        )
    else:
        columns = st.columns(3)
        for rank, (column, rec) in enumerate(zip(columns, result.recommendations), 1):
            trail = catalog.trail(rec.trail_id)
            photos = catalog.showable_photos(rec.trail_id, limit=1)
            badges = (
                f"<span class='pm-badge'>{rec.score:.0%} match</span>"
                f"<span class='pm-rank'>#{rank}</span>"
            )
            reasons = "".join(f"<li>{escape(reason)}</li>" for reason in rec.reasons)
            with column:
                block(
                    f"""
                    <div class='pm-card'>
                    {photo_tile(photos[0] if photos else None, extra=badges)}
                    <div class='pm-card-body'>
                    <div class='pm-area'>{escape(trail['area'])}</div>
                    <h3>{escape(trail['trail_name'])}</h3>
                    <div class='pm-chips'>{chips(trail)}</div>
                    <ul class='pm-why'>{reasons}</ul>
                    </div></div>
                    """
                )
                st.button(
                    "See map and photos",
                    key=f"rec_{rec.trail_id}",
                    on_click=select_trail,
                    args=(rec.trail_id,),
                    use_container_width=True,
                    type="primary",
                )
    if result.excluded:
        with st.expander(f"Why {len(result.excluded)} trails were left out"):
            for trail_id, reason in result.excluded.items():
                st.write(f"**{catalog.trail(trail_id)['trail_name']}** — {reason}")

    # ---- Explorer -------------------------------------------------------
    block(
        "<div class='pm-section'><h2>3 · Explore the trail</h2>"
        "<p>Click a marker on the map, or pick a trail from the list.</p></div>"
    )
    pick_col, toggle_col = st.columns([3, 1])
    pick_col.selectbox(
        "Trail",
        trail_ids,
        format_func=lambda trail_id: catalog.trail(trail_id)["trail_name"],
        key="selected_trail",
        label_visibility="collapsed",
    )
    whole_park = toggle_col.toggle("Show whole park", value=False)
    selected_id = st.session_state.selected_trail
    selected = catalog.trail(selected_id)

    map_col, detail_col = st.columns([3, 2], gap="large")
    with map_col:
        clicked = st_folium(
            build_map(catalog, selected_id, whole_park),
            height=640,
            use_container_width=True,
            key=f"map_{selected_id}_{whole_park}",
            returned_objects=["last_object_clicked", "last_object_clicked_tooltip"],
        )
        block(
            "<div class='pm-legend'>Markers:"
            f"<span class='pm-dot' style='background:{SUN}'></span>selected"
            + "".join(
                f"<span class='pm-dot' style='background:{color}'></span>{name}"
                for name, color in LEVEL_COLORS.items()
            )
            + " · Dashed line: provisional route</div>"
        )
        match = clicked_trail(catalog, clicked or {})
        if match and match != selected_id:
            st.session_state.pending_trail = match
            st.rerun()
    with detail_col:
        render_detail(catalog, selected)

    # ---- All trails -----------------------------------------------------
    block(
        f"<div class='pm-section'><h2>All {len(catalog.trails)} trails</h2>"
        "<p>Every hike in the Mount Rainier pilot catalog.</p></div>"
    )
    per_row = 5
    for start in range(0, len(catalog.trails), per_row):
        columns = st.columns(per_row)
        for column, trail in zip(columns, catalog.trails[start:start + per_row]):
            photos = catalog.showable_photos(trail["trail_id"], limit=1)
            with column:
                block(
                    f"""
                    <div class='pm-card'>
                    {photo_tile(photos[0] if photos else None, 'pm-card-img small')}
                    <div class='pm-card-body small'>
                    <div class='pm-area'>{escape(trail['area'])}</div>
                    <h3>{escape(trail['trail_name'])}</h3>
                    <div class='pm-chips'>{chips(trail)}</div>
                    </div></div>
                    """
                )
                st.button(
                    "View",
                    key=f"all_{trail['trail_id']}",
                    on_click=select_trail,
                    args=(trail["trail_id"],),
                    use_container_width=True,
                )

    # ---- Park -----------------------------------------------------------
    park_tiles = "".join(
        photo_tile(photo, "pm-gallery-main")
        for photo in [
            p for p in catalog.park_photos
            if p["license_type"] != "unknown" and p["is_hero"] != "true"
        ][:3]
    )
    block(
        f"""
        <div class='pm-park'>
        <h2>{escape(park['park_name'])}</h2>
        <p>{escape(park['description'])}</p>
        <p><b>Entrance fees (from NPS):</b> {escape(park['entrance_fee_note'])}</p>
        <p><a href="{escape(park['official_url'], quote=True)}" target="_blank">Official park website</a>
        &nbsp;·&nbsp;
        <a href="{escape(park['conditions_url'], quote=True)}" target="_blank">Current conditions and alerts</a></p>
        <div class='pm-park-photos'>{park_tiles}</div>
        </div>
        <div class='pm-footer'>
        ParkMatch is a student prototype. It is not affiliated with or endorsed by the
        National Park Service. Trail text, locations, and photos come from the NPS Data API;
        map tiles © OpenStreetMap contributors. Difficulty is a draft rule, not an NPS rating:
        Hard is {HARD_MIN_MILES:g}+ miles or {HARD_MIN_GAIN_FT:,}+ ft of gain; Easy is up to
        {EASY_MAX_MILES:g} miles with under {EASY_MAX_GAIN_FT} ft of gain; everything else is
        Moderate. Always check current conditions with NPS before you go.
        </div>
        """
    )


main()
