import { useCallback, useEffect, useState } from "react";
import {
  completeTaskStop,
  getOperatorWorkspace,
} from "../api/operationsApi.js";
import useAsyncResource from "./useAsyncResource.js";

export default function useOperatorData() {
  const resource = useAsyncResource(getOperatorWorkspace);
  const [selectedTaskId, setSelectedTaskId] = useState(null);

  useEffect(() => {
    if (!selectedTaskId && resource.data?.tasks?.length) {
      setSelectedTaskId(resource.data.tasks[0].task_id);
    }
  }, [resource.data, selectedTaskId]);

  const handleCompleteStop = useCallback(
    async (taskId, sequence) => {
      await completeTaskStop(taskId, sequence);
      await resource.reload();
    },
    [resource.reload],
  );

  const selectedTask =
    resource.data?.tasks?.find((task) => task.task_id === selectedTaskId) ??
    null;

  return {
    ...resource,
    selectedTask,
    selectedTaskId,
    selectTask: setSelectedTaskId,
    completeStop: handleCompleteStop,
  };
}
