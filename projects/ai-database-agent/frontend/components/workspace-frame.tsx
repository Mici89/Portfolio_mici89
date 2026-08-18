"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useDatabaseSession } from "@/components/database-session";

type WorkspaceArea = "understand" | "catalog" | "query";

const areas: Array<{
  id: WorkspaceArea;
  href: string;
  title: string;
  description: string;
}> = [
  {
    id: "understand",
    href: "/",
    title: "理解数据库",
    description: "读取结构，补全表和字段含义",
  },
  {
    id: "catalog",
    href: "/catalog",
    title: "语义目录",
    description: "查看解释、证据和审核版本",
  },
  {
    id: "query",
    href: "/query",
    title: "智能对话",
    description: "查询数据，确认后执行修改",
  },
];

function AreaIcon({area}: {area: WorkspaceArea}) {
  if (area === "catalog") {
    return (
      <span className="area-icon area-icon--catalog" aria-hidden="true">
        <i /><i /><i /><i />
      </span>
    );
  }
  if (area === "query") {
    return (
      <span className="area-icon area-icon--query" aria-hidden="true">
        <i /><i /><i />
      </span>
    );
  }
  return (
    <span className="area-icon area-icon--understand" aria-hidden="true">
      <i /><i /><i />
    </span>
  );
}

export function WorkspaceFrame({
  active,
  children,
}: {
  active: WorkspaceArea;
  children: ReactNode;
}) {
  const router = useRouter();
  const {ready, snapshot, disconnect} = useDatabaseSession();

  if (!ready) {
    return <main className="session-loading">正在读取数据库会话…</main>;
  }

  if (!snapshot) {
    return (
      <main className="session-missing">
        <div>
          <span className="product-mark">DB</span>
          <h1>尚未连接数据库</h1>
          <p>先建立数据库连接，再进入数据工作台。</p>
          <Link href="/">返回连接数据库</Link>
        </div>
      </main>
    );
  }

  const leaveDatabase = () => {
    disconnect();
    router.push("/");
  };

  return (
    <main className="workspace-shell">
      <header className="workspace-topbar">
        <Link className="product-name" href="/">
          <span className="product-mark">DB</span>
          <span>
            <strong>数据工作台</strong>
            <small>本地运行</small>
          </span>
        </Link>
        <div className="active-database">
          <span className="connection-light" />
          <span>
            <small>当前数据库</small>
            <strong>{snapshot.database.name}</strong>
          </span>
          <em>{snapshot.source.database_type} {snapshot.database.server_version}</em>
          <button type="button" onClick={leaveDatabase}>退出数据库</button>
        </div>
      </header>

      <nav className="workspace-areas" aria-label="主要功能">
        {areas.map((area) => (
          <Link
            className={area.id === active ? "active" : ""}
            href={area.href}
            key={area.id}
            aria-current={area.id === active ? "page" : undefined}
          >
            <AreaIcon area={area.id} />
            <span>
              <strong>{area.title}</strong>
              <small>{area.description}</small>
            </span>
            <b aria-hidden="true">→</b>
          </Link>
        ))}
      </nav>

      <div className="workspace-content">{children}</div>
    </main>
  );
}
