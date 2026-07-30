import createClient from "openapi-fetch";

import type { paths } from "./schema";
import { getLaunchToken } from "./launchToken";

export const apiClient = createClient<paths>({
  baseUrl: window.location.origin,
});

apiClient.use({
  onRequest({ request }) {
    request.headers.set("Authorization", `Bearer ${getLaunchToken()}`);
    return request;
  },
});
