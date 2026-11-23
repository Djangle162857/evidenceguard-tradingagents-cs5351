# EvidenceGuard 答辩材料

20 页 CityU Beamer，包含 17 页主讲和 3 页问答备查。幻灯片为英文。[逐页中英文对照讲稿](speaker-notes.zh-en.md)提供两种语言的完整口播。任选一种语言排练，主讲目标约 18 分钟，包含 90 秒离线演示。

工程证据截点为 2026 年 11 月 20 日。封面采用排练稿上的 Group 42，正式组号以课程确认为准。代码处于 v0.3 候选审阅阶段。已知渲染缺陷和仍待完成的正式评估见[工程审查](../../verification/v0.3/final-review.md)。

## 编译 CityU Beamer

此稿采用 [inscripoem/cityu-beamer](https://github.com/inscripoem/cityu-beamer/tree/13e6b1d2f56e9480563d91e75df5b3215f235470) 的社区模板。主题代码和字体随源码提供，许可证分别见 [LICENSE](LICENSE) 和[字体许可](fonts/GUST-FONT-LICENSE.txt)。CityU 校徽和背景图有[单独的版权声明](NOTICE.md)。从该模板固定提交的 `assets/` 取得四张背景图后，将该目录置于 `main.tex` 旁。文件名及 SHA-256 见[模板来源清单](template-provenance.json)。

在本目录运行以下命令。所需 TeX Live 包包括 Beamer、fontspec、ctex/Fandol、Latin Modern、TikZ、booktabs 和 tabularx。

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build main.tex
```

成品位于 `build/main.pdf`。[讲稿 PDF](speaker-notes.zh-en.pdf)可直接打开或打印。

## 第 11 页离线演示

从仓库根目录执行。先按[项目说明](../../../README.md)安装依赖。

```bash
mkdir -p results
demo_dir="$(mktemp -d results/defense.XXXXXX)"
.venv/bin/evidenceguard replay examples/offline-replay.json --out "$demo_dir/draft.json"
.venv/bin/evidenceguard inspect "$demo_dir/draft.json"
.venv/bin/evidenceguard review publish "$demo_dir/draft.json" --store "$demo_dir/empty-review" --out "$demo_dir/published.json"
```

打开 `draft.json` 查看 `completed / passed / pending / draft`。最后一条命令应返回退出码 2，并显示 `no review recorded for current artifact`。回放使用合成夹具，模型请求数为零。[复测记录](../../verification/v0.3/public-regression.txt)
