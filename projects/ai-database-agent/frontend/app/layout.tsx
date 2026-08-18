import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { DatabaseSessionProvider } from "@/components/database-session";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "数据工作台",
  description:
    "连接数据库、理解结构、维护语义并通过自然语言查询数据。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <DatabaseSessionProvider>{children}</DatabaseSessionProvider>
      </body>
    </html>
  );
}
