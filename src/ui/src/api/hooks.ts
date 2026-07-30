import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { apiClient } from "./client";
import type { components } from "./schema";

export type PhotoSummary = components["schemas"]["PhotoSummary"];

const PHOTO_LIST_PAGE_SIZE = 200;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/health");
      if (error) throw error;
      return data;
    },
  });
}

export function useVersion() {
  return useQuery({
    queryKey: ["version"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/version");
      if (error) throw error;
      return data;
    },
  });
}

export function usePhotoList() {
  return useInfiniteQuery({
    queryKey: ["photos"],
    queryFn: async ({ pageParam }: { pageParam: number }) => {
      const { data, error } = await apiClient.GET("/api/v1/photos", {
        params: { query: { limit: PHOTO_LIST_PAGE_SIZE, offset: pageParam } },
      });
      if (error) throw error;
      return data;
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.next_offset ?? undefined,
  });
}
