import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Wikinews Structural Explorer",
  description: "Explore narrative schemas and structural analogies in news articles.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
