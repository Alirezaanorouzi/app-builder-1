import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectStreamUpdate } from "@/lib/project-stream-snapshot";

/** Rotate SSE before typical Liara / reverse-proxy ~300s HTTP limits. */
const STREAM_ROTATE_MS = 240_000;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
/** If a run is active and no event arrived, fall back to JSON snapshot. */
const STALE_BUSY_MS = 35_000;
const SNAPSHOT_POLL_MS = 4_000;

type Message = { id: string; role: string; content: string };

type RunEvent = {
  seq: number;
  event_class: string;
  tool_name: string | null;
  summary: string;
  payload?: Record<string, unknown>;
};

type SandboxInfo = {
  preview_url: string | null;
  provider: string | null;
  external_id: string | null;
  status: string | null;
  name: string | null;
  agent_server_status?: string | null;
  session_expires_at?: string | null;
} | null;

function applyStreamPayload(
  data: ProjectStreamUpdate,
  setters: {
    setMessages: (v: Message[]) => void;
    setActiveStatus: (v: string | null) => void;
    setRunEvents: (v: RunEvent[]) => void;
    setPreviewUrl: (v: string | null) => void;
    setSandbox: (v: SandboxInfo) => void;
    setPreviewWaking: (v: boolean) => void;
    setLiveOutput: (v: string | null) => void;
  },
) {
  setters.setMessages(data.messages ?? []);
  setters.setActiveStatus(data.activeRun?.status ?? null);
  setters.setRunEvents(data.runEvents ?? []);
  if (data.previewUrl) setters.setPreviewUrl(data.previewUrl);
  if (data.sandbox) setters.setSandbox(data.sandbox);
  const wake = data.previewWake;
  setters.setPreviewWaking(
    Boolean(wake && (wake.status === "queued" || wake.status === "running")),
  );
  setters.setLiveOutput(
    data.activeRun?.status === "running" && data.liveOutput
      ? String(data.liveOutput)
      : null,
  );
}

export function useProjectStream(projectId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [sandbox, setSandbox] = useState<SandboxInfo>(null);
  const [activeStatus, setActiveStatus] = useState<string | null>(null);
  const [previewWaking, setPreviewWaking] = useState(false);
  const [liveOutput, setLiveOutput] = useState<string | null>(null);

  const busyRef = useRef(false);
  const lastEventAtRef = useRef(Date.now());
  const reconnectDelayRef = useRef(RECONNECT_BASE_MS);
  const esRef = useRef<EventSource | null>(null);
  const rotateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const staleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const unmountedRef = useRef(false);

  const streamSetters = {
    setMessages,
    setActiveStatus,
    setRunEvents,
    setPreviewUrl,
    setSandbox,
    setPreviewWaking,
    setLiveOutput,
  };

  const touchStream = useCallback(() => {
    lastEventAtRef.current = Date.now();
    reconnectDelayRef.current = RECONNECT_BASE_MS;
  }, []);

  const applyUpdate = useCallback(
    (data: ProjectStreamUpdate) => {
      touchStream();
      const busy =
        data.activeRun?.status === "queued" ||
        data.activeRun?.status === "running" ||
        Boolean(
          data.previewWake &&
            (data.previewWake.status === "queued" ||
              data.previewWake.status === "running"),
        );
      busyRef.current = busy;
      applyStreamPayload(data, streamSetters);
    },
  // stream setters are stable useState dispatchers
  // eslint-disable-next-line react-hooks/exhaustive-deps
    [touchStream],
  );

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch(`/api/projects/${projectId}/snapshot`);
      if (!res.ok) return;
      const data = (await res.json()) as ProjectStreamUpdate;
      applyUpdate(data);
    } catch {
      /* ignore */
    }
  }, [projectId, applyUpdate]);

  useEffect(() => {
    unmountedRef.current = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const clearRotate = () => {
      if (rotateTimerRef.current) {
        clearTimeout(rotateTimerRef.current);
        rotateTimerRef.current = null;
      }
    };

    const closeEs = () => {
      clearRotate();
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };

    const scheduleRotate = () => {
      clearRotate();
      rotateTimerRef.current = setTimeout(() => {
        if (unmountedRef.current) return;
        closeEs();
        openStream();
      }, STREAM_ROTATE_MS);
    };

    const scheduleReconnect = () => {
      if (unmountedRef.current) return;
      closeEs();
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, RECONNECT_MAX_MS);
      reconnectTimer = setTimeout(() => {
        if (!unmountedRef.current) openStream();
      }, delay);
    };

    const openStream = () => {
      if (unmountedRef.current) return;
      closeEs();
      const es = new EventSource(`/api/projects/${projectId}/stream`);
      esRef.current = es;
      es.addEventListener("update", (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as ProjectStreamUpdate;
        applyUpdate(data);
      });
      es.addEventListener("ping", () => {
        touchStream();
      });
      es.onopen = () => {
        touchStream();
        scheduleRotate();
      };
      es.onerror = () => {
        scheduleReconnect();
      };
    };

    openStream();

    staleTimerRef.current = setInterval(() => {
      if (!busyRef.current) return;
      if (Date.now() - lastEventAtRef.current < STALE_BUSY_MS) return;
      void fetchSnapshot();
    }, SNAPSHOT_POLL_MS);

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (staleTimerRef.current) clearInterval(staleTimerRef.current);
      closeEs();
    };
  }, [projectId, applyUpdate, touchStream, fetchSnapshot]);

  return {
    messages,
    setMessages,
    runEvents,
    previewUrl,
    sandbox,
    activeStatus,
    setActiveStatus,
    previewWaking,
    liveOutput,
    setPreviewUrl,
    setSandbox,
  };
}