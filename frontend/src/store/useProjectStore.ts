/* ──────────────────────────────────────────────────────────────────────────
   Global application state via React Context + useReducer.
   Tracks which project / scene / shot / take is active, plus UI state.
   ────────────────────────────────────────────────────────────────────────── */

import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import React from "react";

// ── State shape ──────────────────────────────────────────────────────────

export interface AppState {
  currentProjectId: string | null;
  selectedSceneId: string | null;
  selectedShotId: string | null;
  selectedTakeId: string | null;
  inspectorOpen: boolean;
  queuePaused: boolean;
}

const initialState: AppState = {
  currentProjectId: null,
  selectedSceneId: null,
  selectedShotId: null,
  selectedTakeId: null,
  inspectorOpen: true,
  queuePaused: false,
};

/**
 * Below 1024px the inspector is an overlay drawer, so starting it open would
 * cover the centre panel on the first paint. AppLayout also reacts to resizes;
 * this only fixes the initial value.
 */
function createInitialState(): AppState {
  const docked =
    typeof window === "undefined" ? true : window.innerWidth >= 1024;
  return { ...initialState, inspectorOpen: docked };
}

// ── Actions ──────────────────────────────────────────────────────────────

export type AppAction =
  | { type: "SET_PROJECT"; id: string | null }
  | { type: "SELECT_SCENE"; id: string | null }
  | { type: "SELECT_SHOT"; id: string | null }
  | { type: "SELECT_TAKE"; id: string | null }
  | { type: "TOGGLE_INSPECTOR" }
  | { type: "SET_INSPECTOR"; open: boolean }
  | { type: "SET_QUEUE_PAUSED"; paused: boolean };

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_PROJECT":
      return {
        ...state,
        currentProjectId: action.id,
        selectedSceneId: null,
        selectedShotId: null,
        selectedTakeId: null,
      };
    case "SELECT_SCENE":
      return {
        ...state,
        selectedSceneId: action.id,
        selectedShotId: null,
        selectedTakeId: null,
      };
    case "SELECT_SHOT":
      return { ...state, selectedShotId: action.id, selectedTakeId: null };
    case "SELECT_TAKE":
      return { ...state, selectedTakeId: action.id };
    case "TOGGLE_INSPECTOR":
      return { ...state, inspectorOpen: !state.inspectorOpen };
    case "SET_INSPECTOR":
      return { ...state, inspectorOpen: action.open };
    case "SET_QUEUE_PAUSED":
      return { ...state, queuePaused: action.paused };
    default:
      return state;
  }
}

// ── Context ──────────────────────────────────────────────────────────────

const StateCtx = createContext<AppState>(initialState);
const DispatchCtx = createContext<Dispatch<AppAction>>(() => {});

export function ProjectStoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, createInitialState);

  return React.createElement(
    StateCtx.Provider,
    { value: state },
    React.createElement(DispatchCtx.Provider, { value: dispatch }, children),
  );
}

export function useAppState(): AppState {
  return useContext(StateCtx);
}

export function useAppDispatch(): Dispatch<AppAction> {
  return useContext(DispatchCtx);
}
