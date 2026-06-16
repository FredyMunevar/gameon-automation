import "./globals.css";

export const metadata = {
  title: "Polla GameOn — Pronósticos",
  description: "Mis picks del Mundial 2026 (modelo Poisson-Elo) y su historial.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
