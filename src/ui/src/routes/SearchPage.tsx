import { useState } from "react";
import type React from "react";

import { useCreateCollection, useSearch } from "../api/hooks";
import { SearchBar } from "../components/SearchBar";
import { SearchResults } from "../components/SearchResults";

export function SearchPage(): React.JSX.Element {
  const search = useSearch();
  const createCollection = useCreateCollection();
  const [smartName, setSmartName] = useState("");
  const [saved, setSaved] = useState(false);

  const handleSaveSmart = (): void => {
    const trimmed = smartName.trim();
    if (!trimmed || !search.variables) {
      return;
    }
    createCollection.mutate(
      { name: trimmed, search_query: search.variables },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <SearchBar
        onSubmit={(query) => {
          search.mutate(query);
          setSaved(false);
        }}
      />
      {search.isPending && <p>Searching...</p>}
      {search.isError && <p>Search failed.</p>}
      {search.data && (
        <>
          <div>
            <label>
              Smart collection name
              <input
                type="text"
                aria-label="Smart collection name"
                value={smartName}
                onChange={(event) => setSmartName(event.target.value)}
              />
            </label>
            <button type="button" onClick={handleSaveSmart}>
              Save as smart collection
            </button>
            {saved && <span> Saved.</span>}
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <SearchResults results={search.data.items} />
          </div>
        </>
      )}
    </div>
  );
}
