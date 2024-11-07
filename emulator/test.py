import pandas as pd
import pyqtgraph as pg

MAP_IMAGE_PATH = "alidade_satellite.jpg"
TOWERS_DATA_PATH = "250.csv"
MAX_TOWERS_DISPLAY = 2000
MOSCOW_CENTER_LON = 37.618423
MOSCOW_CENTER_LAT = 55.751244
MAP_ZOOM = 13

towers_df = pd.read_csv(TOWERS_DATA_PATH)
if len(towers_df) > MAX_TOWERS_DISPLAY:
    towers_df = towers_df.sample(n=MAX_TOWERS_DISPLAY, random_state=1)

latitudes = towers_df['lat'].values
longitudes = towers_df['lon'].values
mccs = towers_df['mcc'].values
mncs = towers_df['area'].values  # Получаем MNC
cells = towers_df['cell'].values

tower_scatter = pg.ScatterPlotItem(
    x=longitudes, y=latitudes, pen=pg.mkPen(None), brush=pg.mkBrush(0, 0, 255, 120), size=5
)
towers = list(zip(longitudes, latitudes, mccs, mncs, cells))

towers_with_distance = [
    (lon, lat, mcc, mnc, cell)
    for lon, lat, mcc, mnc, cell in towers
]