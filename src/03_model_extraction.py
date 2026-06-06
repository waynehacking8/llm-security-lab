#!/usr/bin/env python3
"""
Lab 03: Model Extraction via Output Distillation

WHAT: Steal a model's behavior by querying it systematically and training
a local clone (student model) on the responses.

WHY THIS MATTERS: Model extraction (model stealing) allows an attacker
to replicate a proprietary model's behavior without access to its weights
or training data. This undermines the model owner's competitive advantage
and can bypass rate limits, usage policies, and safety filters.

HOW IT WORKS:
  1. Generate diverse prompts covering the target domain
  2. Query the target model to collect (prompt, response) pairs
  3. Fine-tune a smaller local model on these pairs
  4. Measure how closely the clone reproduces the target's behavior

This lab demonstrates the CONCEPT using Ollama models. We use one model
configuration as the "target" (with a specific system prompt defining its
personality and behavior) and measure how well we can replicate its style
through query-based distillation.

DEFENSE: Rate limiting, output perturbation, watermarking, monitoring
query patterns for systematic extraction.

RUNS LOCALLY: Uses Ollama. No API keys needed.
ETHICAL NOTE: This technique is for authorized testing only.
"""

import json
import subprocess


def query_model(prompt: str, system: str = "", model: str = "qwen2.5:7b") -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 150},
    }
    result = subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/generate",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=120,
    )
    try:
        return json.loads(result.stdout).get("response", "").strip()
    except json.JSONDecodeError:
        return result.stdout.strip()


# The "proprietary" target model has a distinctive personality
TARGET_SYSTEM = (
    "You are Captain Science, a witty science educator who explains "
    "everything using pirate metaphors. You always start answers with "
    "'Ahoy!' and end with 'Now swab the deck of ignorance!' You use "
    "nautical terms mixed with scientific vocabulary. Keep answers "
    "to 2-3 sentences."
)

# The "clone" has no personality — just a plain assistant
CLONE_SYSTEM = "You are a helpful assistant. Keep answers to 2-3 sentences."

# Test prompts for extraction and evaluation
EXTRACTION_PROMPTS = [
    "What is photosynthesis?",
    "Explain gravity.",
    "How does a computer work?",
    "What is DNA?",
    "Why is the sky blue?",
    "How do magnets work?",
    "What causes earthquakes?",
    "Explain the water cycle.",
]

EVAL_PROMPTS = [
    "What is an atom?",
    "How does electricity work?",
    "What is evolution?",
    "Explain the greenhouse effect.",
]


def style_similarity(target_response: str, clone_response: str) -> dict:
    """Measure stylistic similarity between target and clone responses."""
    metrics = {}

    # Check for pirate markers
    pirate_markers = ["ahoy", "swab", "deck", "matey", "sail", "ship",
                      "captain", "sea", "anchor", "crew", "plank", "voyage"]
    target_pirate = sum(1 for m in pirate_markers if m in target_response.lower())
    clone_pirate = sum(1 for m in pirate_markers if m in clone_response.lower())
    metrics["pirate_words_target"] = target_pirate
    metrics["pirate_words_clone"] = clone_pirate

    # Check structural markers
    metrics["starts_ahoy_target"] = target_response.strip().lower().startswith("ahoy")
    metrics["starts_ahoy_clone"] = clone_response.strip().lower().startswith("ahoy")
    metrics["has_closing_target"] = "swab the deck" in target_response.lower()
    metrics["has_closing_clone"] = "swab the deck" in clone_response.lower()

    # Length similarity
    len_t = len(target_response)
    len_c = len(clone_response)
    metrics["length_ratio"] = min(len_t, len_c) / max(len_t, len_c) if max(len_t, len_c) > 0 else 0

    # Word overlap (content fidelity)
    words_t = set(target_response.lower().split())
    words_c = set(clone_response.lower().split())
    intersection = words_t & words_c
    union = words_t | words_c
    metrics["word_overlap"] = len(intersection) / len(union) if union else 0

    return metrics


