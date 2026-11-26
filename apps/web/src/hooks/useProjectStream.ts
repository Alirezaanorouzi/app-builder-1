import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectStreamUpdate } from "@/lib/project-stream-snapshot";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
/** If a run is active and no content frame arrived, fall back to JSON snapshot. */
const STALE_BUSY_MS = 12_000;
const SNAPSHOT_POLL_MS = 4_000;

type Message = { id: string; role: string; content: string };

type RunEvent = {
  seq: number;
  event_class: string;
  tool_name: string | null;
  summary: string;
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

function mergeDelta(
  prevMessages: Message[],
  prevEvents: RunEvent[],
  prevRunId: string | null,
  delta: ProjectStreamUpdate,
): { messages: Message[]; runEvents: RunEvent[]; runId: string | null } {
  const seenMsg = new Set(prevMessages.map((m) => m.id));
  const messages = [...prevMessages];
  for (const m of delta.messages ?? []) {
    if (!seenMsg.has(m.id)) messages.push(m);
  }
  const nextRunId = delta.activeRun?.id ?? null;
  const runChanged = nextRunId !== prevRunId;
  let runEvents = prevEvents;
  if (runChanged) {
    runEvents = nextRunId ? (delta.runEvents ?? []) : [];
  } else if (delta.runEvents?.length) {
    const seenSeq = new Set(prevEvents.map((e) => e.seq));
    const appended = delta.runEvents.filter((e) => !seenSeq.has(e.seq));
    if (appended.length) runEvents = [...prevEvents, ...appended];
  }
  return { messages: messages.slice(-50), runEvents, runId: nextRunId };
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
  const lastContentAtRef = useRef(Date.now());
  const messagesRef = useRef(messages);
  const eventsRef = useRef(runEvents);
  const runIdRef = useRef<string | null>(null);
  messagesRef.current = messages;
  eventsRef.current = runEvents;
  const reconnectDelayRef = useRef(RECONNECT_BASE_MS);
  const esRef = useRef<EventSource | null>(null);
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

  const noteContent = useCallback(() => {
    lastContentAtRef.current = Date.now();
    reconnectDelayRef.current = RECONNECT_BASE_MS;
  }, []);

  const applyMeta = useCallback((data: ProjectStreamUpdate) => {
    const busy =
      data.activeRun?.status === "queued" ||
      data.activeRun?.status === "running" ||
      Boolean(
        data.previewWake &&
          (data.previewWake.status === "queued" || data.previewWake.status === "running"),
      );
    busyRef.current = busy;
    setActiveStatus(data.activeRun?.status ?? null);
    if (data.previewUrl) setPreviewUrl(data.previewUrl);
    if (data.sandbox) setSandbox(data.sandbox);
    const wake = data.previewWake;
    setPreviewWaking(
      Boolean(wake && (wake.status === "queued" || wake.status === "running")),
    );
    setLiveOutput(
      data.activeRun?.status === "running" && data.liveOutput
        ? String(data.liveOutput)
        : null,
    );
  }, []);

  const applySnapshot = useCallback(
    (data: ProjectStreamUpdate) => {
      noteContent();
      runIdRef.current = data.activeRun?.id ?? null;
      applyStreamPayload(data, streamSetters);
      busyRef.current =
        data.activeRun?.status === "queued" ||
        data.activeRun?.status === "running" ||
        Boolean(
          data.previewWake &&
            (data.previewWake.status === "queued" ||
              data.previewWake.status === "running"),
        );
    },
    [noteContent],
  );

  const applyDelta = useCallback(
    (data: ProjectStreamUpdate) => {
      noteContent();
      const merged = mergeDelta(
        messagesRef.current,
        eventsRef.current,
        runIdRef.current,
        data,
      );
      runIdRef.current = merged.runId;
      setMessages(merged.messages);
      setRunEvents(merged.runEvents);
      applyMeta(data);
    },
    [noteContent, applyMeta],
  );

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch(`/api/projects/${projectId}/snapshot`);
      if (!res.ok) return;
      const data = (await res.json()) as ProjectStreamUpdate;
      applySnapshot(data);
    } catch {
      /* ignore */
    }
  }, [projectId, applySnapshot]);

  useEffect(() => {
    unmountedRef.current = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const closeEs = () => {
      const es = esRef.current;
      esRef.current = null;
      if (es) {
        es.onerror = null;
        es.close();
      }
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
      es.addEventListener("snapshot", (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as ProjectStreamUpdate;
        applySnapshot(data);
      });
      es.addEventListener("delta", (ev) => {
        const data = JSON.parse((ev as MessageEvent).data) as ProjectStreamUpdate;
        applyDelta(data);
      });
      es.onerror = () => {
        scheduleReconnect();
      };
    };

    openStream();

    const staleTimer = setInterval(() => {
      if (!busyRef.current) return;
      if (Date.now() - lastContentAtRef.current < STALE_BUSY_MS) return;
      void fetchSnapshot();
    }, SNAPSHOT_POLL_MS);

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(staleTimer);
      closeEs();
    };
  }, [projectId, applySnapshot, applyDelta, fetchSnapshot]);

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
