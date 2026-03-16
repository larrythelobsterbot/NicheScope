import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NicheScope - E-Commerce Niche Research Dashboard",
  description:
    "Track product trends, analyze margins, and monitor competitors for dropshipping and private label businesses.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="ambient-bg" />
        {children}
      </body>
    </html>
  );
}
