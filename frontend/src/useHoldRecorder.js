import { useCallback, useEffect, useRef, useState } from "react";
import {
  MAX_DURATION_SEC,
  MAX_FILE_BYTES,
  MIN_DURATION_SEC,
  pickSupportedMimeType,
} from "./recording.js";

function stopTracks(stream) {
  if (!stream) {
    return;
  }
  stream.getTracks().forEach((track) => track.stop());
}

function messageForGetUserMediaError(error) {
  if (error?.name === "NotAllowedError" || error?.name === "PermissionDeniedError") {
    return "无法使用麦克风，请在浏览器中允许麦克风权限后重试。";
  }
  if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
    return "未找到可用的麦克风设备。";
  }
  return "录制失败，请重试。";
}

export function useHoldRecorder() {
  const mimeType = pickSupportedMimeType();
  const supported = Boolean(mimeType);

  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState(
    supported ? null : "当前浏览器不支持 WebM/Opus 录音，请更换 Chrome、Edge 或 Firefox。",
  );
  const [result, setResult] = useState(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  const pressedRef = useRef(false);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const startedAtRef = useRef(0);
  const stopReasonRef = useRef("release");
  const maxTimerRef = useRef(0);
  const tickTimerRef = useRef(0);
  const resultUrlRef = useRef(null);
  const stoppingRef = useRef(false);
  const closedRef = useRef(true);

  const clearTimers = useCallback(() => {
    window.clearTimeout(maxTimerRef.current);
    window.clearInterval(tickTimerRef.current);
    maxTimerRef.current = 0;
    tickTimerRef.current = 0;
  }, []);

  const releaseMicrophone = useCallback(() => {
    stopTracks(streamRef.current);
    streamRef.current = null;
  }, []);

  const replaceResult = useCallback((next) => {
    if (resultUrlRef.current) {
      URL.revokeObjectURL(resultUrlRef.current);
      resultUrlRef.current = null;
    }
    if (next?.blob) {
      const url = URL.createObjectURL(next.blob);
      resultUrlRef.current = url;
      setResult({ ...next, url });
      return;
    }
    setResult(null);
  }, []);

  const finishRecording = useCallback(
    (reason) => {
      if (closedRef.current) {
        return;
      }
      closedRef.current = true;

      const elapsedMs = Math.max(0, performance.now() - startedAtRef.current);
      const durationSec = Math.min(elapsedMs / 1000, MAX_DURATION_SEC);
      const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });

      recorderRef.current = null;
      chunksRef.current = [];
      stoppingRef.current = false;
      pressedRef.current = false;
      releaseMicrophone();
      clearTimers();
      setElapsedSec(durationSec);
      setPhase("idle");

      if (reason === "cancel") {
        replaceResult(null);
        setError("已取消录音。");
        return;
      }

      if (reason === "error") {
        replaceResult(null);
        setError("录制失败，请重试。");
        return;
      }

      if (blob.size === 0) {
        replaceResult(null);
        setError("录制失败，没有得到有效音频，请重试。");
        return;
      }

      if (durationSec < MIN_DURATION_SEC) {
        replaceResult(null);
        setError("录音时长需在 1 到 60 秒之间。");
        return;
      }

      if (blob.size > MAX_FILE_BYTES) {
        replaceResult(null);
        setError("录音文件超过 5MB，请缩短录音后重试。");
        return;
      }

      setError(null);
      replaceResult({
        blob,
        mimeType: blob.type || mimeType,
        durationSec,
        sizeBytes: blob.size,
      });
    },
    [clearTimers, mimeType, releaseMicrophone, replaceResult],
  );

  const stopRecording = useCallback(
    (reason) => {
      pressedRef.current = false;
      if (!recorderRef.current) {
        if (streamRef.current) {
          releaseMicrophone();
          setPhase("idle");
        }
        return;
      }
      if (stoppingRef.current) {
        return;
      }
      stoppingRef.current = true;
      stopReasonRef.current = reason;
      clearTimers();
      setPhase("stopping");
      const recorder = recorderRef.current;
      if (recorder.state === "inactive") {
        finishRecording(reason);
        return;
      }
      recorder.stop();
    },
    [clearTimers, finishRecording, releaseMicrophone],
  );

  const startRecording = useCallback(
    async (event) => {
      if (!supported) {
        setError("当前浏览器不支持 WebM/Opus 录音，请更换 Chrome、Edge 或 Firefox。");
        return;
      }
      if (event.pointerType === "mouse" && event.button !== 0) {
        return;
      }
      if (phase === "recording" || phase === "requesting" || phase === "stopping") {
        return;
      }

      event.preventDefault();
      pressedRef.current = true;
      stoppingRef.current = false;
      closedRef.current = false;
      setError(null);
      setPhase("requesting");
      setElapsedSec(0);

      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (mediaError) {
        pressedRef.current = false;
        closedRef.current = true;
        setPhase("idle");
        setError(messageForGetUserMediaError(mediaError));
        return;
      }

      if (!pressedRef.current) {
        stopTracks(stream);
        closedRef.current = true;
        setPhase("idle");
        setError("没有保持按住。若刚允许麦克风，请再次按住按钮录音。");
        return;
      }

      streamRef.current = stream;
      chunksRef.current = [];

      let recorder;
      try {
        recorder = new MediaRecorder(stream, { mimeType });
      } catch {
        stopTracks(stream);
        streamRef.current = null;
        pressedRef.current = false;
        closedRef.current = true;
        setPhase("idle");
        setError("录制失败，请重试。");
        return;
      }

      recorderRef.current = recorder;
      recorder.ondataavailable = (chunkEvent) => {
        if (chunkEvent.data && chunkEvent.data.size > 0) {
          chunksRef.current.push(chunkEvent.data);
        }
      };
      recorder.onerror = () => {
        stopRecording("error");
      };
      recorder.onstop = () => {
        finishRecording(stopReasonRef.current);
      };

      try {
        recorder.start();
      } catch {
        stopTracks(stream);
        streamRef.current = null;
        recorderRef.current = null;
        pressedRef.current = false;
        closedRef.current = true;
        setPhase("idle");
        setError("录制失败，请重试。");
        return;
      }

      startedAtRef.current = performance.now();
      setPhase("recording");
      tickTimerRef.current = window.setInterval(() => {
        const seconds = (performance.now() - startedAtRef.current) / 1000;
        setElapsedSec(Math.min(seconds, MAX_DURATION_SEC));
      }, 200);
      maxTimerRef.current = window.setTimeout(() => {
        stopRecording("limit");
      }, MAX_DURATION_SEC * 1000);
    },
    [finishRecording, mimeType, phase, stopRecording, supported],
  );

  useEffect(() => {
    const onPointerEnd = (event) => {
      if (!pressedRef.current && phase !== "recording" && phase !== "requesting") {
        return;
      }
      if (event.pointerType === "mouse" && event.button !== 0) {
        return;
      }
      stopRecording("release");
    };

    const onPointerCancel = () => {
      if (pressedRef.current || phase === "recording" || phase === "requesting") {
        stopRecording("cancel");
      }
    };

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        stopRecording("cancel");
      }
    };

    const onHidden = () => {
      if (document.hidden) {
        stopRecording("release");
      }
    };

    window.addEventListener("pointerup", onPointerEnd);
    window.addEventListener("pointercancel", onPointerCancel);
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("visibilitychange", onHidden);

    return () => {
      window.removeEventListener("pointerup", onPointerEnd);
      window.removeEventListener("pointercancel", onPointerCancel);
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("visibilitychange", onHidden);
    };
  }, [phase, stopRecording]);

  useEffect(() => {
    return () => {
      clearTimers();
      releaseMicrophone();
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      }
      if (resultUrlRef.current) {
        URL.revokeObjectURL(resultUrlRef.current);
      }
    };
  }, [clearTimers, releaseMicrophone]);

  const buttonProps = {
    type: "button",
    disabled: !supported || phase === "stopping",
    onPointerDown: startRecording,
    onContextMenu: (event) => event.preventDefault(),
    "aria-pressed": phase === "recording",
  };

  return {
    supported,
    mimeType,
    phase,
    error,
    result,
    elapsedSec,
    buttonProps,
  };
}
