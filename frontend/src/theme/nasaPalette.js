/**
 * Official NASA Color Palette (from user specification)
 * Used consistently across all UI surfaces, charts, and simulation overlays.
 */
export const NASA_PALETTE = {
  blueYonder: {
    name: "BLUE YONDER",
    hex: "#2E96F5",
    pms: "PMS 279 C (equiv)",
    role: "Example model curves and airflow arrows",
  },
  neonBlue: {
    name: "NEON BLUE",
    hex: "#0960E1",
    pms: "PMS 2728 C (equiv)",
    role: "Primary interactions and active controls",
  },
  electricBlue: {
    name: "ELECTRIC BLUE",
    hex: "#0042A6",
    pms: "PMS 2146 C",
    role: "Panel borders, headings and chart grids",
  },
  deepBlue: {
    name: "DEEP BLUE",
    hex: "#07173F",
    pms: "PMS 295 C",
    role: "Primary text and scene background",
  },
  rocketRed: {
    name: "ROCKET RED",
    hex: "#E43700",
    pms: "PMS BRIGHT RED C",
    role: "Higher illustrative score accent",
  },
  martianRed: {
    name: "MARTIAN RED",
    hex: "#8E1100",
    pms: "PMS 7622 C (equiv)",
    role: "Model emphasis and chart fill",
  },
  neonYellow: {
    name: "NEON YELLOW",
    hex: "#EAFE07",
    pms: "PMS NEON 387",
    role: "Selected model variant and input marker",
  },
  white: {
    name: "WHITE",
    hex: "#FFFFFF",
    pms: "WHITE",
    role: "Text and high-contrast readouts",
  },
};

export const PALETTE_LIST = Object.values(NASA_PALETTE);
