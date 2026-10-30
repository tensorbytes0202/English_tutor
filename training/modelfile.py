"""Write the Modelfile from prompts.py, so the prompt in it can never differ from the one used in training.

    python -m training.modelfile
"""
from pathlib import Path

from prompts import SYSTEM_PROMPT

TEMPLATE = '''# Ollama config for the fine-tuned tutor. Written by `python -m training.modelfile`: edit prompts.py, not this file.
# Put english-tutor.Q4_K_M.gguf (from the Colab notebook) next to this file, then run:
#   ollama create english-tutor -f Modelfile
FROM ./english-tutor.Q4_K_M.gguf

# Qwen chat format (the same one used in training).
TEMPLATE """{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}
{{- range .Messages }}{{- if ne .Role "system" }}<|im_start|>{{ .Role }}
{{ .Content }}<|im_end|>
{{ end }}{{- end }}<|im_start|>assistant
"""

SYSTEM """%s"""

# Low temperature: a correction should be the same every time.
PARAMETER temperature 0.2
PARAMETER num_ctx 2048
PARAMETER stop "<|im_end|>"
'''


def render():
    return TEMPLATE % SYSTEM_PROMPT


if __name__ == "__main__":
    (Path(__file__).parent.parent / "Modelfile").write_text(render(), encoding="utf-8")
    print("Modelfile written")
