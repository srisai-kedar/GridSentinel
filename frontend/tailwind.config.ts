import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: {
          bg: "var(--canvas-bg)",
        },
        surface: {
          panel: "var(--surface-panel)",
          subdued: "var(--surface-subdued)",
          hover: "var(--surface-hover)",
        },
        border: {
          hairline: "var(--border-hairline)",
        },
        accent: {
          violet: "var(--accent-violet)",
          violetLight: "var(--accent-violet-light)",
          violetDark: "var(--accent-violet-dark)",
        },
        scada: {
          bg: "#08090D",
          panel: "#0E1118",
          panelSubdued: "#131722",
          panelHover: "#181E2C",
          panelBorder: "rgba(255, 255, 255, 0.07)",
          textPrimary: "#EDEDF0",
          textSecondary: "#9CA3AF",
          textMuted: "#5A6275",
          normal: "#10B981",       // Emerald Green (Normal)
          normalGlow: "rgba(16, 185, 129, 0.25)",
          fault: "#F59E0B",        // Amber (Natural Fault)
          faultGlow: "rgba(245, 158, 11, 0.25)",
          cyber: "#EF4444",        // Crimson (Cyber Intrusion)
          cyberGlow: "rgba(239, 68, 68, 0.25)",
          nodata: "#4B5563",       // Slate (Disconnected / No data)
          accent: "#8B5CF6",       // Muted Violet Accent
        }
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "Courier New", "monospace"],
      },
      borderRadius: {
        'scada': '10px',
        'scada-sm': '6px',
        'scada-lg': '14px',
      },
      animation: {
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'telemetry-flow': 'telemetryFlow 1.8s linear infinite',
      },
      keyframes: {
        telemetryFlow: {
          '0%': { strokeDashoffset: '24' },
          '100%': { strokeDashoffset: '0' },
        }
      }
    },
  },
  plugins: [],
};
export default config;
