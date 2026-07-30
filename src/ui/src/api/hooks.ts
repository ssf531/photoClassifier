import { useQuery } from "@tanstack/react-query";

import { apiClient } from "./client";

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
