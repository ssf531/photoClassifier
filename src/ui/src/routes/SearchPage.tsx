import type React from "react";

import { useSearch } from "../api/hooks";
import { SearchBar } from "../components/SearchBar";
import { SearchResults } from "../components/SearchResults";

export function SearchPage(): React.JSX.Element {
  const search = useSearch();

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <SearchBar onSubmit={(query) => search.mutate(query)} />
      {search.isPending && <p>Searching...</p>}
      {search.isError && <p>Search failed.</p>}
      {search.data && (
        <div style={{ flex: 1, minHeight: 0 }}>
          <SearchResults results={search.data.items} />
        </div>
      )}
    </div>
  );
}
