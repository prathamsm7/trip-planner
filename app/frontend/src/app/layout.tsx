import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Safar AI — Trip Planner",
  description: "Conversation-based trip planning",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full overflow-hidden">
      <body className="h-full overflow-hidden">{children}</body>
    </html>
  );
}
