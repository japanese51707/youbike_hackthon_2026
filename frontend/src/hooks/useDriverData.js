import { getDriverWorkspace } from "../api/driverApi.js";
import useAsyncResource from "./useAsyncResource.js";

export default function useDriverData() {
  return useAsyncResource(getDriverWorkspace, { cacheKey: "driver-workspace" });
}
