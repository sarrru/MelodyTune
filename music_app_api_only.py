import os
from dotenv import load_dotenv
load_dotenv()

import time
from collections import OrderedDict
import requests
from urllib.parse import quote_plus

import streamlit as st

# Hide the "Deploy" button with CSS
st.markdown("""
    <style>
    button[title="Deploy this app"] {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)

# Import from our local utility files
from lastfm_api_utils import (
    get_track_info, get_artist_info, get_recommendations,
    get_similar_artists, get_top_tags_for_entity, search_track
)
from genre_assets import get_genre_image_url

# Page Configuration and Styling
st.set_page_config(
    page_title="MelodyTune: Music Recommender 🎵",
    page_icon="🎶",
    layout="wide"
)

# --- Hide Streamlit default header (removes stray material icon text) ---
st.markdown("""
    <style>
      header[data-testid="stHeader"] { display: none !important; }
      /* pull content up a bit since header is gone */
      div.block-container { padding-top: 1rem; }
    </style>
""", unsafe_allow_html=True)

# ---------- API Key (safe with/without secrets.toml) ----------
try:
    LASTFM_API_KEY = st.secrets["LASTFM_API_KEY"]
except Exception:
    LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

# ---------- Success-only image cache (avoid caching failures) ----------
if "img_cache" not in st.session_state:
    st.session_state.img_cache = {}

def _store_img(key: str, url: str | None) -> str | None:
    if url:
        st.session_state.img_cache[key] = url
    return url

# ---------- Image helpers (NO st.cache_data; we memoize only successes) ----------
def get_cover_image(artist: str, track: str) -> str | None:
    """Album/track art via Last.fm (autocorrect) -> iTunes (US/IN/NP)."""
    artist = (artist or "").strip()
    track  = (track  or "").strip()
    if not artist or not track:
        return None

    key = f"cover::{artist.lower()}::{track.lower()}"
    if key in st.session_state.img_cache:
        return st.session_state.img_cache[key]

    headers = {"User-Agent": "MelodyTune/1.0 (Streamlit app)"}

    # Last.fm: track.getInfo
    if LASTFM_API_KEY:
        for _ in range(2):  # light retry
            try:
                r = requests.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "track.getInfo",
                        "api_key": LASTFM_API_KEY,
                        "artist": artist,
                        "track": track,
                        "autocorrect": 1,
                        "format": "json",
                    },
                    headers=headers, timeout=8
                )
                if r.ok:
                    imgs = ((r.json().get("track", {}) or {}).get("album", {}) or {}).get("image", []) or []
                    for size in ["mega", "extralarge", "large", "medium", "small"]:
                        url = next((i.get("#text") for i in imgs if i.get("size") == size and i.get("#text")), "")
                        if url:
                            return _store_img(key, url)
                    for i in imgs:
                        if i.get("#text"):
                            return _store_img(key, i["#text"])
            except Exception:
                pass

    # iTunes fallback (multi-country)
    for country in ("US", "IN", "NP"):
        try:
            q = quote_plus(f"{artist} {track}")
            r = requests.get(
                f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=1&country={country}",
                headers=headers, timeout=8
            )
            if r.ok and r.json().get("resultCount", 0) > 0:
                art100 = r.json()["results"][0].get("artworkUrl100") or ""
                if art100:
                    return _store_img(key, art100.replace("100x100", "300x300"))
        except Exception:
            continue

    return None


def get_artist_image(artist: str) -> str | None:
    """Artist image via Last.fm (info → top albums → top tracks’ cover), then iTunes, then Wikipedia."""
    artist = (artist or "").strip()
    if not artist:
        return None

    key = f"artist::{artist.lower()}"
    if key in st.session_state.img_cache:
        return st.session_state.img_cache[key]

    headers = {"User-Agent": "MelodyTune/1.0 (Streamlit app)"}

    # Last.fm: artist.getInfo
    if LASTFM_API_KEY:
        for _ in range(2):
            try:
                r = requests.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "artist.getInfo",
                        "api_key": LASTFM_API_KEY,
                        "artist": artist,
                        "autocorrect": 1,
                        "format": "json",
                    },
                    headers=headers, timeout=8
                )
                if r.ok:
                    imgs = (r.json().get("artist", {}) or {}).get("image", []) or []
                    for size in ["mega", "extralarge", "large", "medium", "small"]:
                        url = next((i.get("#text") for i in imgs if i.get("size") == size and i.get("#text")), "")
                        if url:
                            return _store_img(key, url)
                    for i in imgs:
                        if i.get("#text"):
                            return _store_img(key, i["#text"])
            except Exception:
                pass

        # Last.fm: artist.getTopAlbums
        try:
            r = requests.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.getTopAlbums",
                    "api_key": LASTFM_API_KEY,
                    "artist": artist,
                    "autocorrect": 1,
                    "limit": 3,
                    "format": "json",
                },
                headers=headers, timeout=8
            )
            if r.ok:
                albums = (r.json().get("topalbums", {}) or {}).get("album", []) or []
                if isinstance(albums, dict):
                    albums = [albums]
                for alb in albums:
                    imgs = alb.get("image", []) or []
                    for size in ["extralarge", "large", "medium", "small"]:
                        url = next((i.get("#text") for i in imgs if i.get("size") == size and i.get("#text")), "")
                        if url:
                            return _store_img(key, url)
                    for i in imgs:
                        if i.get("#text"):
                            return _store_img(key, i["#text"])
        except Exception:
            pass

        # Last.fm: artist.getTopTracks → reuse top track album art
        try:
            r = requests.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.getTopTracks",
                    "api_key": LASTFM_API_KEY,
                    "artist": artist,
                    "autocorrect": 1,
                    "limit": 2,
                    "format": "json",
                },
                headers=headers, timeout=8
            )
            if r.ok:
                tracks = (r.json().get("toptracks", {}) or {}).get("track", []) or []
                if isinstance(tracks, dict):
                    tracks = [tracks]
                for t in tracks:
                    tname = t.get("name")
                    if tname:
                        img = get_cover_image(artist, tname)
                        if img:
                            return _store_img(key, img)
        except Exception:
            pass

    # iTunes fallback (multi-country)
    for country in ("US", "IN", "NP"):
        try:
            q = quote_plus(artist)
            r = requests.get(
                f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=1&country={country}",
                headers=headers, timeout=8
            )
            if r.ok and r.json().get("resultCount", 0) > 0:
                art100 = r.json()["results"][0].get("artworkUrl100") or ""
                if art100:
                    return _store_img(key, art100.replace("100x100", "300x300"))
        except Exception:
            continue

    # Wikipedia REST fallback (very reliable)
    try:
        title = quote_plus(artist)
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
            headers=headers, timeout=8
        )
        if r.ok and isinstance(r.json(), dict):
            j = r.json()
            orig = (j.get("originalimage") or {}).get("source") or ""
            thumb = (j.get("thumbnail") or {}).get("source") or ""
            if orig:
                return _store_img(key, orig)
            if thumb:
                return _store_img(key, thumb)
    except Exception:
        pass

    return None

# ---------- Styling ----------
def load_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }
        .stApp { background-color: #111111; }
        .card { 
            background: rgba(40, 40, 50, 0.6); 
            border-radius: 12px; 
            padding: 1rem; 
            margin-bottom: 1rem; 
            border: 1px solid rgba(255, 255, 255, 0.1); 
            backdrop-filter: blur(10px); 
            transition: all 0.2s ease-in-out; 
            text-align: center;
            height: 100%;
        }
        .card:hover { 
            transform: translateY(-5px); 
            box-shadow: 0 8px 30px rgba(0, 255, 209, 0.2); 
        }
        .card img { border-radius: 8px; margin-bottom: 1rem; object-fit: cover; width: 100%; aspect-ratio: 1/1;}
        .card .title { font-size: 1.1rem; font-weight: 700; color: #FFFFFF; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .card .subtitle { font-size: 0.9rem; font-weight: 400; color: #AAAAAA; margin-bottom: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# ---------- Recommendation Engines ----------
def generate_recommendations(basis, num_recs):
    st.session_state.recommendations = OrderedDict()
    entity_type = basis['type']

    with st.spinner("🎧 Tuning into the right frequency..."):
        time.sleep(1)
        if entity_type == 'track':
            recs = get_recommendations("track.getSimilar", basis, limit=num_recs)
            for r in recs:
                st.session_state.recommendations[tuple(r.values())] = r

            if len(st.session_state.recommendations) < num_recs:
                sim_artists = get_similar_artists(basis['artist'], limit=2)
                for sa in sim_artists:
                    recs = get_recommendations("artist.getTopTracks", {"artist": sa}, limit=2)
                    for r in recs:
                        st.session_state.recommendations.setdefault(tuple(r.values()), r)

        elif entity_type == 'artist':
            recs = get_recommendations("artist.getTopTracks", basis, limit=num_recs)
            for r in recs:
                st.session_state.recommendations[tuple(r.values())] = r

            if len(st.session_state.recommendations) < num_recs:
                sim_artists = get_similar_artists(basis['artist'], limit=3)
                for sa in sim_artists:
                    recs = get_recommendations("artist.getTopTracks", {"artist": sa}, limit=2)
                    for r in recs:
                        st.session_state.recommendations.setdefault(tuple(r.values()), r)

    # Add images (real cover first; fallback to genre image)
    with st.spinner("Adding the final artistic touches..."):
        time.sleep(1)
        for key, rec in list(st.session_state.recommendations.items()):
            cover = get_cover_image(rec['artist'], rec['track'])
            if cover:
                st.session_state.recommendations[key]['art'] = cover
            else:
                if not rec.get('art'):
                    tags = get_top_tags_for_entity('track', rec['track'], rec['artist'])
                    st.session_state.recommendations[key]['art'] = get_genre_image_url(tags)

def display_recommendations():
    recs_list = list(st.session_state.recommendations.values())[:st.session_state.num_recs]
    st.markdown("### 🔮 Your Personalized Recommendations:")
    cols = st.columns(4)
    for i, rec in enumerate(recs_list):
        with cols[i % 4]:
            st.markdown(f"""
            <div class="card">
                <img src="{rec['art']}" onerror="this.onerror=null;this.src='https://placehold.co/400x400/708090/FFFFFF?text=Music&font=inter';">
                <div class="title" title="{rec['track']}">{rec['track']}</div>
                <div class="subtitle">{rec['artist']}</div>
            </div>""", unsafe_allow_html=True)
            st.link_button("Listen on Last.fm 🎵", rec['url'], use_container_width=True)

def display_insights(basis):
    st.subheader(" Recommendation Insights")
    entity_type = basis['type']
    with st.spinner(f"Fetching insights for {basis.get('artist') or basis.get('track')}..."):
        info = get_artist_info(basis['artist']) if entity_type == 'artist' else get_track_info(basis['track'], basis['artist'])

    if not info:
        st.warning("Could not retrieve detailed insights for this selection.")
        return

    col1, col2 = st.columns([1, 2])

    # ------- COVER-FOCUSED IMAGE BLOCK (updated) -------
    with col1:
        # Always try to show a COVER image in Insights
        cover_url = None

        if entity_type == 'track':
            # Robust fallbacks for names coming from info OR the sidebar basis
            artist_name = (info.get('artist') or basis.get('artist') or '').strip()
            track_name  = (info.get('name')   or basis.get('track')  or '').strip()

            cover_url = (
                get_cover_image(artist_name, track_name)
                or info.get('art')
            )

        else:  # entity_type == 'artist'
            artist_name = (info.get('name') or basis.get('artist') or '').strip()

            # Try to fetch a representative cover from the artist's top track
            try:
                top = get_recommendations("artist.getTopTracks", {"artist": artist_name}, limit=1)
                if top:
                    t0 = top[0]
                    cover_url = get_cover_image(t0.get('artist', ''), t0.get('track', '')) or t0.get('art')
            except Exception:
                pass

            # If we still don't have a cover, fall back to the artist image
            if not cover_url:
                cover_url = get_artist_image(artist_name) or info.get('art')

        # Final genre fallback to avoid empty image
        cover_url = cover_url or get_genre_image_url(info.get('tags', []))

        st.markdown(
            f'<img src="{cover_url}" style="border-radius:12px;" '
            "onerror=\"this.onerror=null;this.src='https://placehold.co/400x400/708090/FFFFFF?text=Music&font=inter';\">",
            unsafe_allow_html=True
        )
    # ------- END IMAGE BLOCK -------

    with col2:
        st.markdown(f"### {info['name']}")
        if entity_type == 'track':
            st.markdown(f"#### by {info['artist']}")
        tags_line = "`, `".join(info.get('tags', []))
        st.markdown(f"**Top Tags:** `{tags_line}`")
        summary = info.get('summary', '') or ''
        summary_text = summary.split('. ', 1)[0] + '.' if '. ' in summary else summary
        if not summary_text or "biography is not available" in summary_text.lower():
            summary_text = f"No detailed summary available for {info['name']}."
        st.markdown(f"<p style='color:#AAAAAA;'>{summary_text}</p>", unsafe_allow_html=True)

# ----------------------- MAIN LOGIC -----------------------
def load_css_and_title():
    load_css()
    st.title("🎧 MelodyTune: Music Recommender")

load_css_and_title()

# Initialize session state
if 'recommendations' not in st.session_state:
    st.session_state.recommendations = None
if 'recommendation_basis' not in st.session_state:
    st.session_state.recommendation_basis = None

with st.sidebar:
    st.header("Start Your Discovery", "🎶")
    st.markdown("Enter an artist, a track, or both!")
    artist_input = st.text_input("Artist Name ", value="Linkin Park")
    track_input = st.text_input("Track Name (Optional)", value="Numb")
    st.session_state.num_recs = st.slider("Number of Recommendations", 4, 12, 8, 4)

    if st.button("Get Recommendations", use_container_width=True, type="primary"):
        st.session_state.recommendations = None
        basis = None

        if artist_input and track_input:
            basis = {'type': 'track', 'track': track_input, 'artist': artist_input}
        elif artist_input:
            basis = {'type': 'artist', 'artist': artist_input}
        elif track_input:
            with st.spinner(f"Finding artist for '{track_input}'..."):
                top_track_match = search_track(track_input)
                if top_track_match:
                    st.info(
                        f"Found **{top_track_match['name']}** by **{top_track_match['artist']}**. "
                        "Using this for recommendations.",
                        icon="💡"
                    )
                    basis = {'type': 'track', 'track': top_track_match['name'], 'artist': top_track_match['artist']}
                else:
                    st.error(f"Could not find a match for '{track_input}'. Please also provide an artist.", icon="❌")
        else:
            st.warning("Please enter an artist or a track name to begin.", icon="⚠️")

        st.session_state.recommendation_basis = basis
        st.rerun()

if st.session_state.recommendation_basis:
    if st.session_state.recommendations is None:
        st.markdown("##### Generating diverse recommendations...")
        generate_recommendations(st.session_state.recommendation_basis, st.session_state.num_recs)

    tab1, tab2 = st.tabs(["🎵 Recommendations", "📊 Insights"])
    with tab1:
        display_recommendations()
    with tab2:
        display_insights(st.session_state.recommendation_basis)
else:
    st.markdown("""
    Welcome to MelodyTune! This application provides **diverse music recommendations**.  
    Our intelligent system attempts to **recognize your intended song/artist** even with typos.
    It can work with just an artist, just a track, or both!
    """)
    st.info("Enter an artist or track in the sidebar and start your journey! ", icon="👈")

st.markdown("---")
st.markdown("Built with ❤️ using Last.fm API and Streamlit.")


