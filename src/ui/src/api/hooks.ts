import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiClient } from "./client";
import type { components } from "./schema";

export type PhotoSummary = components["schemas"]["PhotoSummary"];
export type PhotoDetail = components["schemas"]["PhotoDetailResponse"];
export type AiResultSummary = components["schemas"]["AiResultSummary"];
export type SearchQueryRequest = components["schemas"]["SearchQueryRequest"];
export type SearchResultItem = components["schemas"]["SearchResultItem"];
export type AppSettings = components["schemas"]["AppSettings"];
export type SettingsPatch = components["schemas"]["SettingsPatch"];
export type PluginSummary = components["schemas"]["PluginSummary"];

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

export function usePhotoDetail(photoId: string) {
  return useQuery({
    queryKey: ["photo", photoId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/photos/{photo_id}", {
        params: { path: { photo_id: photoId } },
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: async (query: SearchQueryRequest) => {
      const { data, error } = await apiClient.POST("/api/v1/search", {
        body: query,
      });
      if (error) throw error;
      return data;
    },
  });
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/settings");
      if (error) throw error;
      return data;
    },
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (patch: SettingsPatch) => {
      const { data, error } = await apiClient.PATCH("/api/v1/settings", {
        body: patch,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function usePlugins() {
  return useQuery({
    queryKey: ["plugins"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/plugins");
      if (error) throw error;
      return data;
    },
  });
}

export function useUpdatePlugin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      pluginId,
      enabled,
    }: {
      pluginId: string;
      enabled: boolean;
    }) => {
      const { data, error } = await apiClient.PATCH(
        "/api/v1/plugins/{plugin_id}",
        {
          params: { path: { plugin_id: pluginId } },
          body: { enabled },
        },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["plugins"] });
    },
  });
}
