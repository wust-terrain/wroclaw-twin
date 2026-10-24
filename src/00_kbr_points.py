import geopandas as gpd, pathlib

shp = "data/raw/kbr2018/points/EtapV-2_Punkty_pomiarowe_ruchu_drogowego.shp"

g = gpd.read_file(shp).set_crs(2177, allow_override=True)
pathlib.Path("data/interim").mkdir(parents=True, exist_ok=True)
g.to_file("data/interim/kbr_points.gpkg", layer="points", driver="GPKG")
r = g[g["Kordon"].isin(["R1", "R2", "R3"])].to_crs(4326)
w, s, e, n = r.total_bounds
w, e, s, n = w - 0.043, e + 0.043, s - 0.027, n + 0.027
print(f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}")