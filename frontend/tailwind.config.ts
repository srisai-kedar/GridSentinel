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
        background: "var(--background)",
        foreground: "var(--foreground)",
        // Strict unified SCADA colors:
        scada: {
          bg: "#0B0F19",
          panel: "#111827",
          panelBorder: "#1F2937",
          panelHover: "#1E293B",
          textPrimary: "#F3F4F6",
          textSecondary: "#9CA3AF",
          textMuted: "#6B7280",
          normal: "#10B981",       // Green (Normal)
          normalGlow: "rgba(16, 185, 129, 0.3)",
          fault: "#F59E0B",        // Amber (Natural Fault)
          faultGlow: "rgba(245, 158, 11, 0.3)",
          cyber: "#EF4444",        // Red (Cyber Intrusion)
          cyberGlow: "rgba(239, 68, 68, 0.3)",
          nodata: "#6B7280",       // Gray (Disconnected / No data)
        }
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "Courier New", "monospace"],
      },
      animation: {
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
};
export default config;
