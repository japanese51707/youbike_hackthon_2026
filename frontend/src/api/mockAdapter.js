import {
  mutateMockState,
  readMockState,
  resetMockState,
} from "../state/mockStore.js";

export class MockDataError extends Error {
  constructor(message) {
    super(message);
    this.name = "MockDataError";
  }
}

function requireArray(value, field) {
  if (!Array.isArray(value)) {
    throw new MockDataError(`Mock 資料欄位 ${field} 必須是陣列`);
  }
  return value;
}

function requireObject(value, field) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new MockDataError(`Mock 資料欄位 ${field} 必須是物件`);
  }
  return value;
}

function findOrThrow(collection, predicate, label) {
  const item = collection.find(predicate);
  if (!item) {
    throw new MockDataError(`找不到 ${label}`);
  }
  return item;
}

export const mockAdapter = {
  async getDashboard() {
    const state = readMockState();
    return {
      stations: requireArray(state.stations, "stations"),
      stationDetail: requireObject(state.station_detail, "station_detail"),
      heatmap: requireObject(state.heatmap, "heatmap"),
      recommendations: requireArray(state.recommendations, "recommendations"),
      kpi: requireObject(state.kpi, "kpi"),
      alerts: requireArray(state.alerts, "alerts"),
      weather: requireObject(state.weather, "weather"),
      events: requireArray(state.events, "events"),
      vehicles: requireArray(state.vehicles, "vehicles"),
    };
  },

  async getStationDetail(stationId) {
    const state = readMockState();
    const station = findOrThrow(
      requireArray(state.stations, "stations"),
      (item) => item.station_id === stationId,
      `站點 ${stationId}`,
    );
    const detail = requireObject(state.station_detail, "station_detail");

    if (detail.current?.station_id === stationId) {
      return detail;
    }

    return {
      current: station,
      prediction: null,
      params: null,
      history: [],
    };
  },

  async confirmRecommendation(recommendationId) {
    const nextState = mutateMockState((draft) => {
      const recommendation = findOrThrow(
        requireArray(draft.recommendations, "recommendations"),
        (item) => item.recommendation_id === recommendationId,
        `調度建議 ${recommendationId}`,
      );
      recommendation.demo_status = "confirmed";
      recommendation.confirmed_at = new Date().toISOString();
    });
    return findOrThrow(
      nextState.recommendations,
      (item) => item.recommendation_id === recommendationId,
      `調度建議 ${recommendationId}`,
    );
  },

  async acknowledgeAlert(alertId) {
    const nextState = mutateMockState((draft) => {
      const alert = findOrThrow(
        requireArray(draft.alerts, "alerts"),
        (item) => item.alert_id === alertId,
        `警示 ${alertId}`,
      );
      alert.acknowledged = true;
    });
    return findOrThrow(
      nextState.alerts,
      (item) => item.alert_id === alertId,
      `警示 ${alertId}`,
    );
  },

  async getOperatorWorkspace() {
    const state = readMockState();
    return {
      tasks: requireArray(state.tasks, "tasks"),
      operators: requireArray(state.operators, "operators"),
    };
  },

  async completeTaskStop(taskId, sequence) {
    const nextState = mutateMockState((draft) => {
      const task = findOrThrow(
        requireArray(draft.tasks, "tasks"),
        (item) => item.task_id === taskId,
        `任務 ${taskId}`,
      );
      const stop = findOrThrow(
        requireArray(task.route, "tasks.route"),
        (item) => item.seq === sequence,
        `任務停靠點 ${sequence}`,
      );
      stop.stop_status = "completed";
      const isCompleted = task.route.every(
        (item) => item.stop_status === "completed",
      );
      task.task_status = isCompleted ? "completed" : "in_progress";
    });
    return findOrThrow(
      nextState.tasks,
      (item) => item.task_id === taskId,
      `任務 ${taskId}`,
    );
  },

  async getOverview() {
    const state = readMockState();
    return {
      overview: requireObject(state.dispatch_overview, "dispatch_overview"),
      kpi: requireObject(state.kpi, "kpi"),
      simulation: requireObject(state.simulation_replay, "simulation_replay"),
      timeline: requireObject(state.timeline, "timeline"),
      stations: requireArray(state.stations, "stations"),
      operators: requireArray(state.operators, "operators"),
      auditLogs: requireArray(state.audit_logs, "audit_logs"),
      events: requireArray(state.events, "events"),
    };
  },

  async resetDemo() {
    resetMockState();
    return { reset: true };
  },
};
