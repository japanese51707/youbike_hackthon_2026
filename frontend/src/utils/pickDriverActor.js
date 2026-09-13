const FIELD_ROLES = new Set(["operator", "driver", "depot_standby"]);

function hasTask(operator) {
  return Boolean(operator?.current_task_id);
}

function isFieldOperator(operator) {
  return (
    hasTask(operator) ||
    FIELD_ROLES.has(operator?.role) ||
    FIELD_ROLES.has(operator?.role_type)
  );
}

/**
 * 司機手機端預設身分：已有任務的人優先，避免進頁面還要在名單裡找。
 * 目前這個人已有任務就留下；否則改選 busy、再選任何有 current_task_id 的人。
 */
export function pickDriverActor(operators, currentId = "") {
  const rows = Array.isArray(operators) ? operators.filter((row) => row?.operator_id) : [];
  const withTask = rows.filter(hasTask);
  if (currentId && withTask.some((row) => row.operator_id === currentId)) {
    return currentId;
  }
  const busy = withTask.find((row) => row.status === "busy");
  return busy?.operator_id || withTask[0]?.operator_id || currentId || "";
}

const PRIVILEGED_ROLES = new Set(["dispatcher", "maintainer"]);
const DEMO_DISPATCHER_NAME = "李主任";

function isPrivileged(operator) {
  return PRIVILEGED_ROLES.has(operator?.role);
}

/**
 * 調度面板與戰情室預設身分：沒選或選到沒權限的人時，改成李主任（OP-002）。
 * 已經是調度／維運就留下，避免 Demo 中途手動切換被蓋掉。
 */
export function pickDashboardActor(operators, currentId = "") {
  const rows = Array.isArray(operators) ? operators.filter((row) => row?.operator_id) : [];
  const current = rows.find((row) => row.operator_id === currentId);
  if (current && isPrivileged(current)) return current.operator_id;
  const named = rows.find((row) => row.name === DEMO_DISPATCHER_NAME && isPrivileged(row));
  return named?.operator_id || rows.find(isPrivileged)?.operator_id || currentId || "";
}

export function fieldOperators(operators) {
  return (Array.isArray(operators) ? operators : []).filter(isFieldOperator);
}

export function driverActorOptions(operators, currentId = "") {
  const rows = fieldOperators(operators);
  if (currentId && !rows.some((row) => row.operator_id === currentId)) {
    const current = (operators || []).find((row) => row.operator_id === currentId);
    if (current) rows.unshift(current);
  }
  return rows
    .slice()
    .sort((left, right) => Number(hasTask(right)) - Number(hasTask(left)))
    .map((row) => ({
      value: row.operator_id,
      label: `${row.name || row.operator_id}${hasTask(row) ? "｜有任務" : "｜待命"}`,
    }));
}
