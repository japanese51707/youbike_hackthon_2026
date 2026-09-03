import { useCallback, useEffect, useState } from "react";
import {
  acknowledgeAlert,
  confirmRecommendation,
} from "../api/dispatchApi.js";
import {
  getDashboardData,
  getStationDetail,
} from "../api/stationsApi.js";
import useAsyncResource from "./useAsyncResource.js";

export default function useDashboardData() {
  const resource = useAsyncResource(getDashboardData);
  const [selectedStationId, setSelectedStationId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    if (!selectedStationId && resource.data?.stationDetail?.current) {
      setSelectedStationId(resource.data.stationDetail.current.station_id);
    }
  }, [resource.data, selectedStationId]);

  useEffect(() => {
    if (!selectedStationId) return undefined;
    let active = true;
    setDetailLoading(true);
    setDetailError(null);
    getStationDetail(selectedStationId)
      .then((result) => {
        if (active) setDetail(result);
      })
      .catch((error) => {
        if (active) setDetailError(error);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedStationId, resource.data]);

  const handleConfirmRecommendation = useCallback(
    async (recommendationId) => {
      await confirmRecommendation(recommendationId);
      await resource.reload();
    },
    [resource.reload],
  );

  const handleAcknowledgeAlert = useCallback(
    async (alertId) => {
      await acknowledgeAlert(alertId);
      await resource.reload();
    },
    [resource.reload],
  );

  return {
    ...resource,
    detail,
    detailError,
    detailLoading,
    selectedStationId,
    selectStation: setSelectedStationId,
    confirmRecommendation: handleConfirmRecommendation,
    acknowledgeAlert: handleAcknowledgeAlert,
  };
}
