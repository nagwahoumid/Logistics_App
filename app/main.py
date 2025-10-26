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

app = FastAPI(title="NagwaRide API (MVP)")

# CORS (relaxed for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# Serve everything inside /web at /web/...
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

# Landing page -> web/index.html
@app.get("/")
def index():
    return FileResponse("web/index.html")

# Build a small road graph (3 km radius around central London)
center_latlon = (51.509, -0.118)
G = ox.graph_from_point(center_latlon, dist=3000, network_type="drive")
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)
print("Road network ready.")

class RouteRequest(BaseModel):
    start: Tuple[float, float]   # (lat, lon)
    end:   Tuple[float, float]   # (lat, lon)

@app.get("/health")
def health():
    return {"ok": True, "service": "NagwaRide"}

@app.post("/route")
def route(req: RouteRequest):
    try:
        # nearest nodes
        orig = ox.nearest_nodes(G, X=req.start[1], Y=req.start[0])
        dest = ox.nearest_nodes(G, X=req.end[1],   Y=req.end[0])

        # fastest path by travel time
        path: List[int] = nx.shortest_path(G, orig, dest, weight="travel_time")

        # polyline coordinates (lon, lat)
        coords = [(G.nodes[n]["x"], G.nodes[n]["y"]) for n in path]
        line = LineString(coords)

        # distance + duration (m, s)
        length_m   = float(sum(ox.utils_graph.get_route_edge_attributes(G, path, "length")))
        duration_s = float(sum(ox.utils_graph.get_route_edge_attributes(G, path, "travel_time")))

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

