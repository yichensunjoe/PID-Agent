/// <reference types="vite/client" />

import type { E2EBridge } from "./e2eBridge";

declare global {
  interface Window {
    __PID_AGENT_E2E__?: E2EBridge;
  }
}

export {};
