import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GridSentinel — SCADA Command Center",
  description:
    "Physics-aware cyber-physical anomaly detection dashboard for Indian power distribution SCADA networks.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://api.mapbox.com/mapbox-gl-js/v3.7.0/mapbox-gl.css"
          rel="stylesheet"
        />
      </head>
      <body className="bg-[#0B0F19] text-gray-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
