from flask import Flask, render_template, request, redirect, session, url_for
import openrouteservice
from geopy.geocoders import Nominatim
import folium
import spotipy
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -----------------------------
# OpenRouteService API key
# -----------------------------
API_KEY = ""
client = openrouteservice.Client(key=API_KEY)

# -----------------------------
# Spotify credentials
# -----------------------------
SPOTIPY_CLIENT_ID = ""
SPOTIPY_CLIENT_SECRET = ""
SPOTIPY_REDIRECT_URI = ""
SCOPE = "user-read-playback-state,user-modify-playback-state,user-read-currently-playing,playlist-read-private"


# -----------------------------
# Helper function: Geocode a place
# -----------------------------
def get_coordinates(place):
    geolocator = Nominatim(user_agent="route_finder_app")

    try:
        locations = geolocator.geocode(place, exactly_one=False, limit=3, addressdetails=True)
    except Exception as e:
        print(f"Nominatim error: {e}")
        locations = None

    if locations:
        best = locations[0]
        return best.longitude, best.latitude

    # Optional: fallback to ORS pelias search
    try:
        geocode_result = client.pelias_search(text=place, size=3)
        if geocode_result and geocode_result['features']:
            coords = geocode_result['features'][0]['geometry']['coordinates']
            return coords[0], coords[1]
    except Exception as e:
        print(f"Fallback geocoding error: {e}")

    return None, None


# -----------------------------
# Home page
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        end_place = request.form.get("end")

        # Get start location from hidden fields if available
        start_lat = request.form.get("start_lat")
        start_lon = request.form.get("start_lon")
        start_place = request.form.get("start")

        if start_lat and start_lon:
            start_lat = float(start_lat)
            start_lon = float(start_lon)
        else:
            if not start_place:
                return render_template("index.html", error="Enter a starting place or use current location.")
            start_lon, start_lat = get_coordinates(start_place)
            if not start_lon or not start_lat:
                return render_template("index.html", error="Could not find the starting place.")

        # Destination geocoding
        end_lon, end_lat = get_coordinates(end_place)
        if not end_lon or not end_lat:
            return render_template("index.html", error="Could not find the destination.")

        # Get route
        try:
            route = client.directions(
                coordinates=[[start_lon, start_lat], [end_lon, end_lat]],
                profile='driving-car',
                format='geojson'
            )
            summary = route['features'][0]['properties']['summary']
            distance_km = summary['distance'] / 1000
            duration_min = summary['duration'] / 60
        except Exception as e:
            return render_template("index.html", error=f"Error fetching route: {e}")

        # Auto-zoom to route bounds
        coords = route['features'][0]['geometry']['coordinates']
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        sw = [min(lats), min(lons)]
        ne = [max(lats), max(lons)]

        m = folium.Map(tiles='CartoDB positron')
        folium.GeoJson(route, name="route").add_to(m)
        m.fit_bounds([sw, ne])

        # Markers
        folium.Marker([start_lat, start_lon],
                      tooltip="Start",
                      popup="You are here" if start_lat and start_lon else start_place,
                      icon=folium.Icon(color='green')).add_to(m)

        folium.Marker([end_lat, end_lon],
                      tooltip="Destination",
                      popup=end_place,
                      icon=folium.Icon(color='red')).add_to(m)

        map_html = m._repr_html_()

        return render_template(
            "map.html",
            distance=round(distance_km, 2),
            duration=round(duration_min, 1),
            start=start_place if start_place else "Current Location",
            end=end_place,
            folium_map=map_html
        )

    return render_template("index.html")


# -----------------------------
# Spotify Connect
# -----------------------------
@app.route("/connect_spotify")
def connect_spotify():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE
    )
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route("/spotify/callback")
def spotify_callback():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope=SCOPE
    )
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('spotify_dashboard'))


@app.route("/spotify/dashboard")
def spotify_dashboard():
    token_info = session.get('token_info')
    if not token_info:
        return redirect(url_for('connect_spotify'))

    sp = spotipy.Spotify(auth=token_info['access_token'])
    user = sp.current_user()
    playlists = sp.current_user_playlists()

    return render_template("spotify_dashboard.html", user=user, playlists=playlists['items'])


if __name__ == "__main__":
    app.run(debug=True)