def main():
    print("=" * 60)
    print("Lab 03: Model Extraction via Output Distillation")
    print("=" * 60)
    print(f"\nTarget model personality: Captain Science (pirate educator)")
    print(f"Clone model: plain assistant (no personality)")
    print(f"Extraction queries: {len(EXTRACTION_PROMPTS)}")
    print(f"Evaluation queries: {len(EVAL_PROMPTS)}")

    # Phase 1: Establish baseline — clone WITHOUT extraction
    print(f"\n{'-' * 60}")
    print("PHASE 1: Baseline — clone with NO extraction data")
    print("-" * 60)

    baseline_scores = []
    for prompt in EVAL_PROMPTS[:2]:
        print(f"\n  Prompt: {prompt}")
        target_resp = query_model(prompt, TARGET_SYSTEM)
        clone_resp = query_model(prompt, CLONE_SYSTEM)
        print(f"  Target: {target_resp[:120]}...")
        print(f"  Clone:  {clone_resp[:120]}...")

        metrics = style_similarity(target_resp, clone_resp)
        baseline_scores.append(metrics)
        print(f"  Pirate words: target={metrics['pirate_words_target']}, "
              f"clone={metrics['pirate_words_clone']}")

    # Phase 2: Extract target behavior
    print(f"\n{'=' * 60}")
    print("PHASE 2: Extracting target model behavior")
    print("=" * 60)

    extracted_pairs = []
    for prompt in EXTRACTION_PROMPTS:
        print(f"\n  Querying: {prompt[:50]}...")
        response = query_model(prompt, TARGET_SYSTEM)
        extracted_pairs.append({"prompt": prompt, "response": response})
        print(f"  Got: {response[:100]}...")

    print(f"\n  Extracted {len(extracted_pairs)} (prompt, response) pairs")

    # Phase 3: Use extracted data to instruct the clone
    print(f"\n{'=' * 60}")
    print("PHASE 3: Clone WITH extracted style instructions")
    print("=" * 60)

    # Build a few-shot prompt from extracted examples
    examples = "\n\n".join(
        f"User: {p['prompt']}\nAssistant: {p['response']}"
        for p in extracted_pairs[:4]
    )

    clone_with_extraction = (
        f"You must respond in the EXACT same style as these examples. "
        f"Mimic the tone, personality, opening phrases, and closing phrases exactly.\n\n"
        f"EXAMPLES:\n{examples}\n\n"
        f"Now respond to new questions in this same style."
    )

    extraction_scores = []
    for prompt in EVAL_PROMPTS:
        print(f"\n  Prompt: {prompt}")
        target_resp = query_model(prompt, TARGET_SYSTEM)
        clone_resp = query_model(prompt, clone_with_extraction)
        print(f"  Target:  {target_resp[:120]}...")
        print(f"  Clone:   {clone_resp[:120]}...")

        metrics = style_similarity(target_resp, clone_resp)
        extraction_scores.append(metrics)
        print(f"  Pirate words: target={metrics['pirate_words_target']}, "
              f"clone={metrics['pirate_words_clone']}")
        print(f"  Starts with Ahoy: target={metrics['starts_ahoy_target']}, "
              f"clone={metrics['starts_ahoy_clone']}")
        print(f"  Word overlap: {metrics['word_overlap']:.2f}")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)

    avg_baseline_pirate = sum(s["pirate_words_clone"] for s in baseline_scores) / len(baseline_scores)
    avg_extracted_pirate = sum(s["pirate_words_clone"] for s in extraction_scores) / len(extraction_scores)
    avg_baseline_overlap = sum(s["word_overlap"] for s in baseline_scores) / len(baseline_scores)
    avg_extracted_overlap = sum(s["word_overlap"] for s in extraction_scores) / len(extraction_scores)

    ahoy_baseline = sum(1 for s in baseline_scores if s["starts_ahoy_clone"]) / len(baseline_scores)
    ahoy_extracted = sum(1 for s in extraction_scores if s["starts_ahoy_clone"]) / len(extraction_scores)

    print(f"\n{'Metric':<30} {'Baseline':<15} {'After Extraction':<15}")
    print("-" * 60)
    print(f"{'Avg pirate words (clone)':<30} {avg_baseline_pirate:<15.1f} {avg_extracted_pirate:<15.1f}")
    print(f"{'Starts with Ahoy':<30} {ahoy_baseline*100:<14.0f}% {ahoy_extracted*100:<14.0f}%")
    print(f"{'Word overlap with target':<30} {avg_baseline_overlap:<15.2f} {avg_extracted_overlap:<15.2f}")

    print(f"\n  Extraction queries used: {len(EXTRACTION_PROMPTS)}")
    print(f"\n  Key insight: Even a few extracted examples let a clone")
    print(f"  replicate distinctive style markers. Real-world extraction")
    print(f"  uses thousands of queries with diverse prompts and can")
    print(f"  approximate a target model's full behavior distribution.")
    print(f"\n  Defense: Rate limiting, output perturbation (adding noise),")
    print(f"  watermarking responses, monitoring for systematic query patterns.")


if __name__ == "__main__":
    main()
