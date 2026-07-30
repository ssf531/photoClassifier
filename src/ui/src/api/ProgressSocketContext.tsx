import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { createProgressSocket, type ProgressSocket } from "./progressSocket";

const ProgressSocketContext = createContext<ProgressSocket | null>(null);

export interface ProgressSocketProviderProps {
  children: ReactNode;
  createSocket?: () => ProgressSocket;
}

/**
 * Owns exactly one ProgressSocket for the app's lifetime (FEAT-062:
 * navigating between routes must not remount the WebSocket connection).
 * `useState`'s lazy initializer runs exactly once, so route changes below
 * this provider never trigger a new instance.
 */
export function ProgressSocketProvider({
  children,
  createSocket = createProgressSocket,
}: ProgressSocketProviderProps) {
  const [socket] = useState(createSocket);

  useEffect(() => {
    socket.connect();
    return () => socket.close();
  }, [socket]);

  return (
    <ProgressSocketContext.Provider value={socket}>
      {children}
    </ProgressSocketContext.Provider>
  );
}

export function useProgressSocket(): ProgressSocket {
  const socket = useContext(ProgressSocketContext);
  if (socket === null) {
    throw new Error(
      "useProgressSocket must be used within a ProgressSocketProvider",
    );
  }
  return socket;
}
