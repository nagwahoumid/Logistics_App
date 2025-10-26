# app/main.py
from typing import Tuple, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel
import osmnx as ox
import networkx as nx
from shapely.geometry import LineString, mapping
from pyproj import Transformer  # <-- NEW

app = FastAPI(title="NagwaRide API (MVP)")

# Allow connections from anywhere (for browser)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve your web folder
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

@app.get("/")
def index():
    return FileResponse("web/index.html")

# Build small road graph
center_latlon = (51.509, -0.118)
G = ox.graph_from_point(center_latlon, dist=3000, network_type="drive")
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)

# Project to meters (this avoids scikit-learn!)
Gp = ox.project_graph(G)

# Create converters for coordinates
to_xy = Transformer.from_crs("epsg:4326", Gp.graph["crs"], always_xy=True)
to_ll = Transformer.from_crs(Gp.graph["crs"], "epsg:4326", always_xy=True)

print("Road network ready (projected).")

class RouteRequest(BaseModel):
    start: Tuple[float, float]   # (lat, lon)
    end: Tuple[float, float]     # (lat, lon)

@app.get("/health")
def health():
    return {"ok": True, "service": "NagwaRide"}

@app.post("/route")
def route(req: RouteRequest):
    try:
        # Convert input to projected coords
        sx, sy = to_xy.transform(req.start[1], req.start[0])
        ex, ey = to_xy.transform(req.end[1], req.end[0])

        # Find nearest nodes using KDTree (no scikit-learn!)
        orig = ox.distance.nearest_nodes(Gp, sx, sy, method="kdtree")
        dest = ox.distance.nearest_nodes(Gp, ex, ey, method="kdtree")

        # Fastest path
        path: List[int] = nx.shortest_path(Gp, orig, dest, weight="travel_time")

        # Convert coords back to lon/lat for map display
        coords_xy = [(Gp.nodes[n]["x"], Gp.nodes[n]["y"]) for n in path]
        coords_ll = [to_ll.transform(x, y) for (x, y) in coords_xy]
        line = LineString(coords_ll)

        # Distance and duration
        length_m = float(sum(ox.utils_graph.get_route_edge_attributes(Gp, path, "length")))
        duration_s = float(sum(ox.utils_graph.get_route_edge_attributes(Gp, path, "travel_time")))

        return {
            "distance_m": round(length_m, 1),
            "duration_s": round(duration_s, 1),
            "geojson": {
                "type": "Feature",
                "geometry": mapping(line),
                "properties": {"name": "fastest_route"},
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing failed: {e}")