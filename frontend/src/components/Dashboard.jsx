import { useState } from "react";
import {
  Zap,
  BookOpen,
  Gauge,
  Target,
  TrendingDown,
  ChevronDown,
} from "lucide-react";

/* ── Constants for dropdowns ─────────────────────────────── */
const EXAM_SECTIONS = [
  "Quantitative Aptitude",
  "Logical Reasoning",
  "Verbal Ability",
];

const DIFFICULTIES = ["Easy", "Medium", "Hard"];

const DEFAULT_TOPICS = {
  "Quantitative Aptitude": [
    "Percentages",
    "Time & Work",
    "Algebra",
    "Geometry",
    "Probability",
    "Ratio & Proportion",
  ],
  "Logical Reasoning": [
    "Syllogisms",
    "Blood Relations",
    "Puzzles",
    "Data Sufficiency",
    "Direction Sense",
  ],
  "Verbal Ability": [
    "Reading Comprehension",
    "Sentence Correction",
    "Vocabulary",
    "Para Jumbles",
  ],
};

function Dashboard({ onStartTest }) {
  // ── Test configuration state ─────────────────────────────
  const [selectedSection, setSelectedSection] = useState(EXAM_SECTIONS[0]);
  const [selectedTopic, setSelectedTopic] = useState(DEFAULT_TOPICS[EXAM_SECTIONS[0]][0]);
  const [selectedDifficulty, setSelectedDifficulty] = useState(DIFFICULTIES[1]);

  // ── When section changes, reset topic to the first for that section ──
  const handleSectionChange = (section) => {
    setSelectedSection(section);
    const topics = DEFAULT_TOPICS[section] || [];
    setSelectedTopic(topics[0] || "");
  };

  const handleStartTest = () => {
    if (!selectedTopic.trim()) return;
    onStartTest({
      topic: selectedSection,
      subTopic: selectedTopic.trim(),
      difficulty: selectedDifficulty,
    });
  };

  const currentTopics = DEFAULT_TOPICS[selectedSection] || [];

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight text-white mb-3">
          Configure Your Practice Session
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto">
          Select your desired topic and difficulty. Our AI will instantly generate 
          a custom 10-question test tailored to your specifications.
        </p>
      </div>

      {/* ── Test Configuration ──────────────────────────────── */}
      <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-8 shadow-xl">
        <div className="mb-6 flex items-center justify-center gap-2">
          <Target className="h-6 w-6 text-violet-400" />
          <h2 className="text-xl font-semibold text-white">
            Test Configuration
          </h2>
        </div>

        <div className="grid gap-6 sm:grid-cols-3">
          {/* Exam Section */}
          <SelectField
            icon={<BookOpen className="h-4 w-4 text-gray-400" />}
            label="Exam Section"
            value={selectedSection}
            onChange={handleSectionChange}
            options={EXAM_SECTIONS}
          />

          {/* Specific Topic */}
          <SelectField
            icon={<TrendingDown className="h-4 w-4 text-gray-400" />}
            label="Specific Topic"
            value={selectedTopic}
            onChange={setSelectedTopic}
            options={currentTopics}
          />

          {/* Difficulty */}
          <SelectField
            icon={<Gauge className="h-4 w-4 text-gray-400" />}
            label="Difficulty"
            value={selectedDifficulty}
            onChange={setSelectedDifficulty}
            options={DIFFICULTIES}
          />
        </div>
      </div>

      {/* CTA */}
      <div className="rounded-2xl border border-gray-800 bg-gradient-to-br from-violet-500/10 via-gray-900/80 to-gray-900/80 p-10 text-center shadow-xl">
        <h2 className="text-2xl font-semibold text-white">
          Ready to practice{" "}
          <span className="text-violet-400">{selectedTopic}</span>
          {" · "}
          <span className="text-amber-400">{selectedDifficulty}</span>
        </h2>
        <p className="mt-3 text-gray-400">
          Click below to generate a batch of 10 high-quality questions.
        </p>

        <button
          onClick={handleStartTest}
          disabled={!selectedTopic.trim()}
          className="mt-8 inline-flex items-center gap-2 rounded-xl bg-violet-600 px-10 py-4 text-base font-semibold text-white shadow-lg shadow-violet-600/25 transition-all hover:bg-violet-500 hover:scale-105 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100"
        >
          <Zap className="h-5 w-5" />
          Generate 10 Questions
        </button>
      </div>
    </div>
  );
}

/* ── Select dropdown field ───────────────────────────────── */
function SelectField({ icon, label, value, onChange, options }) {
  return (
    <div>
      <label className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-gray-400">
        {icon}
        {label}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full appearance-none rounded-xl border border-gray-700 bg-gray-800/80 px-5 py-3.5 pr-12 text-sm font-medium text-white transition-all hover:border-gray-500 hover:bg-gray-800 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/40 cursor-pointer"
        >
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-500" />
      </div>
    </div>
  );
}

export default Dashboard;
