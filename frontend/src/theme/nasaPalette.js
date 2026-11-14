/**
 * Official NASA Color Palette (from user specification)
 * Used consistently across all UI surfaces, charts, and simulation overlays.
 */
export const NASA_PALETTE = {
  blueYonder: {
    name: "BLUE YONDER",
    hex: "#2E96F5",
    pms: "PMS 279 C (equiv)",
    role: "Telemetri Veri Hatları, Hava Akışı Vektörleri, Nominal Durum",
  },
  neonBlue: {
    name: "NEON BLUE",
    hex: "#0960E1",
    pms: "PMS 2728 C (equiv)",
    role: "Birincil Etkileşim, Aktif Kontroller, Mikroçekim Alev Çekirdeği",
  },
  electricBlue: {
    name: "ELECTRIC BLUE",
    hex: "#0042A6",
    pms: "PMS 2146 C",
    role: "Yapısal Paneller, Kart Başlıkları, Grafik Izgara ve Çerçeveler",
  },
  deepBlue: {
    name: "DEEP BLUE",
    hex: "#07173F",
    pms: "PMS 295 C",
    role: "Ana Komuta Arka Planı, Derin Uzay ve Yanma Odası Zemini",
  },
  rocketRed: {
    name: "ROCKET RED",
    hex: "#E43700",
    pms: "PMS BRIGHT RED C",
    role: "Yüksek Yangın İhtimali, Kritik Eşik, Aktif Alev Cephesi",
  },
  martianRed: {
    name: "MARTIAN RED",
    hex: "#8E1100",
    pms: "PMS 7622 C (equiv)",
    role: "Kritik Tehlike Bölgesi Dolgusu, Termal Risk Zemin Vurgusu",
  },
  neonYellow: {
    name: "NEON YELLOW",
    hex: "#EAFE07",
    pms: "PMS NEON 387",
    role: "AI Öneri Vurgusu, Uyarı İşaretçisi, Aktif Çalışma Noktası (Crosshair)",
  },
  white: {
    name: "WHITE",
    hex: "#FFFFFF",
    pms: "WHITE",
    role: "Birincil Tipografi, Sayısal Telemetri Okumaları, Yüksek Kontrast",
  },
};

export const PALETTE_LIST = Object.values(NASA_PALETTE);
