import { getOperationsOverview } from "../api/operationsApi.js";
import useAsyncResource from "./useAsyncResource.js";

export default function useOverviewData() {
  return useAsyncResource(getOperationsOverview);
}
