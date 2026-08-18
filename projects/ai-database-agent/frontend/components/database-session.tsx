"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type {
  ConnectionInfo,
  DatabaseSnapshot,
} from "@/lib/types";

type DatabaseSessionValue = {
  ready: boolean;
  connectionInfo: ConnectionInfo | null;
  snapshot: DatabaseSnapshot | null;
  connect: (
    connectionInfo: ConnectionInfo,
    snapshot: DatabaseSnapshot,
  ) => void;
  disconnect: () => void;
};

const STORAGE_KEY = "ai-db.active-database.v1";

const DatabaseSessionContext = createContext<DatabaseSessionValue | null>(null);

export function DatabaseSessionProvider({children}: {children: ReactNode}) {
  const [ready, setReady] = useState(false);
  const [connectionInfo, setConnectionInfo] = useState<ConnectionInfo | null>(null);
  const [snapshot, setSnapshot] = useState<DatabaseSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      try {
        const stored = window.sessionStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as {
            connectionInfo: ConnectionInfo;
            snapshot: DatabaseSnapshot;
          };
          setConnectionInfo(parsed.connectionInfo);
          setSnapshot(parsed.snapshot);
        }
      } catch {
        window.sessionStorage.removeItem(STORAGE_KEY);
      } finally {
        setReady(true);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<DatabaseSessionValue>(() => ({
    ready,
    connectionInfo,
    snapshot,
    connect: (nextConnectionInfo, nextSnapshot) => {
      setConnectionInfo(nextConnectionInfo);
      setSnapshot(nextSnapshot);
      window.sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          connectionInfo: nextConnectionInfo,
          snapshot: nextSnapshot,
        }),
      );
    },
    disconnect: () => {
      setConnectionInfo(null);
      setSnapshot(null);
      window.sessionStorage.removeItem(STORAGE_KEY);
    },
  }), [connectionInfo, ready, snapshot]);

  return (
    <DatabaseSessionContext.Provider value={value}>
      {children}
    </DatabaseSessionContext.Provider>
  );
}

export function useDatabaseSession(): DatabaseSessionValue {
  const value = useContext(DatabaseSessionContext);
  if (!value) {
    throw new Error("useDatabaseSession must be used inside DatabaseSessionProvider");
  }
  return value;
}
