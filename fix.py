import re

with open('core/script_generator.py', 'rb') as f:
    content = f.read().decode('utf-8', errors='ignore')

# 1. Update EDITORIAL GUIDELINES #2
content = re.sub(
    r'provide deep, insightful context and background analysis for the top news stories\.',
    r'provide deep, factual context and historical background for the top news stories. Do NOT add subjective analysis or commentary.',
    content
)

# 2. Update EDITORIAL GUIDELINES #10
content = re.sub(
    r'Pad the script with rich, valuable context on Vietnam\'s economic situation, detailed background on companies mentioned, and thorough explanations of how policies impact foreign businesses\.',
    r'Pad the script with rich, factual context on Vietnam\'s economic situation, historical background on companies mentioned, and objective explanations of policies. Do NOT give business advice.',
    content
)

# 3. Add to STRICT PROHIBITIONS in generate_podcast_script
prohibitions_addition = """
    - NO SUBJECTIVE INTERPRETATION OR ADVICE: Do NOT add any phrases like "建議您..." (I suggest you...), "這是一個重要警示" (This is an important warning), or "這凸顯了...".
    - Strictly report only the objective facts of the news. Do NOT give business, investment, or personal advice."""

if "NO SUBJECTIVE INTERPRETATION OR ADVICE" not in content:
    content = content.replace(
        '### STRICT PROHIBITIONS ###',
        f'### STRICT PROHIBITIONS ###{prohibitions_addition}'
    )

# 4. Add to STRICT RULES in review_and_improve_script (editor_prompt)
editor_rules_addition = """
    10. STRICTLY REMOVE all subjective interpretations, opinions, warnings, and business advice (e.g. remove phrases like "建議您...", "這是一個警示")."""

if "STRICTLY REMOVE all subjective interpretations" not in content:
    # Find the place in editor_prompt
    content = re.sub(
        r'(9\. For weather tips:.*?\n)',
        r'\1' + editor_rules_addition + '\n',
        content,
        count=1
    )

with open('core/script_generator.py', 'wb') as f:
    f.write(content.encode('utf-8'))

print("Modifications applied successfully.")
