import { useState } from "react";
import { BrainCircuit, FlaskConical, LayoutDashboard } from "lucide-react";
import Dashboard from "./components/Dashboard";
import TestEngine from "./components/TestEngine";

function App() {
  const [view, setView] = useState("dashboard");
  const [testConfig, setTestConfig] = useState(null);

  const handleStartTest = (config) => {
    // config = { topic, subTopic, difficulty }
    setTestConfig(config);
    setView("test");
  };

  const handleBackToDashboard = () => {
    setTestConfig(null);
    setView("dashboard");
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Navbar ─────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          {/* Logo */}
          <button
            onClick={handleBackToDashboard}
            className="flex items-center gap-2 text-xl font-bold tracking-tight text-white transition hover:opacity-80"
          >
            <BrainCircuit className="h-7 w-7 text-violet-400" />
            <span>
              Exam<span className="text-violet-400">GPT</span>
            </span>
          </button>

          {/* Nav Links */}
          <div className="flex items-center gap-1">
            <button
              onClick={handleBackToDashboard}
              className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition ${
                view === "dashboard"
                  ? "bg-violet-500/15 text-violet-400"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              Dashboard
            </button>
            <button
              onClick={() => setView("test")}
              className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition ${
                view === "test"
                  ? "bg-violet-500/15 text-violet-400"
                  : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
              }`}
            >
              <FlaskConical className="h-4 w-4" />
              Test Engine
            </button>
          </div>
        </div>
      </nav>

      {/* ── Main Content ──────────────────────────────────── */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        {view === "dashboard" ? (
          <Dashboard onStartTest={handleStartTest} />
        ) : (
          <TestEngine
            testConfig={testConfig}
            onBack={handleBackToDashboard}
          />
        )}
      </main>

      {/* ── Footer ────────────────────────────────────────── */}
      <footer className="border-t border-gray-800 py-4 text-center text-xs text-gray-600">
        ExamGPT &mdash; Adaptive Learning Engine
      </footer>
    </div>
  );
}

export default App;
