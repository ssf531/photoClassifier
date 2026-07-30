import type React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { ProgressSocketProvider } from "./api/ProgressSocketContext";
import { GridPage } from "./routes/GridPage";
import { PhotoDetailRoute } from "./routes/PhotoDetailRoute";
import { PluginsPage } from "./routes/PluginsPage";
import { SearchPage } from "./routes/SearchPage";
import { SettingsPage } from "./routes/SettingsPage";

const queryClient = new QueryClient();

export function App(): React.JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <ProgressSocketProvider>
        <BrowserRouter>
          <nav>
            <Link to="/">Grid</Link>
            <Link to="/search">Search</Link>
            <Link to="/settings">Settings</Link>
            <Link to="/plugins">Plugins</Link>
          </nav>
          <Routes>
            <Route path="/" element={<GridPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/plugins" element={<PluginsPage />} />
            <Route path="/photo/:photoId" element={<PhotoDetailRoute />} />
          </Routes>
        </BrowserRouter>
      </ProgressSocketProvider>
    </QueryClientProvider>
  );
}
