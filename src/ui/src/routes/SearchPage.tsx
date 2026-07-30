import type React from "react";

import { useSearch } from "../api/hooks";
import { SearchBar } from "../components/SearchBar";

export function SearchPage(): React.JSX.Element {
  const search = useSearch();

  return (
    <div>
      <SearchBar onSubmit={(query) => search.mutate(query)} />
      {search.isPending && <p>Searching...</p>}
      {search.isError && <p>Search failed.</p>}
      {search.data && (
        <p>
          {search.data.items.length} result
          {search.data.items.length === 1 ? "" : "s"}
        </p>
      )}
    </div>
  );
}
