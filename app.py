"""ParkMatch prototype: preference form, top-3 matches, trail map, photo gallery.

Run with:  streamlit run app.py
"""

from __future__ import annotations

from html import escape
from math import cos, log2, radians
from pathlib import Path
import sys

import folium
import streamlit as st
import streamlit.components.v1 as components
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
LINE_COLORS = {"Easy": "#4fa62f", "Moderate": "#2d7aa8", "Hard": "#14361f"}
PREF_DEFAULTS = {
    "pref_city": "Seattle",
    "pref_level": "Moderate",
    "pref_time": "2_to_4",
    "pref_scenery": ["mountain_views"],
}

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
.pm-map-legend {
  position: relative; z-index: 5; width: max-content; top: 12px;
  margin: 0 0 -150px 58px; height: 134px; box-sizing: border-box;
  background: rgba(255,255,255,.94); border-radius: 8px; padding: .55rem .8rem;
  box-shadow: 0 1px 6px rgba(20,54,31,.25); font-size: .8rem; color: var(--ink);
}
.pm-map-legend b { display: block; margin-bottom: .25rem; color: var(--forest); }
.pm-map-legend div { display: flex; align-items: center; gap: .45rem; margin: .18rem 0; }
.pm-swatch { display: inline-block; width: 1.9rem; height: .34rem; border-radius: 3px; }
.pm-trail-hero {
  margin: 0 -1rem 1.2rem; padding: 7rem 3rem 1.6rem; color: #fff;
  background-size: cover; background-position: center; border-radius: 0 0 14px 14px;
  position: relative; background-color: var(--forest);
}
.pm-trail-hero h1 { color: #fff; font-size: 2.6rem; margin: .2rem 0 .6rem; padding: 0; }
.pm-trail-hero .pm-area { color: var(--sun); }
.pm-topbar { height: .6rem; }
</style>
"""


def block(markup: str) -> None:
    """Render HTML; lines are joined so Markdown never sees indented code."""
    st.markdown(
        " ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True
    )


def bg(url: str) -> str:
    return f"background-image:url('{escape(url, quote=True)}')"


PROCESSED_DIR = ROOT / "data" / "processed"


@st.cache_resource
def get_catalog(data_stamp: float) -> Catalog:
    """Load the tables; ``data_stamp`` reloads them when a file changes."""
    return load_catalog(PROCESSED_DIR)


def data_stamp() -> float:
    return max(path.stat().st_mtime for path in PROCESSED_DIR.iterdir())


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


def open_trail(trail_id: str) -> None:
    st.query_params["trail"] = trail_id


def close_trail() -> None:
    if "trail" in st.query_params:
        del st.query_params["trail"]
    # A fresh key stops the overview map replaying its last click.
    st.session_state.map_nonce = st.session_state.get("map_nonce", 0) + 1


def scroll_to_top(page: str) -> None:
    """Jump to the top when the visitor moves between pages."""
    if st.session_state.get("last_page") != page:
        st.session_state.last_page = page
        components.html(
            "<script>const m = window.parent.document.querySelector("
            "'[data-testid=\"stMain\"]'); if (m) m.scrollTo(0, 0);"
            "window.parent.scrollTo(0, 0);</script>",
            height=0,
        )


def view_for(features: list[dict], width_px: int, height_px: int) -> tuple[list[float], int]:
    """Center and zoom level that fit ``features`` in a map of the given size."""
    west, south, east, north = bounds(features)
    center = [(south + north) / 2, (west + east) / 2]
    lon_span = max(east - west, 1e-4)
    lat_span = max(north - south, 1e-4) / cos(radians(center[0]))
    zoom = min(
        log2(360 * width_px / 256 / lon_span),
        log2(360 * height_px / 256 / lat_span),
    )
    return center, max(9, min(16, int(zoom - 0.35)))


def build_map(catalog: Catalog, selected_id: str | None, height_px: int) -> folium.Map:
    """All routes colored by difficulty; the selected one is highlighted."""
    park = catalog.parks[PARK_CODE]
    focus = (
        [catalog.routes[selected_id]]
        if selected_id in catalog.routes
        else list(catalog.routes.values())
    )
    if focus:
        center, zoom = view_for(focus, 700 if selected_id else 900, height_px)
    else:
        center, zoom = [park["latitude"], park["longitude"]], 10
    if selected_id and selected_id not in catalog.routes:
        chosen = catalog.trail(selected_id)
        if chosen["latitude"] is not None:
            center, zoom = [chosen["latitude"], chosen["longitude"]], 13

    trail_map = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=None,
        control_scale=True,
        scrollWheelZoom=False,  # let the mouse wheel scroll the page
    )
    folium.TileLayer(
        tiles=(
            "https://basemap.nationalmap.gov/arcgis/rest/services/"
            "USGSTopo/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="USGS The National Map",
        name="Topographic map",
        max_zoom=16,
    ).add_to(trail_map)
    folium.TileLayer("OpenStreetMap", name="Street map", show=False).add_to(trail_map)

    ordered = sorted(catalog.routes.items(), key=lambda item: item[0] == selected_id)
    for trail_id, feature in ordered:
        trail = catalog.trail(trail_id)
        chosen = trail_id == selected_id
        color = SUN if chosen else LINE_COLORS.get(trail["difficulty"], "#777")
        casing = "#14361f" if chosen else "#ffffff"
        for line_color, weight in (
            (casing, 10 if chosen else 8),
            (color, 6 if chosen else 4),
        ):
            folium.GeoJson(
                feature,
                style_function=lambda _f, c=line_color, w=weight: {
                    "color": c,
                    "weight": w,
                    "opacity": 1.0,
                },
                tooltip=trail["trail_name"],
            ).add_to(trail_map)

    for trail in catalog.trails:
        if trail["latitude"] is None or trail["longitude"] is None:
            continue
        chosen = trail["trail_id"] == selected_id
        folium.CircleMarker(
            location=[trail["latitude"], trail["longitude"]],
            radius=9 if chosen else 6,
            color="#14361f" if chosen else "#ffffff",
            weight=2,
            fill=True,
            fill_color=SUN if chosen else LINE_COLORS.get(trail["difficulty"], "#777"),
            fill_opacity=1.0,
            tooltip=trail["trail_name"],
        ).add_to(trail_map)

    folium.LayerControl(collapsed=True).add_to(trail_map)
    return trail_map


def clicked_trail(catalog: Catalog, clicked: dict) -> str | None:
    """Map a click reported by the map back to a trail_id."""
    tooltip = clicked.get("last_object_clicked_tooltip")
    if tooltip:
        name = " ".join(tooltip.split())
        for trail in catalog.trails:
            if trail["trail_name"] == name:
                return trail["trail_id"]
    drawing = clicked.get("last_active_drawing") or {}
    trail_id = (drawing.get("properties") or {}).get("trail_id")
    if trail_id in {trail["trail_id"] for trail in catalog.trails}:
        return trail_id
    return None


def render_map(catalog: Catalog, selected_id: str | None, height_px: int, key: str) -> None:
    """Draw the legend and map; a click on a route opens that trail's page."""
    rows = "".join(
        f"<div><span class='pm-swatch' style='background:{color}'></span>{name}</div>"
        for name, color in LINE_COLORS.items()
    )
    block(
        f"""
        <div class='pm-map-legend'>
        <b>Trail difficulty</b>
        {rows}
        <div><span class='pm-swatch' style='background:{SUN};outline:2px solid #14361f'></span>Selected trail</div>
        </div>
        """
    )
    clicked = st_folium(
        build_map(catalog, selected_id, height_px),
        height=height_px,
        use_container_width=True,
        key=key,
        returned_objects=[
            "last_object_clicked",
            "last_object_clicked_tooltip",
            "last_active_drawing",
        ],
    )
    match = clicked_trail(catalog, clicked or {})
    if match and match != selected_id:
        st.query_params["trail"] = match
        st.rerun()


def route_notes(catalog: Catalog, trail: dict) -> str:
    feature = catalog.routes.get(trail["trail_id"])
    notes: list[str] = []
    if feature is None:
        notes.append(
            "The route line for this trail is not mapped yet. The marker shows "
            "the location NPS lists for this hike."
        )
    else:
        properties = feature["properties"]
        if not properties.get("geometry_verified"):
            notes.append(
                "The route line is provisional. It was assembled from "
                f"{properties.get('geometry_source', 'public trail data')} and has "
                "not been checked against the official NPS map. Do not use it "
                "for navigation."
            )
        if properties.get("route_note"):
            notes.append(properties["route_note"])
    if trail["attribute_note"]:
        notes.append(trail["attribute_note"])
    return "".join(f"<div class='pm-note'>{escape(text)}</div>" for text in notes)


def render_trail_page(catalog: Catalog, trail: dict) -> None:
    park = catalog.parks[PARK_CODE]
    photos = catalog.showable_photos(trail["trail_id"])
    cover = photos[0] if photos else None

    block("<div class='pm-topbar'></div>")
    st.button("← Back to all trails and the map", on_click=close_trail)

    hero_style = (
        "background-image:linear-gradient(180deg, rgba(20,54,31,.1), rgba(20,54,31,.9)), "
        f"url('{escape(cover['remote_url'], quote=True)}')"
        if cover
        else ""
    )
    credit = f"<span class='pm-credit'>Photo: {escape(cover['credit'])}</span>" if cover else ""
    label = (
        f"<span class='pm-chip label'>{escape(trail['designation'])}</span>"
        if trail["designation"]
        else ""
    )
    block(
        f"""
        <div class='pm-trail-hero' style="{hero_style}">
        <div class='pm-area'>{escape(trail['area'])} · {escape(park['park_name'])}</div>
        <h1>{escape(trail['trail_name'])}</h1>
        <div class='pm-chips'>{chips(trail)}{label}</div>
        {credit}
        </div>
        """
    )

    map_col, detail_col = st.columns([3, 2], gap="large")
    with map_col:
        block(
            "<div class='pm-section' style='margin-top:0'><h2>Route map</h2>"
            "<p>The highlighted line is this trail.</p></div>"
        )
        render_map(catalog, trail["trail_id"], 560, key=f"trail_map_{trail['trail_id']}")
        block(route_notes(catalog, trail))
    with detail_col:
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
        gallery = ""
        if len(photos) > 1:
            gallery = "<div class='pm-thumbs' style='margin:0 0 .8rem'>" + "".join(
                photo_tile(photo, "pm-gallery-main") for photo in photos[1:]
            ) + "</div>"
        block(
            f"""
            <div class='pm-detail'>
            {alert}
            <p style='font-size:1.05rem'>{escape(trail['summary'])}</p>
            <div class='pm-chips'>{scenery}</div>
            <div class='pm-stats'>{stat_html}</div>
            {gallery}
            </div>
            """
        )
        with st.expander("More about this trail (from NPS)", expanded=True):
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


def render_footer(catalog: Catalog) -> None:
    park = catalog.parks[PARK_CODE]
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
        National Park Service. Trail text, locations, and photos come from the NPS Data API.
        Route lines come from the Washington State Trails Database (Recreation and
        Conservation Office); they are provisional and for information only, not navigation.
        Base maps: USGS The National Map and © OpenStreetMap contributors. Difficulty is a draft rule, not an
        NPS rating: Hard is {HARD_MIN_MILES:g}+ miles or {HARD_MIN_GAIN_FT:,}+ ft of gain;
        Easy is up to {EASY_MAX_MILES:g} miles with under {EASY_MAX_GAIN_FT} ft of gain;
        everything else is Moderate. Always check current conditions with NPS before you go.
        </div>
        """
    )


def render_home(catalog: Catalog) -> None:
    park = catalog.parks[PARK_CODE]

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
        city = col_city.selectbox("Starting from", list(START_CITIES), key="pref_city")
        level = col_level.segmented_control(
            "Hardest level you want", DIFFICULTY_LEVELS, key="pref_level"
        ) or PREF_DEFAULTS["pref_level"]
        time_key = col_time.segmented_control(
            "Time you have to hike",
            list(TIME_LABELS),
            format_func=TIME_LABELS.get,
            key="pref_time",
        ) or PREF_DEFAULTS["pref_time"]
        scenery = col_scenery.pills(
            "What you want to see",
            list(SCENERY_LABELS),
            format_func=SCENERY_LABELS.get,
            selection_mode="multi",
            key="pref_scenery",
        )
        miles = haversine_meters(
            START_CITIES[city], (park["longitude"], park["latitude"])
        ) / METERS_PER_MILE
        st.caption(
            f"{city} is about {miles:.0f} miles from the park in a straight line "
            "(driving is longer). Every trail here is in the same park, so your "
            "starting city does not change the ranking."
        )

    result = recommend(catalog.trails, Preferences(level, time_key, tuple(scenery)))

    # ---- Matches --------------------------------------------------------
    block(
        "<div class='pm-section'><h2>2 · Your top matches</h2>"
        "<p>Trails that are too hard or too long for your choices are left out.</p></div>"
    )
    if not result.recommendations:
        st.warning("No trail fits these choices. Try a harder level or more time.")
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
                    "Open trail page",
                    key=f"rec_{rec.trail_id}",
                    on_click=open_trail,
                    args=(rec.trail_id,),
                    use_container_width=True,
                    type="primary",
                )
    if result.excluded:
        with st.expander(f"Why {len(result.excluded)} trails were left out"):
            for trail_id, reason in result.excluded.items():
                st.write(f"**{catalog.trail(trail_id)['trail_name']}** — {reason}")

    # ---- Routes map -----------------------------------------------------
    block(
        "<div class='pm-section'><h2>3 · Trail map</h2>"
        "<p>Every trail in the park catalog. Click a line or a dot to open that trail's page. "
        "Route lines are provisional and not for navigation.</p></div>"
    )
    render_map(
        catalog, None, 620, key=f"overview_map_{st.session_state.get('map_nonce', 0)}"
    )

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
                    "Open",
                    key=f"all_{trail['trail_id']}",
                    on_click=open_trail,
                    args=(trail["trail_id"],),
                    use_container_width=True,
                )


def main() -> None:
    st.set_page_config(page_title="ParkMatch — Mount Rainier", page_icon="🏔️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    catalog = get_catalog(data_stamp())

    # Keep the visitor's choices alive while the form is off screen.
    for key, default in PREF_DEFAULTS.items():
        st.session_state[key] = st.session_state.get(key, default)

    trail_id = st.query_params.get("trail")
    if trail_id in {trail["trail_id"] for trail in catalog.trails}:
        scroll_to_top(trail_id)
        render_trail_page(catalog, catalog.trail(trail_id))
    else:
        scroll_to_top("home")
        render_home(catalog)
    render_footer(catalog)


main()
