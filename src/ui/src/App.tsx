import type React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { ProgressSocketProvider } from "./api/ProgressSocketContext";
import { CollectionsPage } from "./routes/CollectionsPage";
import { DuplicateReviewPage } from "./routes/DuplicateReviewPage";
import { GridPage } from "./routes/GridPage";
import { OnboardingPage } from "./routes/OnboardingPage";
import { PhotoDetailRoute } from "./routes/PhotoDetailRoute";
import { PluginsPage } from "./routes/PluginsPage";
import { RecommendationsPage } from "./routes/RecommendationsPage";
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
            <Link to="/collections">Collections</Link>
            <Link to="/recommendations">Recommendations</Link>
            <Link to="/duplicates">Duplicate Review</Link>
            <Link to="/onboarding">Onboarding</Link>
          </nav>
          <Routes>
            <Route path="/" element={<GridPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/plugins" element={<PluginsPage />} />
            <Route path="/collections" element={<CollectionsPage />} />
            <Route path="/recommendations" element={<RecommendationsPage />} />
            <Route path="/duplicates" element={<DuplicateReviewPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/photo/:photoId" element={<PhotoDetailRoute />} />
          </Routes>
        </BrowserRouter>
      </ProgressSocketProvider>
    </QueryClientProvider>
  );
}
