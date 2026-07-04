// frontend/lib/signalLabels.js
// Plain-English labels for every correlation signal produced by the backend.
// Backed by SIGNAL_WEIGHTS in backend/correlation/correlation_engine.py.
// Icons are optional visual glyphs; use them in the analysis panel.

export const SIGNAL_LABELS = {
  // Hard anchors (strongest evidence)
  exact_phone_match:      { label: "Same phone number",        icon: "📞", tier: "hard" },
  exact_email_match:      { label: "Same email address",       icon: "📧", tier: "hard" },
  exact_upi_match:        { label: "Same UPI ID",              icon: "🏦", tier: "hard" },
  profile_photo_phash:    { label: "Matching profile photo",   icon: "🖼️", tier: "hard" },
  face_match:             { label: "Same face (biometric)",    icon: "🧑", tier: "hard" },
  bio_url_match:          { label: "Bio links match",          icon: "🔗", tier: "hard" },
  breach_co_occurrence:   { label: "Appears in same breaches", icon: "🛡️", tier: "hard" },

  // Identity signals
  username_exact_match:    { label: "Username: exact match",         icon: "🆔", tier: "identity" },
  username_substring_match:{ label: "Username: partial match",       icon: "🆔", tier: "identity" },
  username_fuzzy_match:    { label: "Username: similar spelling",    icon: "🆔", tier: "identity" },
  exact_name_match:        { label: "Same full name",                icon: "👤", tier: "identity" },
  fuzzy_name_match:        { label: "Similar name spelling",         icon: "👤", tier: "identity" },

  // Context / corroborating signals
  location_overlap:      { label: "Same declared location",     icon: "📍", tier: "context" },
  city_match:            { label: "Same city (in bio)",         icon: "🏙️", tier: "context" },
  employer_overlap:      { label: "Same employer or school",    icon: "🏢", tier: "context" },
  posting_hours_overlap: { label: "Active in same hours",       icon: "🕒", tier: "context" },
  stylometry_cosine:     { label: "Similar writing style",      icon: "✍️", tier: "context" },
  bio_keyword_overlap:   { label: "Shared bio keywords",        icon: "🏷️", tier: "context" },
  mutual_connections:    { label: "Shared connections",         icon: "👥", tier: "context" },
  reciprocal_mention:    { label: "Mention each other",         icon: "↔️", tier: "context" },

  // AI adjudication — the LLM examiner judged these the same person holistically.
  llm_same_person:       { label: "AI-assessed same person",    icon: "🤖", tier: "identity" },
  semantic_rerank_match: { label: "Semantic profile match",     icon: "🧠", tier: "context" },
};

export function labelFor(signalName) {
  return SIGNAL_LABELS[signalName]?.label
    ?? signalName.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export function iconFor(signalName) {
  return SIGNAL_LABELS[signalName]?.icon ?? "•";
}

export function tierFor(signalName) {
  return SIGNAL_LABELS[signalName]?.tier ?? "context";
}
