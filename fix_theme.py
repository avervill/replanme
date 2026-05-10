import os

file_path = r"c:\Users\kuday\replanme\apps\web\src\components\schedule-workspace.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    code = f.read()

replacements = {
    "bg-white/78": "bg-[#0F172A]/40 backdrop-blur-md rounded-[16px] border border-[rgba(255,255,255,0.06)]",
    "border-black/5": "border-[rgba(255,255,255,0.06)]",
    "border-black/10": "border-[rgba(255,255,255,0.06)]",
    "bg-white/70": "bg-transparent",
    "bg-white/75": "bg-[rgba(255,255,255,0.02)]",
    "bg-white/65": "bg-[rgba(255,255,255,0.01)]",
    "bg-white/85": "bg-transparent",
    "bg-white/90": "bg-transparent text-white",
    "bg-slate-50/70": "bg-transparent",
    "bg-slate-50": "bg-[rgba(255,255,255,0.02)]",
    "bg-slate-100": "bg-[rgba(255,255,255,0.05)]",
    "hover:bg-slate-100": "hover:bg-[rgba(255,255,255,0.05)] text-white",
    "hover:bg-slate-200": "hover:bg-[rgba(255,255,255,0.08)]",
    "hover:bg-[#2563d8]/[0.04]": "hover:bg-[rgba(255,255,255,0.02)]",
    "text-slate-600": "text-calm-muted",
    "text-slate-500": "text-calm-muted opacity-80",
    "text-slate-400": "text-calm-muted opacity-70",
    "text-slate-700": "text-calm-text",
    "text-ink": "text-white",
    "bg-mist": "bg-[rgba(255,255,255,0.05)]",
    "bg-ink": "bg-calm-primary",
    "border-amber-200": "border-amber-500/20",
    "bg-amber-50": "bg-amber-500/5",
    "text-amber-950": "text-amber-100",
    "text-amber-900/80": "text-amber-200/80",
    "border-red-200": "border-red-500/20",
    "bg-red-50": "bg-red-500/5",
    "text-red-950": "text-red-100",
    "text-red-900/80": "text-red-200/80",
}

for old, new in replacements.items():
    code = code.replace(old, new)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(code)

print("Theme replaced successfully")
