/** Basemap and confidence colour constants shared by map views. */
const ENV_URL = import.meta.env.VITE_BASEMAP_URL as string | undefined;
export const BASEMAPS = {
  satellite: {
    tiles: [
      ENV_URL ??
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    ],
    attribution: ENV_URL ? 'Basemap' : 'Imagery © Esri, Maxar, Earthstar Geographics',
    paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.8 },
  },
  dark: {
    tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors © CARTO',
    paint: { 'raster-saturation': -1, 'raster-brightness-max': 0.7 },
  },
} as const;
export type BasemapKey = keyof typeof BASEMAPS;

export const CONF_COLOR = { high: '#e8735a', medium: '#e6b455', low: '#9aa79b' } as const;
