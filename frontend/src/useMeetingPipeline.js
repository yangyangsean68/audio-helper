import { useCallback, useEffect, useRef, useState } from "react";
import {
  extractMeeting,
  fetchAudioFile,
  finalizeSearch,
  formatErrorText,
  getHealth,
  normalizeRequestError,
  recognizeAudio,
  searchPlaces,
  uploadRecording,
} from "./api.js";

function emptyRound() {
  return {
    audioId: null,
    transcript: null,
    extract: null,
    searchId: null,
    midpoint: null,
    pois: [],
    replyText: null,
    audioUrl: null,
    warning: null,
  };
}

function stopAudioElement(audio) {
  if (!audio) {
    return;
  }
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}

export function useMeetingPipeline() {
  const [healthStatus, setHealthStatus] = useState(null);
  const [stage, setStage] = useState("idle");
  const [inFlight, setInFlight] = useState(false);
  const [error, setError] = useState(null);
  const [round, setRound] = useState(emptyRound);
  const [needsManualPlay, setNeedsManualPlay] = useState(false);
  const [audioLoadError, setAudioLoadError] = useState(null);

  const seqRef = useRef(0);
  const abortRef = useRef(null);
  const stageRef = useRef("idle");
  const inFlightRef = useRef(false);
  const audioRef = useRef(null);
  const objectUrlRef = useRef(null);

  const setPipelineStage = useCallback((next) => {
    stageRef.current = next;
    setStage(next);
  }, []);

  const stopPlayback = useCallback(() => {
    stopAudioElement(audioRef.current);
    audioRef.current = null;
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setNeedsManualPlay(false);
  }, []);

  const beginRound = useCallback(() => {
    seqRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    stopPlayback();
    setRound(emptyRound());
    setError(null);
    setAudioLoadError(null);
    setNeedsManualPlay(false);
    return { seq: seqRef.current, signal: abortRef.current.signal };
  }, [stopPlayback]);

  const stillCurrent = useCallback((seq, signal) => {
    return seq === seqRef.current && !signal.aborted;
  }, []);

  const playAudioBlob = useCallback(async (blob) => {
    stopPlayback();
    const objectUrl = URL.createObjectURL(blob);
    objectUrlRef.current = objectUrl;
    const audio = new Audio(objectUrl);
    audioRef.current = audio;
    try {
      await audio.play();
      setNeedsManualPlay(false);
    } catch (playError) {
      if (playError?.name === "NotAllowedError") {
        setNeedsManualPlay(true);
        return;
      }
      setAudioLoadError("音频加载失败，文字结果已保留。");
    }
  }, [stopPlayback]);

  const playManually = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    try {
      await audio.play();
      setNeedsManualPlay(false);
      setAudioLoadError(null);
    } catch {
      setAudioLoadError("音频播放失败，文字结果已保留。");
    }
  }, []);

  const runPipeline = useCallback(
    async (recording, city) => {
      if (inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      const { blob, mimeType } = recording;
      const { seq, signal } = beginRound();
      const requestConfig = { signal };
      setInFlight(true);
      setPipelineStage("health");

      try {
        const health = await getHealth(requestConfig);
        if (!stillCurrent(seq, signal)) {
          return;
        }
        setHealthStatus(health.data.status);
        if (health.data.status !== "ok") {
          throw Object.assign(new Error("后端服务不可用。"), {
            response: {
              data: {
                error: {
                  code: "SERVICE_UNAVAILABLE",
                  message: "后端服务不可用。",
                  stage: "health",
                },
              },
            },
          });
        }

        setPipelineStage("upload");
        const uploaded = await uploadRecording(blob, mimeType, requestConfig);
        if (!stillCurrent(seq, signal)) {
          return;
        }
        setRound((current) => ({ ...current, audioId: uploaded.data.audio_id }));

        setPipelineStage("asr");
        const asr = await recognizeAudio(uploaded.data.audio_id, requestConfig);
        if (!stillCurrent(seq, signal)) {
          return;
        }
        setRound((current) => ({ ...current, transcript: asr.data.text }));

        setPipelineStage("extract");
        const cityValue = city.trim() || "杭州";
        const extracted = await extractMeeting(asr.data.text, cityValue, requestConfig);
        if (!stillCurrent(seq, signal)) {
          return;
        }
        setRound((current) => ({ ...current, extract: extracted.data }));

        setPipelineStage("search");
        const searched = await searchPlaces(extracted.data, requestConfig);
        if (!stillCurrent(seq, signal)) {
          return;
        }
        setRound((current) => ({
          ...current,
          searchId: searched.data.search_id,
          midpoint: searched.data.midpoint,
          pois: (searched.data.pois || []).slice(0, 3),
        }));

        setPipelineStage("finalize");
        const finalized = await finalizeSearch(searched.data.search_id, requestConfig);
        if (!stillCurrent(seq, signal)) {
          return;
        }
        setRound((current) => ({
          ...current,
          replyText: finalized.data.reply_text,
          audioUrl: finalized.data.audio_url,
          warning: finalized.data.warning,
        }));

        if (finalized.data.audio_url) {
          setPipelineStage("audio");
          try {
            const audioBlob = await fetchAudioFile(finalized.data.audio_url, requestConfig);
            if (!stillCurrent(seq, signal)) {
              return;
            }
            await playAudioBlob(audioBlob);
          } catch (audioError) {
            if (!stillCurrent(seq, signal)) {
              return;
            }
            const normalized = await normalizeRequestError(audioError, "audio");
            if (normalized.canceled) {
              return;
            }
            setAudioLoadError(
              normalized.kind === "business"
                ? `${normalized.message} 文字结果已保留。`
                : "音频加载失败，文字结果已保留。",
            );
          }
        }

        if (stillCurrent(seq, signal)) {
          setPipelineStage("done");
        }
      } catch (requestError) {
        if (!stillCurrent(seq, signal)) {
          return;
        }
        const normalized = await normalizeRequestError(requestError, stageRef.current);
        if (normalized.canceled) {
          return;
        }
        if (
          normalized.stage === "health" &&
          (normalized.kind === "network" || normalized.kind === "timeout")
        ) {
          setHealthStatus("offline");
        }
        setError(normalized);
        setPipelineStage("error");
      } finally {
        if (seq === seqRef.current) {
          inFlightRef.current = false;
          setInFlight(false);
        }
      }
    },
    [beginRound, playAudioBlob, setPipelineStage, stillCurrent],
  );

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((health) => {
        if (!cancelled) {
          setHealthStatus(health.data.status);
        }
      })
      .catch(async (requestError) => {
        if (cancelled) {
          return;
        }
        const normalized = await normalizeRequestError(requestError, "health");
        if (!normalized.canceled) {
          setHealthStatus("offline");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      seqRef.current += 1;
      abortRef.current?.abort();
      stopAudioElement(audioRef.current);
      audioRef.current = null;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, []);

  return {
    healthStatus,
    stage,
    inFlight,
    error,
    errorText: error ? formatErrorText(error) : null,
    round,
    needsManualPlay,
    audioLoadError,
    runPipeline,
    playManually,
  };
}
