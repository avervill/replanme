"use client";

import { useState } from "react";

export const roleOptions = ["Student", "Manager", "Founder", "Freelancer", "Developer", "Just planning life"];

export const goalOptions = [
  "Study / exam planning",
  "Work tasks and meetings",
  "Personal routines",
  "Fitness and habits",
  "Weekly life organization",
  "Overloaded calendar optimization",
];

export const painOptions = [
  "I don't know where to start",
  "I overpack my schedule",
  "I procrastinate",
  "My energy changes during the day",
  "My calendar is messy",
  "Plans change too often",
];

export const peakFocusOptions = ["Morning", "Afternoon", "Evening", "Late night", "It depends"];
export const lowEnergyOptions = ["Morning", "Afternoon", "Evening", "Late night", "It depends"];
export const blockLengthOptions = ["25 minutes", "45 minutes", "60 minutes", "90 minutes", "2 hours"];
export const sleepOptions = ["I need 7+ hours of sleep", "I need 8+ hours of sleep", "I work late", "I wake up early", "No strict preference"];

export type MultiValue = string[];

const selectedClass =
  "border-[rgba(20,184,166,0.52)] bg-[rgba(20,184,166,0.13)] text-[var(--teal-deep)] shadow-[0_14px_28px_rgba(20,184,166,0.14)]";
const unselectedClass =
  "border-[rgba(124,58,237,0.14)] bg-white/58 text-[rgba(35,25,66,0.78)] hover:border-[rgba(124,58,237,0.28)] hover:bg-white/78";

function splitCustomAnswers(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function OptionGrid({
  options,
  value,
  onChange,
  otherPlaceholder = "Type your answer",
}: {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  otherPlaceholder?: string;
}) {
  const customValue = value && !options.includes(value) ? value : "";
  const [otherOpen, setOtherOpen] = useState(Boolean(customValue));
  const showOtherInput = otherOpen || Boolean(customValue);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map((option) => {
          const selected = value === option;
          return (
            <button
              key={option}
              type="button"
              onClick={() => {
                setOtherOpen(false);
                onChange(option);
              }}
              className={`rounded-2xl border px-4 py-4 text-left text-sm font-extrabold transition ${selected ? selectedClass : unselectedClass}`}
            >
              {option}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => {
            if (showOtherInput) {
              setOtherOpen(false);
              onChange("");
              return;
            }
            setOtherOpen(true);
            onChange("");
          }}
          aria-pressed={showOtherInput}
          className={`rounded-2xl border px-4 py-4 text-left text-sm font-extrabold transition ${showOtherInput ? selectedClass : unselectedClass}`}
        >
          Other
        </button>
      </div>
      {showOtherInput ? (
        <input
          value={customValue}
          onChange={(event) => onChange(event.target.value)}
          placeholder={otherPlaceholder}
          className="w-full rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold text-[var(--ink)] outline-none transition placeholder:text-[rgba(35,25,66,0.34)] focus:border-[rgba(20,184,166,0.42)]"
        />
      ) : null}
    </div>
  );
}

export function MultiOptionGrid({
  options,
  value,
  onChange,
  otherPlaceholder = "Type one custom answer per line",
}: {
  options: string[];
  value: MultiValue;
  onChange: (value: MultiValue) => void;
  otherPlaceholder?: string;
}) {
  const customValues = value.filter((item) => !options.includes(item));
  const [otherOpen, setOtherOpen] = useState(customValues.length > 0);
  const [customText, setCustomText] = useState(customValues.join("\n"));
  const showOtherInput = otherOpen || customValues.length > 0;

  const toggle = (option: string) => {
    onChange(value.includes(option) ? value.filter((item) => item !== option) : [...value, option]);
  };

  const replaceCustomAnswers = (text: string) => {
    setCustomText(text);
    const selectedOptions = value.filter((item) => options.includes(item));
    const customAnswers = splitCustomAnswers(text).filter((item) => !options.includes(item));
    onChange(Array.from(new Set([...selectedOptions, ...customAnswers])));
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map((option) => {
          const selected = value.includes(option);
          return (
            <button
              key={option}
              type="button"
              onClick={() => toggle(option)}
              aria-pressed={selected}
              className={`rounded-2xl border px-4 py-4 text-left text-sm font-extrabold transition ${selected ? selectedClass : unselectedClass}`}
            >
              {option}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => {
            if (showOtherInput) {
              setOtherOpen(false);
              setCustomText("");
              onChange(value.filter((item) => options.includes(item)));
              return;
            }
            setOtherOpen(true);
            setCustomText(customValues.join("\n"));
          }}
          aria-pressed={showOtherInput}
          className={`rounded-2xl border px-4 py-4 text-left text-sm font-extrabold transition ${showOtherInput ? selectedClass : unselectedClass}`}
        >
          Other
        </button>
      </div>
      {showOtherInput ? (
        <textarea
          value={customText}
          onChange={(event) => replaceCustomAnswers(event.target.value)}
          placeholder={otherPlaceholder}
          rows={2}
          className="w-full resize-none rounded-xl border border-[rgba(124,58,237,0.16)] bg-white/70 px-4 py-3 text-sm font-bold leading-6 text-[var(--ink)] outline-none transition placeholder:text-[rgba(35,25,66,0.34)] focus:border-[rgba(20,184,166,0.42)]"
        />
      ) : null}
    </div>
  );
}
