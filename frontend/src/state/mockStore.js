import mockData from "../mock/mock_data.json";

const clone = (value) => structuredClone(value);
const initialState = clone(mockData);
let state = clone(initialState);

export function readMockState() {
  return clone(state);
}

export function mutateMockState(mutator) {
  const draft = clone(state);
  mutator(draft);
  state = draft;
  return clone(state);
}

export function resetMockState() {
  state = clone(initialState);
  return readMockState();
}
