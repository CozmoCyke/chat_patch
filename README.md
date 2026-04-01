# chat_patch

Apply AI-generated code patches safely.

## ✨ Features

- Apply unified diff patches from stdin
- Interactive confirmation
- Works with legacy encodings (latin1 / mojibake)
- Designed to integrate with automation tools like `replace_auto`

## 🚀 Usage

```bash
chat_patch <<'PATCH'
--- a/file.cpp
+++ b/file.cpp
@@
- old code
+ new code
PATCH

🧠 Philosophy

Instead of manually editing files based on AI suggestions,
this tool lets you apply them as structured patches.

🔧 Roadmap
 dry-run mode
 auto-apply mode
 multi-file patch support
 encoding normalization
 integration with search/replace pipelines
