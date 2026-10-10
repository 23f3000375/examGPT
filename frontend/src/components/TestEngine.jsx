import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Loader2,
  Send,
  RotateCcw,
  AlertTriangle,
  Clock,
  Sparkles,
  BookOpen,
  Lightbulb,
  ChevronRight,
  ArrowRight,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const USER_ID = 1;

function TestEngine({ testConfig, onBack }) {
  const { topic, subTopic, difficulty, studyText } = testConfig || {};

  // ── State ────────────────────────────────────────────────
  const [questions, setQuestions] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [score, setScore] = useState(0);

  const [selectedOption, setSelectedOption] = useState(null);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [gradingResult, setGradingResult] = useState(null);
  
  const [loading, setLoading] = useState(true);
  const [progressState, setProgressState] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [fallbackText, setFallbackText] = useState("");

  const startTimeRef = useRef(null);

  const startGeneration = useCallback(async (isCancelled = () => false, text = studyText) => {
    setLoading(true);
    setError(null);
    setProgressState(null);

    try {
      const response = await fetch(`${API_BASE}/api/generate-question-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic,
          sub_topic: subTopic,
          difficulty: difficulty,
          study_text: text,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to connect to generation stream.");
      }
      if (!response.body) {
        throw new Error("The generation stream returned no response body.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!isCancelled()) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); 

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            let event;
            try {
              event = JSON.parse(line.slice(6));
            } catch {
              continue;
            }
            if (event.detail) {
              throw new Error(event.detail);
            }
            if (event.status === "generating" || event.status === "progress") {
              setProgressState({
                chunk: event.chunk,
                total_chunks: event.total_chunks,
                provider: event.provider,
              });
            } else if (event.status === "complete") {
              setQuestions(event.batch);
              setCurrentIndex(0);
              setScore(0);
              startTimeRef.current = Date.now();
            }
          }
        }
      }
    } catch (err) {
      if (!isCancelled()) {
        console.error("Failed to generate batch:", err);
        setError(err.message || "Failed to generate questions.");
      }
    } finally {
      if (!isCancelled()) setLoading(false);
    }
  }, [difficulty, studyText, subTopic, topic]);

  // ── Generate batch on mount ─────────────────────────────
  useEffect(() => {
    if (!topic || !subTopic) return undefined;
    let cancelled = false;
    const timer = window.setTimeout(() => startGeneration(() => cancelled), 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [startGeneration, topic, subTopic]);

  if (!topic || !subTopic) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center space-y-6">
        <div className="p-4 bg-red-500/10 rounded-full border border-red-500/20">
          <AlertTriangle className="h-10 w-10 text-red-400" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Missing Parameters</h2>
          <p className="text-gray-400 max-w-md mx-auto">
            We couldn't find your test configuration. Please return to the Dashboard and explicitly choose a topic to study.
          </p>
        </div>
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 rounded-xl bg-gray-800 px-6 py-3 text-sm font-semibold text-white transition hover:bg-gray-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </button>
      </div>
    );
  }

  // ── Submit answer ────────────────────────────────────────
  const handleSubmit = async () => {
    const currentQuestion = questions[currentIndex];
    if (!selectedOption || !currentQuestion) return;

    setSubmitting(true);
    setError(null);

    const timeTaken = startTimeRef.current
      ? parseFloat(((Date.now() - startTimeRef.current) / 1000).toFixed(1))
      : 0;

    try {
      const { data } = await axios.post(`${API_BASE}/api/submit-answer`, {
        user_id: USER_ID,
        question_id: currentQuestion.id,
        chosen_option: selectedOption,
        time_taken_seconds: timeTaken,
      });

      setGradingResult({ ...data, time_taken: timeTaken });
      setIsSubmitted(true);
      if (data.is_correct) {
        setScore((s) => s + 1);
      }
    } catch (err) {
      console.error("Failed to submit answer:", err);
      setError(
        err.response?.data?.detail || "Could not submit your answer."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex((i) => i + 1);
      setSelectedOption(null);
      setIsSubmitted(false);
      setGradingResult(null);
      startTimeRef.current = Date.now();
    } else {
      // Test is finished
      onBack();
    }
  };

  const difficultyColor = {
    easy: "text-emerald-400 bg-emerald-500/15",
    medium: "text-amber-400 bg-amber-500/15",
    hard: "text-red-400 bg-red-500/15",
  }[difficulty] || "text-gray-400 bg-gray-500/15";

  const getOptionStyle = (key) => {
    const base =
      "group relative flex w-full cursor-pointer items-start gap-4 rounded-xl border p-5 text-left transition-all duration-200";

    if (isSubmitted && gradingResult) {
      const isCorrect = key === gradingResult.correct_answer;
      const isChosen = key === selectedOption;

      if (isCorrect) {
        return `${base} border-emerald-500/50 bg-emerald-500/10 ring-1 ring-emerald-500/30`;
      }
      if (isChosen && !isCorrect) {
        return `${base} border-red-500/50 bg-red-500/10 ring-1 ring-red-500/30`;
      }
      return `${base} border-gray-800 bg-gray-900/40 opacity-40 cursor-default`;
    }

    if (key === selectedOption) {
      return `${base} border-violet-500 bg-violet-500/10 ring-2 ring-violet-500/40 shadow-lg shadow-violet-500/5`;
    }
    return `${base} border-gray-800 bg-gray-900/60 hover:border-gray-600 hover:bg-slate-800 hover:shadow-md`;
  };

  const getOptionIcon = (key) => {
    if (!isSubmitted || !gradingResult) return null;
    if (key === gradingResult.correct_answer) {
      return <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />;
    }
    if (key === selectedOption && key !== gradingResult.correct_answer) {
      return <XCircle className="h-5 w-5 shrink-0 text-red-400" />;
    }
    return null;
  };

  const getOptionBadge = (key) => {
    if (isSubmitted && gradingResult) {
      if (key === gradingResult.correct_answer)
        return "bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30";
      if (key === selectedOption)
        return "bg-red-500/20 text-red-400 ring-1 ring-red-500/30";
      return "bg-gray-800 text-gray-500";
    }
    if (key === selectedOption)
      return "bg-violet-500/20 text-violet-400 ring-1 ring-violet-500/30";
    return "bg-gray-800 text-gray-400 group-hover:bg-gray-700 group-hover:text-gray-300";
  };

  const currentQuestion = questions[currentIndex];
  const isLastQuestion = currentIndex === questions.length - 1;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* ── Header + Breadcrumb ──────────────────────────── */}
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <button
              onClick={onBack}
              className="rounded-lg border border-gray-800 p-2 text-gray-400 transition hover:bg-gray-800 hover:text-white"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <h1 className="text-3xl font-bold tracking-tight text-white">
              Test Engine
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 pl-14">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-500/15 px-3 py-1 text-xs font-medium text-violet-400">
              <BookOpen className="h-3 w-3" />
              {topic}
            </span>
            <ChevronRight className="h-3 w-3 text-gray-600" />
            <span className="inline-flex items-center rounded-full bg-gray-800 px-3 py-1 text-xs font-medium text-gray-300">
              {subTopic}
            </span>
            <ChevronRight className="h-3 w-3 text-gray-600" />
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${difficultyColor}`}>
              {difficulty[0].toUpperCase() + difficulty.slice(1)}
            </span>
          </div>
        </div>
        
        {/* Score tracker */}
        {!loading && questions.length > 0 && (
          <div className="text-right">
            <p className="text-sm font-medium text-gray-400">Score</p>
            <p className="text-2xl font-bold text-white tracking-tight">
              {score} <span className="text-gray-600 text-lg">/ {questions.length}</span>
            </p>
          </div>
        )}
      </div>

      {error && !loading && questions.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-red-500/20 bg-red-500/5 py-12 px-6 space-y-6 max-w-3xl mx-auto">
          <div className="p-4 bg-red-500/10 rounded-full border border-red-500/20">
            <AlertTriangle className="h-10 w-10 text-red-400" />
          </div>
          <div className="text-center w-full">
            <h2 className="text-xl font-bold text-white mb-2">Generation Failed</h2>
            <p className="text-gray-400 text-sm leading-relaxed mb-6">
              Gemini and Groq could not generate this test. Paste 80 to 20,000 characters
              of study material and we will create questions locally, using web search
              when available. No LLM provider is required for this fallback.
            </p>
            <textarea
              value={fallbackText}
              onChange={(e) => setFallbackText(e.target.value)}
              rows={6}
              maxLength={20000}
              placeholder="Paste notes, textbook extract, or source material here..."
              className="w-full resize-y rounded-xl border border-gray-700 bg-gray-800/80 px-5 py-3.5 text-sm leading-relaxed text-white placeholder:text-gray-500 transition-all hover:border-gray-500 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/40"
            />
            <p className="mt-2 text-xs text-gray-500 text-left">{fallbackText.trim().length}/20,000 characters. Minimum 80 characters.</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-700 bg-gray-800 px-5 py-3 text-sm font-semibold text-gray-300 transition hover:bg-gray-700 hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" />
              Change Topic
            </button>
            <button
              onClick={() => startGeneration(() => false, fallbackText.trim())}
              disabled={fallbackText.trim().length < 80 || fallbackText.trim().length > 20000}
              className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-600/25 transition hover:bg-violet-500 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw className="h-4 w-4" />
              Generate with Text + Web Search
            </button>
          </div>
        </div>
      ) : error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-300">
          <AlertTriangle className="h-5 w-5 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading Spinner */}
      {loading && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-gray-800 bg-gray-900/40 py-24">
          <div className="relative">
            <Loader2 className="h-12 w-12 animate-spin text-violet-400" />
            <Sparkles className="absolute -right-1 -top-1 h-5 w-5 animate-pulse text-amber-400" />
          </div>
          <p className="mt-6 text-lg font-medium text-gray-300">
            {progressState 
              ? `Generating chunk ${progressState.chunk} of ${progressState.total_chunks}...` 
              : "Connecting to AI Factory..."}
          </p>
          <p className="mt-2 text-sm text-gray-500 text-center max-w-md">
            {progressState?.provider ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-violet-500/10 text-violet-400 rounded-full border border-violet-500/20 text-xs font-semibold">
                via {progressState.provider.toUpperCase()}
              </span>
            ) : "This takes a moment as our AI generates distinct, high-quality questions for you."}
          </p>
        </div>
      )}

      {/* Question Card */}
      {!loading && currentQuestion && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-white">
              Question {currentIndex + 1} <span className="text-gray-500">of {questions.length}</span>
            </h2>
          </div>

          <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-8 shadow-lg">
            <p className="text-xl font-medium leading-relaxed tracking-wide text-white">
              {currentQuestion.question}
            </p>
          </div>

          {/* Options */}
          <div className="grid gap-3">
            {currentQuestion.options.map(({ id: key, text }) => (
              <button
                key={key}
                onClick={() => {
                  if (!isSubmitted) setSelectedOption(key);
                }}
                disabled={isSubmitted}
                className={getOptionStyle(key)}
              >
                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold transition-colors ${getOptionBadge(key)}`}>
                  {key}
                </span>
                <span className="flex-1 pt-1 text-[15px] leading-relaxed text-gray-200">
                  {text}
                </span>
                {getOptionIcon(key)}
              </button>
            ))}
          </div>

          {/* Controls */}
          {!isSubmitted ? (
            <div className="flex items-center justify-end gap-3 pt-4">
              <button
                onClick={handleSubmit}
                disabled={!selectedOption || submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-violet-600/25 transition hover:bg-violet-500 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Send className="h-5 w-5" />
                )}
                Submit Answer
              </button>
            </div>
          ) : (
            <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-300">
              <div className={`flex items-start gap-4 rounded-xl border p-6 ${
                  gradingResult?.is_correct
                    ? "border-emerald-500/30 bg-emerald-500/10"
                    : "border-red-500/30 bg-red-500/10"
                }`}
              >
                {gradingResult?.is_correct ? (
                  <CheckCircle2 className="h-7 w-7 shrink-0 text-emerald-400" />
                ) : (
                  <XCircle className="h-7 w-7 shrink-0 text-red-400" />
                )}
                <div>
                  <p className={`text-lg font-semibold ${
                      gradingResult?.is_correct ? "text-emerald-300" : "text-red-300"
                    }`}
                  >
                    {gradingResult?.is_correct
                      ? "Correct! Well done."
                      : `Incorrect — the correct answer is ${gradingResult?.correct_answer}.`}
                  </p>
                  {gradingResult?.time_taken != null && (
                    <p className="mt-1 flex items-center gap-1.5 text-sm text-gray-400">
                      <Clock className="h-4 w-4" />
                      Answered in {gradingResult.time_taken}s
                    </p>
                  )}
                </div>
              </div>

              {gradingResult?.explanation && (
                <div className="rounded-xl border-l-4 border-blue-500 bg-blue-900/20 p-6">
                  <h3 className="mb-3 flex items-center gap-2 text-base font-semibold text-blue-300">
                    <Lightbulb className="h-5 w-5" />
                    Explanation
                  </h3>
                  <p className="text-[15px] leading-relaxed text-gray-300 whitespace-pre-line">
                    {gradingResult.explanation}
                  </p>
                  {currentQuestion.source_reference && (
                    <p className="mt-4 border-t border-blue-400/20 pt-4 text-sm italic leading-relaxed text-blue-200/80 flex flex-col gap-1">
                      {currentQuestion.source_reference.startsWith("Web search:") ||
                      currentQuestion.source_reference.startsWith("Web:") ? (
                        <>
                          <span className="flex items-center gap-1.5 font-semibold text-blue-300">
                            <BookOpen className="h-4 w-4" /> Sourced from Web
                          </span>
                          <a
                            href={currentQuestion.source_reference.replace(/^Web(?: search)?:\s*/, "")}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline hover:text-blue-100"
                          >
                            {currentQuestion.source_reference.replace(/^Web(?: search)?:\s*/, "")}
                          </a>
                        </>
                      ) : (
                        <span>Source: “{currentQuestion.source_reference}”</span>
                      )}
                    </p>
                  )}
                </div>
              )}

              <div className="flex items-center justify-end pt-4 border-t border-gray-800">
                <button
                  onClick={handleNext}
                  className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-8 py-4 text-base font-semibold text-white shadow-lg shadow-violet-600/25 transition hover:bg-violet-500 hover:scale-105 active:scale-[0.98]"
                >
                  {isLastQuestion ? "Finish Test" : "Next Question"}
                  {isLastQuestion ? <CheckCircle2 className="h-5 w-5" /> : <ArrowRight className="h-5 w-5" />}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TestEngine;
