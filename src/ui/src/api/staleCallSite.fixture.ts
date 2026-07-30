import { apiClient } from "./client";

/**
 * Proves the generated client pins call sites to the real schema: `/version`
 * only ever had `core_api_version`, so a stale reference to a field that
 * doesn't exist must fail to compile. If the schema regeneration pipeline
 * ever stops producing named response fields (e.g. reverts to an untyped
 * dict), this `@ts-expect-error` goes unused and `tsc --noEmit` fails --
 * exactly the regression this fixture exists to catch.
 */
export async function staleCallSite(): Promise<void> {
  const { data } = await apiClient.GET("/version");
  // @ts-expect-error -- `legacy_version_field` was never a real response field
  void data?.legacy_version_field;
}
