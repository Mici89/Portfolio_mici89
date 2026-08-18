import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "企业 AI 应用作品集",
  description: "AI Database Agent、企信雷达与 Enterprise Knowledge Agent 项目案例。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="site-header">
          <Link className="brand" href="/" aria-label="返回作品集首页">
            <span className="brand-mark" aria-hidden="true">M</span>
            <span><strong>Enterprise AI</strong><small>portfolio / 2026</small></span>
          </Link>
          <nav aria-label="主导航">
            <Link href="/#work">项目</Link>
            <Link href="/#capabilities">能力</Link>
            <Link href="/#about">关于</Link>
          </nav>
        </header>
        {children}
        <footer className="site-footer">
          <span>Enterprise AI Portfolio</span>
          <span>所有演示数据均为模拟或脱敏数据</span>
        </footer>
      </body>
    </html>
  );
}
