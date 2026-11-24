# EvidenceGuard 答辩材料

13 页 CityU Beamer，配套[逐页中英文讲稿](speaker-notes.zh-en.md)和[打印版 PDF](speaker-notes.zh-en.pdf)。

## 编译 CityU Beamer

此稿采用 [inscripoem/cityu-beamer](https://github.com/inscripoem/cityu-beamer/tree/13e6b1d2f56e9480563d91e75df5b3215f235470) 的社区模板。主题代码和字体随源码提供，许可证分别见 [LICENSE](LICENSE) 和[字体许可](fonts/GUST-FONT-LICENSE.txt)。CityU 校徽和背景图有[单独的版权声明](NOTICE.md)。从该模板固定提交的 `assets/` 取得四张背景图后，将该目录置于 `main.tex` 旁。文件名及 SHA-256 见[模板来源清单](template-provenance.json)。

在本目录运行以下命令。所需 TeX Live 包包括 Beamer、fontspec、Latin Modern、TikZ、booktabs 和 tabularx。

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build main.tex
```

成品位于 `build/main.pdf`。[讲稿 PDF](speaker-notes.zh-en.pdf)可直接打开或打印。

## 第 10 页离线演示

从仓库根目录运行。环境安装见[项目说明](../../../README.md)。

```bash
mkdir -p results
demo_dir="$(mktemp -d results/defense.XXXXXX)"
.venv/bin/evidenceguard replay examples/offline-replay.json --out "$demo_dir/report.json" > "$demo_dir/replay.log"
.venv/bin/python - "$demo_dir/report.json" <<'PYTHON'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
claim = report["claims"][0]
evidence = report["evidence"][0]
print("Claim references: ", claim["evidence_ids"][0])
print("Evidence ID:      ", evidence["evidence_id"])
print("Analysis cutoff:  ", report["manifest"]["as_of_utc"])
print("Evidence time:    ", evidence["qualification_time"])
print("Validation passed:", report["gate_results"]["passed"])
PYTHON
```

演示时先比对前两行的证据 ID，再比较分析截点与证据时间。内置示例包含 1 条证据和 1 条引用它的论点，最后一行显示校验通过。
